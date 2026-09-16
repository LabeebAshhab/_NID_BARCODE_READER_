"""Regression coverage for camera -> import transitions using real synthetic decoding."""
import time
import tkinter as tk

import cv2
import numpy as np
import pytest
import zxingcpp

from app import ScannerApp
from nid_scanner.config import load_config


def make_image(text):
    barcode = zxingcpp.create_barcode(text, zxingcpp.BarcodeFormat.PDF417)
    return cv2.cvtColor(np.asarray(barcode.to_image(scale=3)), cv2.COLOR_GRAY2BGR)


def finish(root, app):
    deadline = time.monotonic() + 10
    while app.worker is not None and time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    assert app.worker is None, "Background scan did not finish"
    root.update()


def test_camera_then_import_never_reuses_old_results(tmp_path, monkeypatch):
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk display unavailable")
    root.withdraw()
    config = load_config()
    config['output']['directory'] = str(tmp_path / 'exports')
    app = ScannerApp(root, config)
    errors = []
    monkeypatch.setattr('app.messagebox.showerror', lambda *args: errors.append(args))
    try:
        image_a = make_image('name: CAMERA A')
        app.launch(lambda: app.process(image_a, 'camera:0'))
        finish(root, app)
        assert app.records[0]['parsed']['fields']['name'] == 'CAMERA A'

        blank = tmp_path / 'blank.png'
        cv2.imwrite(str(blank), np.full((300, 500, 3), 255, np.uint8))
        monkeypatch.setattr('app.filedialog.askopenfilename', lambda **kwargs: str(blank))
        app.open_image()
        assert app.records == []
        assert not app.tree.get_children()
        assert app.raw.get('1.0', 'end').strip() == ''
        finish(root, app)
        assert app.records == []
        assert 'No barcode decoded' in app.status.get()
        assert str(app.save_button['state']) == 'disabled'

        imported = tmp_path / 'different.png'
        cv2.imwrite(str(imported), make_image('name: IMPORT B'))
        monkeypatch.setattr('app.filedialog.askopenfilename', lambda **kwargs: str(imported))
        app.open_image()
        finish(root, app)
        assert len(app.records) == 1
        assert app.records[0]['parsed']['fields']['name'] == 'IMPORT B'
        assert app.records[0]['source'] == str(imported)
        assert 'CAMERA A' not in app.raw.get('1.0', 'end')

        same = tmp_path / 'same_as_camera.png'
        cv2.imwrite(str(same), image_a)
        monkeypatch.setattr('app.filedialog.askopenfilename', lambda **kwargs: str(same))
        app.open_image()
        finish(root, app)
        assert app.records[0]['source'] == str(same)
        assert app.records[0]['parsed']['fields']['name'] == 'CAMERA A'
        assert len(list((tmp_path / 'exports').glob('*.json'))) == 2

        app.events.put(('results', app.records.copy()))
        monkeypatch.setattr('app.filedialog.askopenfilename', lambda **kwargs: str(blank))
        app.open_image()
        finish(root, app)
        assert not app.records

        missing = tmp_path / 'missing.png'
        monkeypatch.setattr('app.filedialog.askopenfilename', lambda **kwargs: str(missing))
        app.open_image()
        finish(root, app)
        assert errors and not app.records
        assert not app.tree.get_children()
    finally:
        app.close()
