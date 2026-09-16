"""Create a synthetic PDF417 image containing no real identity data."""
from pathlib import Path
import numpy as np
from PIL import Image
import zxingcpp

target = Path(__file__).resolve().parent.parent / "examples" / "synthetic_pdf417.png"
target.parent.mkdir(exist_ok=True)
code = zxingcpp.create_barcode('name: SYNTHETIC TEST\nnid: 0000000000\ndob: 2000-01-01', zxingcpp.BarcodeFormat.PDF417)
Image.fromarray(np.asarray(code.to_image(scale=4))).save(target)
print(target)
