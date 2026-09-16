"""Capture the real UI using generated fictional barcode content (Windows only)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk
import cv2
import numpy as np
from PIL import ImageGrab
import zxingcpp
from app import ScannerApp, enable_high_dpi
from nid_scanner.config import load_config


def main():
    if sys.platform != 'win32':
        raise SystemExit('Window-only screenshot capture requires Windows.')
    config = load_config()
    config['output']['auto_save'] = False
    enable_high_dpi()
    root = tk.Tk()
    app = ScannerApp(root, config)
    folder = ROOT / 'docs' / 'images'
    folder.mkdir(parents=True, exist_ok=True)
    captured = []
    payload = 'name: SYNTHETIC TEST\nnid: 0000000000\ndob: 2000-01-01'
    code = zxingcpp.create_barcode(payload, zxingcpp.BarcodeFormat.PDF417)
    frame = cv2.cvtColor(np.asarray(code.to_image(scale=6)), cv2.COLOR_GRAY2BGR)

    def capture(name):
        root.update_idletasks()
        ImageGrab.grab(window=root.winfo_id()).save(folder / name)
        captured.append(name)

    def finish():
        capture('ui-raw-payload.png')
        root.destroy()

    def overview():
        capture('ui-overview.png')
        app.tabs.select(1)
        root.after(300, finish)

    def wait_for_scan():
        if app.worker is not None:
            root.after(100, wait_for_scan)
            return
        assert len(app.records) == 1
        assert app.records[0]['parsed']['fields']['name'] == 'SYNTHETIC TEST'
        app.status.set('Synthetic demo decoded successfully. Ready to export as CSV or JSON.')
        root.after(300, overview)

    def start():
        app.input_source.set('Synthetic example / fictional data only')
        app.launch(lambda: app.process(frame, 'synthetic-demo'))
        root.after(100, wait_for_scan)

    root.after(300, start)
    root.after(20000, root.destroy)
    root.mainloop()
    if len(captured) != 2:
        raise SystemExit('Screenshot capture did not complete.')
    print('Created README screenshots with fictional data only: '+', '.join(captured))


if __name__ == '__main__':
    main()
