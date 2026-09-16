"""Image-only recovery candidates. Never consults originals, manifests or saved payloads."""
import cv2
import numpy as np


def estimate_skew(gray):
    scale = min(1.0, 1500 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
    edges = cv2.Canny(cv2.GaussianBlur(small, (5, 5), 1), 20, 70)
    lines = cv2.HoughLinesP(edges, 1, np.pi/720, 70,
                            minLineLength=max(30, small.shape[1]//6), maxLineGap=25)
    if lines is None:
        return 0.0
    angles = []
    for x1, y1, x2, y2 in lines[:, 0]:
        angle = np.degrees(np.arctan2(y2-y1, x2-x1))
        angles.append((angle+45) % 90-45)
    return float(np.median(angles))


def rotate(gray, angle):
    h, w = gray.shape
    matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    nw, nh = int(np.ceil(w*cos+h*sin)), int(np.ceil(h*cos+w*sin))
    matrix[:, 2] += ((nw-w)/2, (nh-h)/2)
    return cv2.warpAffine(gray, matrix, (nw, nh), borderValue=255)


def normalize_lighting(gray):
    smooth = cv2.GaussianBlur(gray, (0, 0), .7)
    light = cv2.GaussianBlur(smooth, (0, 0), 21)
    normalized = cv2.divide(smooth, np.maximum(light, 1), scale=180)
    low, high = np.percentile(normalized, (1, 99))
    if high-low < 5:
        return normalized
    return np.clip((normalized.astype(np.float32)-low)*255/(high-low), 0, 255).astype(np.uint8)


def sauvola(gray, window=31, k=.15):
    pixels = gray.astype(np.float32)
    mean = cv2.boxFilter(pixels, -1, (window, window))
    variance = np.maximum(cv2.boxFilter(pixels*pixels, -1, (window, window))-mean*mean, 0)
    threshold = mean*(1+k*(np.sqrt(variance)/128-1))
    return np.where(pixels > threshold, 255, 0).astype(np.uint8)


def candidates(image, config):
    """Progressive, bounded transforms, interleaving geometry before stronger filtering."""
    from .pipeline import barcode_regions
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    limit = config['max_dimension']
    if max(gray.shape) > limit:
        scale = limit/max(gray.shape)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    angle = estimate_skew(gray)
    aligned = rotate(gray, angle)
    yield f'Recovery / measured deskew {angle:+.2f} degrees', aligned, False
    bases = [('Aligned frame', aligned)]
    if config['auto_crop']:
        bases.extend((f'Aligned crop {i+1}', region) for i, region in enumerate(barcode_regions(aligned)))
    # Raw geometry first; important because stronger filters can destroy thin bars.
    for label, base in bases:
        yield f'Recovery / {label}', base, False
        yield f'Recovery / {label} / illumination', normalize_lighting(base), False
    for delta in (-2, 2, -5, 5):
        yield f'Recovery / deskew adjustment {delta:+}', rotate(gray, angle+delta), False
    # Different scales change the relationship between modules and decoder thresholds.
    for label, base in bases:
        normal = normalize_lighting(base)
        for scale in (.5, .75, 1.5, 2.0):
            if max(base.shape)*scale > 4000:
                continue
            yield f'Recovery / {label} / scale {scale}', cv2.resize(normal, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC), False
        for sigma, amount in ((1., 1.5), (1.8, 2.5), (2.8, 3.0)):
            blurred = cv2.GaussianBlur(normal, (0, 0), sigma)
            sharpened = cv2.addWeighted(normal, 1+amount, blurred, -amount, 0)
            yield f'Recovery / {label} / unsharp {sigma}', sharpened, False
            for block in (15, 31, 51):
                yield f'Recovery / {label} / Sauvola {sigma}/{block}', sauvola(sharpened, block), True
                yield f'Recovery / {label} / adaptive {sigma}/{block}', cv2.adaptiveThreshold(sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 3), True
