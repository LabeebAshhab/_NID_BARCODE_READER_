import cv2
import numpy as np
import zxingcpp

from nid_scanner.config import load_config
from nid_scanner.detect import detect_regions, enhance, focus_measure
from nid_scanner.pipeline import scan


def _barcode(text, size=(360, 120)):
    barcode = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.PDF417)
    return cv2.resize(np.asarray(barcode.to_image()), size, interpolation=cv2.INTER_NEAREST)


def test_focus_measure_ranks_sharp_above_blurred():
    sharp = _barcode('FOCUS TEST 123456')
    blurred = cv2.GaussianBlur(sharp, (0, 0), 4.0)
    assert focus_measure(sharp) > focus_measure(blurred) * 5


def test_enhance_preserves_shape_and_dtype():
    gray = np.clip(_barcode('ENHANCE 987') * 0.5, 0, 255).astype(np.uint8)
    result = enhance(gray)
    assert result.shape == gray.shape and result.dtype == np.uint8


def test_detection_locates_barcode_region():
    scene = np.full((500, 800), 180, np.uint8)
    scene[80:200, 220:580] = _barcode('LOCATE ME 4570')
    stages = list(detect_regions(cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR), load_config()['processing']))
    assert stages
    assert any('Detected barcode' in stage for stage, _ in stages)


def test_multiple_cards_reads_the_in_focus_one():
    """A blurred card in hand must not win over a clear card on the desk."""
    sharp = _barcode('CARD ON TABLE SHARP 111')
    blurred = cv2.GaussianBlur(_barcode('CARD IN HAND BLUR 999'), (0, 0), 4.5)
    scene = np.full((600, 900), 180, np.uint8)
    scene[60:180, 60:420] = sharp
    scene[380:500, 300:660] = blurred
    records = scan(cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR), load_config()['processing'], 'desk')
    assert records and records[0]['raw_text'] == 'CARD ON TABLE SHARP 111'
    assert records[0]['stage'].startswith('Detected barcode 1')


def test_detection_disabled_still_reads_via_fallback():
    scene = np.full((400, 700), 180, np.uint8)
    scene[110:230, 120:480] = _barcode('FALLBACK 222')
    config = dict(load_config()['processing'], detect=False)
    records = scan(cv2.cvtColor(scene, cv2.COLOR_GRAY2BGR), config, 'fallback')
    assert records and records[0]['raw_text'] == 'FALLBACK 222'
    assert not records[0]['stage'].startswith('Detected barcode')
