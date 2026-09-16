from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def load_config(path=None):
    path = Path(path or ROOT / "config.toml").resolve()
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    p, c, o = (config[key] for key in ("processing", "camera", "output"))
    p.setdefault('recovery', True)
    p.setdefault('recovery_attempts', 160)
    p.setdefault('max_seconds', 20.0)
    c.setdefault('max_scan_seconds', 2.0)
    if not isinstance(p['recovery'], bool):
        raise ValueError('processing.recovery must be boolean')
    if type(p['recovery_attempts']) is not int or not 1 <= p['recovery_attempts'] <= 600:
        raise ValueError('recovery_attempts must be an integer from 1 to 600')
    for value in (p['max_seconds'], c['max_scan_seconds']):
        if type(value) not in (int, float) or not .1 <= value <= 120:
            raise ValueError('Scan time budgets must be 0.1..120 seconds')
    for key in ("auto_crop", "denoise", "enhance_contrast", "threshold"):
        if not isinstance(p[key], bool):
            raise ValueError(f"processing.{key} must be boolean")
    if not 320 <= p["max_dimension"] <= 6000:
        raise ValueError("max_dimension must be between 320 and 6000")
    if not 1 <= p["upscale"] <= 3 or not 1 <= p["max_attempts"] <= 60:
        raise ValueError("upscale must be 1..3; max_attempts must be 1..60")
    allowed = {"PDF417", "QRCode", "DataMatrix", "Code128", "Aztec", "EAN13"}
    if not p["formats"] or not set(p["formats"]) <= allowed:
        raise ValueError(f"processing.formats must use: {sorted(allowed)}")
    if not o["formats"] or not set(o["formats"]) <= {"csv", "json"}:
        raise ValueError("output.formats must contain csv and/or json")
    for key in ("auto_save", "deduplicate", "csv_excel_safe"):
        if not isinstance(o[key], bool):
            raise ValueError(f"output.{key} must be boolean")
    if not 0.1 <= c["scan_interval_seconds"] <= 60:
        raise ValueError("scan_interval_seconds must be 0.1..60")
    if c["index"] < 0 or not all(160 <= c[k] <= 4096 for k in ("width", "height")):
        raise ValueError("Invalid camera index or dimensions")
    o["directory"] = str((path.parent / o["directory"]).resolve())
    return config
