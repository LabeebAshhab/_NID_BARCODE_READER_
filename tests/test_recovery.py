import base64
from pathlib import Path

import cv2
import numpy as np
import pytest
import zxingcpp

from nid_scanner.config import load_config
from nid_scanner.pipeline import load_image, scan
from nid_scanner.recovery import estimate_skew, normalize_lighting, rotate, sauvola
from degrade_images import degrade, encode_image, load_settings, ROOT


def test_hard_synthetic_payload_recovers_exact_bytes():
    text = 'name: SYNTHETIC TEST ONLY|id: 0000000000|data: '+'ABCDEFGHIJ'*20
    barcode = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.PDF417)
    rgb = cv2.cvtColor(np.asarray(barcode.to_image(scale=8)), cv2.COLOR_GRAY2RGB)
    profile = load_settings(ROOT / 'degradation.toml')['profiles']['hard']
    degraded, _ = degrade(rgb, profile, 42)
    image = cv2.imdecode(np.frombuffer(encode_image(degraded, profile, 'jpg'), np.uint8), cv2.IMREAD_COLOR)
    records = scan(image, load_config()['processing'])
    assert records
    assert base64.b64decode(records[0]['raw_bytes_base64']) == text.encode()


def test_measured_skew_and_binarization():
    image = np.full((400, 700), 235, np.uint8)
    for y in (70, 180, 300):
        cv2.line(image, (50, y), (650, y), 30, 3)
    skewed = rotate(image, 8)
    assert abs(estimate_skew(skewed)+8) < 1
    normal = normalize_lighting(skewed)
    assert normal.shape == skewed.shape and normal.dtype == np.uint8
    assert set(np.unique(sauvola(normal))) <= {0, 255}


def test_camera_budget_and_cancellation():
    image = np.full((300, 500, 3), 255, np.uint8)
    config = dict(load_config()['processing'], max_seconds=0.000001)
    stages = []
    assert scan(image, config, on_stage=lambda *args: stages.append(args)) == []
    assert not stages
    assert scan(image, load_config()['processing'], cancelled=lambda: True) == []
    with pytest.raises(ValueError):
        scan(np.zeros((0, 0, 3), np.uint8), config)


def test_optional_local_medium_fixture():
    source = ROOT / 'native_raw_img' / 'IMG_1456.PNG'
    paths = list((ROOT / 'low_img').rglob('IMG_1456_*medium*.jpg'))
    if not source.exists() or not paths:
        pytest.skip('Private local regression fixture not distributed')
    config = load_config()['processing']
    expected = {r['sha256'] for r in scan(load_image(source), config)}
    records = scan(load_image(paths[0]), config)
    assert records and {r['sha256'] for r in records} == expected
