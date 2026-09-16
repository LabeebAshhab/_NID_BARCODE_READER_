"""Developer smoke check: exercise widgets and background decoding without a camera."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk
from PIL import ImageGrab
from app import ScannerApp, enable_high_dpi
from nid_scanner.config import load_config
from nid_scanner.pipeline import load_image


with tempfile.TemporaryDirectory() as directory:
    config = load_config()
    config['output']['directory'] = directory
    enable_high_dpi()
    root = tk.Tk()
    app = ScannerApp(root, config)
    outcome = []
    def start():
        app.input_source.set('Synthetic demo image')
        app.launch(lambda: app.process(load_image(ROOT / 'examples/synthetic_pdf417.png'), 'synthetic-demo'))
        root.after(100, check)
    def check():
        if app.worker is not None:
            root.after(100, check)
            return
        try:
            assert app.records, 'No result reached the UI'
            assert len(list(Path(directory).glob('*.json'))) == 1
            assert len(list(Path(directory).glob('*.csv'))) == 1
            assert app.tree.get_children(), 'Structured fields are empty'
            assert app.preview_labels['processed'].image
            target = ROOT / 'tmp' / 'ui-smoke.png'
            target.parent.mkdir(exist_ok=True)
            root.update_idletasks()
            ImageGrab.grab(window=root.winfo_id()).save(target)
            outcome.append(True)
        finally:
            root.destroy()
    root.after(200, start)
    root.after(15000, root.destroy)
    root.mainloop()
    assert outcome, 'UI smoke test did not complete'
    print('UI smoke passed: worker, previews, structured data, automatic CSV/JSON export')
