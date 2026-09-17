import base64
import csv
import json

import cv2
import numpy as np
import pytest
import zxingcpp

from nid_scanner.config import load_config
from nid_scanner.payload import parse_payload
from nid_scanner.pipeline import scan, variants, card_crop, load_image
from nid_scanner.storage import Exporter


def barcode(text="name: SYNTHETIC TEST\nnid: 0000000000"):
    code = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.PDF417)
    return cv2.cvtColor(np.asarray(code.to_image(scale=3)), cv2.COLOR_GRAY2BGR)


@pytest.mark.parametrize("rotation", [0, 1, 2, 3])
def test_pdf417_rotations_and_exact_bytes(rotation):
    text = "name: SYNTHETIC TEST\nnid: 0000000000"
    image = np.ascontiguousarray(np.rot90(barcode(text), rotation))
    result = scan(image, load_config()["processing"])[0]
    assert base64.b64decode(result["raw_bytes_base64"]) == text.encode()
    assert result["parsed"]["fields"]["nid"] == "0000000000"


def test_blur_noise_and_skew():
    image = barcode()
    image = cv2.copyMakeBorder(image, 100, 100, 100, 100, cv2.BORDER_CONSTANT, value=(255,)*3)
    h, w = image.shape[:2]
    image = cv2.warpAffine(image, cv2.getRotationMatrix2D((w/2, h/2), 9, 1), (w, h), borderValue=(255,)*3)
    image = cv2.GaussianBlur(image, (3, 3), .5)
    noise = np.random.default_rng(42).normal(0, 3, image.shape)
    image = np.clip(image.astype(float)+noise, 0, 255).astype(np.uint8)
    assert scan(image, load_config()["processing"])


def test_empty_and_cancellation():
    image = np.full((300, 500, 3), 255, np.uint8)
    assert scan(image, load_config()["processing"]) == []
    assert scan(barcode(), load_config()["processing"], cancelled=lambda: True) == []


def test_variants_and_card_rectification():
    image = np.full((650, 950, 3), 40, np.uint8)
    cv2.fillConvexPoly(image, np.int32([[90, 90], [830, 130], [790, 560], [120, 530]]), (240,)*3)
    assert card_crop(image) is not None
    names = [name for name, _ in variants(image, load_config()["processing"])]
    assert any("denoised" in n for n in names)
    assert any("Perspective" in n for n in names)
    assert any("adaptive" in n for n in names)


def test_payload_parser_is_conservative():
    assert parse_payload("1234567890")['fields'] == {}
    assert parse_payload("<name>A</name><name>B</name>")['fields']['name'] == ['A', 'B']
    assert parse_payload('{"name":"পরীক্ষা"}')['fields']['name'] == 'পরীক্ষা'


def test_smart_nid_delimited_payload_is_parsed():
    """Newer Smart/chip NID cards use GS/RS-delimited fields, not XML tags."""
    raw = b"<]?\x1eNMMd. Ruhul Amin\x1dNW3268483744\x1dBR19850121\x1dDT20151130\x1dPK13\x04"
    parsed = parse_payload(raw.decode("latin-1"), raw)
    assert parsed['status'] == "Smart NID fields (unverified)"
    fields = parsed['fields']
    assert fields['Name'] == "Md. Ruhul Amin"
    assert fields['Date of birth'] == "19850121"
    assert fields['Issue date'] == "20151130"
    assert fields['PK'] == "13"          # unknown codes surface under their own code
    # Old XML-tag cards must still parse when raw bytes carry no separators.
    old = "<pin>123</pin><name>X Y</name>"
    assert parse_payload(old, old.encode())['fields']['name'] == "X Y"


def test_csv_json_lossless_and_dedup(tmp_path):
    config = load_config()["output"]
    config["directory"] = str(tmp_path)
    record = scan(barcode('=1+1'), load_config()["processing"])[0]
    exporter = Exporter(config)
    assert len(exporter.save(record)) == 2
    assert exporter.save(record) == []
    saved = json.loads(next(tmp_path.glob('*.json')).read_text(encoding='utf-8'))
    with next(tmp_path.glob('*.csv')).open(encoding='utf-8-sig', newline='') as stream:
        row = next(csv.DictReader(stream))
    assert row['raw_text'].startswith("'")
    assert base64.b64decode(row['raw_bytes_base64']) == b'=1+1'
    assert saved == record


def test_binary_payload_retained():
    raw = bytes([0, 1, 2, 128, 255, 65])
    code = zxingcpp.create_barcode(raw, zxingcpp.BarcodeFormat.PDF417)
    image = cv2.cvtColor(np.asarray(code.to_image(scale=3)), cv2.COLOR_GRAY2BGR)
    record = scan(image, load_config()['processing'])[0]
    assert base64.b64decode(record['raw_bytes_base64']) == raw


def test_image_loading_exif(tmp_path):
    from PIL import Image
    path = tmp_path / 'rotated.jpg'
    image = Image.new('RGB', (80, 40))
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    assert load_image(path).shape[:2] == (80, 40)


def test_export_failure_can_retry(tmp_path, monkeypatch):
    import nid_scanner.storage as storage
    config = load_config()['output']
    config['directory'] = str(tmp_path)
    exporter = Exporter(config)
    record = scan(barcode(), load_config()['processing'])[0]
    original = storage.os.replace
    def fail(*args):
        raise OSError('simulated disk failure')
    monkeypatch.setattr(storage.os, 'replace', fail)
    with pytest.raises(OSError):
        exporter.save(record)
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(storage.os, 'replace', original)
    assert len(exporter.save(record)) == 2
