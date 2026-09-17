import base64
import hashlib
import time
from datetime import datetime, timezone
from uuid import uuid4
from itertools import islice

import cv2
import numpy as np
from PIL import Image, ImageOps
import zxingcpp

from .payload import parse_payload


def load_image(path):
    with Image.open(path) as image:
        if image.width * image.height > 40_000_000:
            raise ValueError("Image exceeds the 40 megapixel input limit")
        rgb = np.array(ImageOps.exif_transpose(image).convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def card_crop(image):
    """Try a large convex card boundary. Return None when uncertain."""
    h, w = image.shape[:2]
    ratio = min(1.0, 900 / max(h, w))
    small = cv2.resize(image, None, fx=ratio, fy=ratio)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 140)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        area = cv2.contourArea(contour) / (small.shape[0] * small.shape[1])
        polygon = cv2.approxPolyDP(contour, .02 * cv2.arcLength(contour, True), True)
        if not .15 < area < .98 or len(polygon) != 4 or not cv2.isContourConvex(polygon):
            continue
        pts = polygon.reshape(4, 2).astype(np.float32) / ratio
        # Sort cyclically, then start at the top-left corner.
        center = pts.mean(axis=0)
        pts = pts[np.argsort(np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0]))]
        pts = np.roll(pts, -np.argmin(pts.sum(axis=1)), axis=0)
        a, b, c, d = pts
        width = int(max(np.linalg.norm(b-a), np.linalg.norm(c-d)))
        height = int(max(np.linalg.norm(d-a), np.linalg.norm(c-b)))
        if min(width, height) < 100 or not 1.2 < max(width, height)/min(width, height) < 2.2:
            continue
        target = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
        return cv2.warpPerspective(image, cv2.getPerspectiveTransform(pts, target), (width, height))
    return None


def barcode_regions(gray):
    """Gradient-based candidates with margins; full frame remains a fallback.

    Candidates are ranked so barcode-like bands come before text (address block,
    machine-readable zone); clearly text-like regions are skipped, but the most
    barcode-like region is always kept so a hard image never loses coverage.
    """
    from .detect import barcode_score
    gradient = np.absolute(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    gradient = cv2.normalize(gradient, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    blurred = cv2.GaussianBlur(gradient, (9, 9), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 27), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    candidates = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw * ch < .015 * h * w or min(cw, ch) < 20:
            continue
        margin = max(20, int(.15 * max(cw, ch)))
        crop = gray[max(0, y-margin):min(h, y+ch+margin), max(0, x-margin):min(w, x+cw+margin)]
        candidates.append((barcode_score(gray[y:y+ch, x:x+cw]), crop))
    candidates.sort(key=lambda item: item[0], reverse=True)
    for index, (score, crop) in enumerate(candidates[:3]):
        # Keep the single best region regardless; drop clearly text-like extras.
        if index and score < 0.10:
            break
        yield crop


def variants(image, config):
    h, w = image.shape[:2]
    scale = min(1., config["max_dimension"] / max(h, w))
    if scale < 1:
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    yield "Full frame / grayscale", gray
    crop = card_crop(image) if config["auto_crop"] else None
    bases = []
    if crop is not None:
        bases.append(("Perspective-corrected card", cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)))
    bases.append(("Full frame", gray))
    for label, base in bases:
        if label != "Full frame":
            yield label, base
        if config["auto_crop"]:
            for index, region in enumerate(barcode_regions(base)):
                yield f"{label} / barcode crop {index+1}", region
        clean = base
        if config["denoise"]:
            clean = cv2.fastNlMeansDenoising(base, None, 7, 7, 21)
            yield f"{label} / denoised", clean
        if config["enhance_contrast"]:
            clean = cv2.createCLAHE(2., (8, 8)).apply(clean)
            yield f"{label} / contrast", clean
        if config["threshold"]:
            yield f"{label} / Otsu", cv2.threshold(clean, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
            yield f"{label} / adaptive", cv2.adaptiveThreshold(clean, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 9)
        if config["upscale"] > 1:
            yield f"{label} / enlarged", cv2.resize(base, None, fx=config["upscale"], fy=config["upscale"], interpolation=cv2.INTER_CUBIC)
        # ZXing handles right-angle rotations; these candidates correct modest camera skew.
        for angle in (-12, 12):
            h, w = base.shape
            matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
            cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
            nw, nh = int(h*sin+w*cos), int(h*cos+w*sin)
            matrix[:, 2] += ((nw-w)/2, (nh-h)/2)
            yield f"{label} / deskew {angle:+} degrees", cv2.warpAffine(base, matrix, (nw, nh), borderValue=255)


def scan(image, config, source="image", on_stage=None, cancelled=None):
    started = time.perf_counter()
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 2:
        raise ValueError("Expected a nonempty uint8 BGR image with at least 2x2 pixels")
    formats = [getattr(zxingcpp.BarcodeFormat, name) for name in config["formats"]]
    deadline = started + config.get('max_seconds', 20.0)
    def stopped():
        return time.perf_counter() >= deadline or (cancelled and cancelled())
    def attempts():
        # Locate the barcode before reading it: try focus-ranked detected regions
        # first (clearest card first), then fall back to the full existing pipeline.
        if config.get('detect', True):
            from .detect import detect_regions
            for stage, candidate in detect_regions(image, config):
                if stopped():
                    return
                yield stage, candidate, zxingcpp.Binarizer.LocalAverage
        for stage, candidate in islice(variants(image, config), config['max_attempts']):
            if stopped():
                return
            yield stage, candidate, zxingcpp.Binarizer.LocalAverage
        if not config.get('recovery', True) or stopped():
            return
        from .recovery import candidates
        count = 0
        for stage, candidate, binary in candidates(image, config):
            modes = [zxingcpp.Binarizer.FixedThreshold] if binary else [zxingcpp.Binarizer.LocalAverage, zxingcpp.Binarizer.GlobalHistogram]
            for mode in modes:
                if stopped() or count >= config.get('recovery_attempts', 160):
                    return
                count += 1
                yield f'{stage} / {mode.name}', candidate, mode
    for attempt, (stage, candidate, binarizer) in enumerate(attempts(), 1):
        if stopped():
            break
        if on_stage:
            on_stage(stage, candidate, attempt)
        results = zxingcpp.read_barcodes(candidate, formats=formats, try_rotate=True,
                                        try_downscale=True, try_invert=True, binarizer=binarizer)
        if cancelled and cancelled():
            break
        records = []
        for result in results:
            if not result.valid:
                continue
            raw = bytes(result.bytes)
            text = result.text
            points = [[getattr(result.position, p).x, getattr(result.position, p).y]
                      for p in ("top_left", "top_right", "bottom_right", "bottom_left")]
            records.append({"id": uuid4().hex, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "source": source, "format": str(result.format), "raw_text": text,
                            "raw_bytes_base64": base64.b64encode(raw).decode("ascii"),
                            "sha256": hashlib.sha256(raw).hexdigest(),
                            "byte_count": len(raw), "parsed": parse_payload(text, raw),
                            "stage": stage, "attempt": attempt, "orientation": result.orientation,
                            "position_in_stage": points,
                            "elapsed_ms": round((time.perf_counter()-started)*1000, 1)})
        if records:
            annotated = cv2.cvtColor(candidate, cv2.COLOR_GRAY2BGR)
            for record in records:
                cv2.polylines(annotated, [np.array(record["position_in_stage"], np.int32)], True, (70, 200, 40), 3)
            if on_stage:
                on_stage("Decoded / barcode bounds", annotated, attempt)
            return records
    return []
