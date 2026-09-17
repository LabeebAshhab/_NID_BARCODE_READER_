"""Locate the barcode before reading it.

This stage runs ahead of the general preprocessing in :mod:`nid_scanner.pipeline`.
It finds barcode-like regions in the frame (dense directional bar structure),
ranks them so the sharpest, best-focused card is tried first, and emits a
brightness/sharpness-enhanced version of each region for blurry or noisy
captures. It only reads the supplied image; it never consults originals or
saved payloads. Detection is heuristic: when nothing is found the caller still
falls back to the full existing pipeline, so a missed detection never loses a
read that the fallback would have made.

Both back-of-card layouts are handled the same way: whether the barcode sits at
the top (laminated PDF417 card) or along the bottom (older paper card / chip
card), it is the densest bar region in the frame and is located by the same
gradient response, then decoded by ZXing.
"""
import cv2
import numpy as np


def focus_measure(gray):
    """Sharpness of a region: variance of the Laplacian. Higher is sharper.

    Used to prefer an in-focus card over an out-of-focus one when several cards
    are visible (for example a blurred card held in hand over clear cards on a
    desk).
    """
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def enhance(gray):
    """Sharpen and brighten a region so a blurry, noisy crop can still decode.

    Light denoise -> unsharp mask -> CLAHE contrast/brightness lift. This does
    not invent bar detail; it only makes existing edges easier for the decoder.
    """
    denoised = cv2.bilateralFilter(gray, 5, 40, 40)
    blurred = cv2.GaussianBlur(denoised, (0, 0), 1.6)
    sharp = cv2.addWeighted(denoised, 1.8, blurred, -0.8, 0)
    return cv2.createCLAHE(3.0, (8, 8)).apply(sharp)


def _barcode_boxes(gray):
    """Bounding boxes of barcode-like regions, largest area first.

    A barcode is a dense run of parallel bars: strong gradient along one axis and
    weak along the other, packed far tighter than ordinary text. The directional
    edge *density* is measured over a window, only the densest areas are kept
    (so text and card artwork drop out), the surviving mask is closed along the
    bar axis into a band, and bands are filtered to elongated rectangles. Both
    axes are tried so the barcode is found whether it sits at the top or bottom
    of the card and whether the capture is upright or rotated.
    """
    h, w = gray.shape
    gx = np.clip(np.absolute(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)), 0, None)
    gy = np.clip(np.absolute(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)), 0, None)
    boxes = []
    for horizontal, grad in ((True, gx - gy), (False, gy - gx)):
        density = cv2.boxFilter(np.clip(grad, 0, None), -1, (max(15, w // 30), max(15, h // 30)))
        density = cv2.normalize(density, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        threshold = max(60, int(np.percentile(density, 92)))
        mask = (density >= threshold).astype(np.uint8) * 255
        if horizontal:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, w // 30), max(5, h // 120)))
        else:
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, w // 120), max(15, h // 30)))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for i in range(1, count):
            x, y, cw, ch, _ = stats[i]
            long_side, short_side = max(cw, ch), min(cw, ch)
            if not 0.01 * h * w < cw * ch < 0.75 * h * w or long_side < 1.6 * short_side:
                continue
            boxes.append((x, y, cw, ch))
    return sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)


def _dedupe(boxes):
    """Drop boxes that mostly overlap an already-kept, larger box."""
    kept = []
    for x, y, cw, ch in boxes:
        box_area = cw * ch
        redundant = False
        for kx, ky, kcw, kch in kept:
            ix = max(0, min(x + cw, kx + kcw) - max(x, kx))
            iy = max(0, min(y + ch, ky + kch) - max(y, ky))
            if ix * iy > 0.6 * box_area:
                redundant = True
                break
        if not redundant:
            kept.append((x, y, cw, ch))
    return kept


def barcode_score(region):
    """How barcode-like a region is, separating a real barcode from text.

    Two physical cues distinguish a card barcode from text such as the address
    block or the ``I<BGD…<<<`` machine-readable zone:

    * **Ink fill.** A PDF417/1D barcode is a dense block that is roughly half
      ink; text is mostly white with sparse strokes. Regions whose dark fraction
      is not in a barcode-like band are rejected outright. This holds even when a
      low-resolution barcode has blurred into a speckle: it is still a dense
      block, whereas crisp text never is.
    * **Bar structure.** Among dense regions, a barcode's bars run the full
      height (near-uniform rows) and switch between bar and space many times
      across the width; the score multiplies row *uniformity* by bar *fineness*.

    Returns 0 for shapes that cannot be a card barcode band (too small, too thin,
    not wide) or whose ink fill is text-like.
    """
    ch, cw = region.shape[:2]
    if ch < 24 or min(ch, cw) < 14 or cw < 2.2 * ch:
        return 0.0
    small = cv2.resize(region, (256, 96), interpolation=cv2.INTER_AREA)
    binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    fill = float((binary == 0).mean())
    if not 0.30 <= fill <= 0.80:
        return 0.0
    normalized = cv2.GaussianBlur(small, (3, 3), 0).astype(np.float32)
    row_profile = normalized.mean(axis=1)
    col_profile = normalized.mean(axis=0)
    uniformity = float(col_profile.std() / (row_profile.std() + 1e-3))
    centered = col_profile - col_profile.mean()
    transitions = int(np.count_nonzero(np.diff(np.sign(centered)) != 0))
    fineness = transitions / col_profile.size
    return uniformity * fineness


def detect_regions(image, config, max_regions=3, min_barcode_score=0.12):
    """Yield ``(stage, gray_crop)`` for located barcodes, best candidate first.

    Regions that look like a barcode (see :func:`barcode_score`) are kept and
    ordered by focus, so a real barcode is tried ahead of text such as the
    address block or machine-readable zone, and — among genuine barcodes — the
    sharpest, in-focus card is tried before a blurred one. If nothing clears the
    barcode-likeness bar, the most barcode-like regions are still tried as a
    fallback so a hard image never loses coverage. For each region several
    candidates are produced: the plain crop, a sharpened/brightened crop, and
    upscaled sharpened crops for small or slightly soft bars.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    boxes = _dedupe(_barcode_boxes(gray))
    if not boxes:
        return
    scored = []
    for x, y, cw, ch in boxes:
        margin = max(15, int(0.10 * min(cw, ch)))
        x0, y0 = max(0, x - margin), max(0, y - margin)
        x1, y1 = min(w, x + cw + margin), min(h, y + ch + margin)
        crop = gray[y0:y1, x0:x1]
        if crop.size == 0:
            continue
        scored.append((barcode_score(gray[y:y + ch, x:x + cw]), focus_measure(crop), crop))
    barcode_like = [item for item in scored if item[0] >= min_barcode_score]
    if barcode_like:
        # Real barcodes only: order by focus so the clearest card wins.
        ordered = sorted(barcode_like, key=lambda item: item[1], reverse=True)
    else:
        # Nothing clearly a barcode: fall back to the most barcode-like regions.
        ordered = sorted(scored, key=lambda item: item[0], reverse=True)
    for index, (_, focus, crop) in enumerate(ordered[:max_regions], 1):
        tag = f"Detected barcode {index} (focus {focus:.0f})"
        yield f"{tag} / crop", crop
        yield f"{tag} / enhanced", enhance(crop)
        long_side = max(crop.shape)
        for scale in (2.0, 3.0):
            if long_side * scale > 4000:
                continue
            upscaled = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            yield f"{tag} / enhanced x{scale:g}", enhance(upscaled)
