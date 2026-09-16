"""Run with python app.py. All Tk operations stay on the main thread."""
import argparse
import ctypes
import json
import queue
import threading
import time
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageTk

from nid_scanner.config import load_config
from nid_scanner.pipeline import load_image, scan
from nid_scanner.storage import Exporter
from nid_scanner.theme import apply_theme


def enable_high_dpi():
    """Ask Windows to render Tk at native monitor resolution before creating Tk."""
    if sys.platform == "win32":
        try:
            if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
        except (AttributeError, OSError):
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


class ScannerApp:
    def __init__(self, root, config):
        self.root, self.config = root, config
        self.exporter = Exporter(config["output"])
        self.events = queue.Queue(maxsize=12)
        self.stop = threading.Event()
        self.worker = None
        self.records = []
        self.history_keys = set()
        self.latest_frame = None
        self.preview_frames = {}
        self.resize_jobs = {}
        root.title("NID Card Reader")
        root.geometry("800x800")
        root.minsize(1000, 720)
        if sys.platform == "win32":
            root.state("zoomed")
        self.colors = apply_theme(root)
        main = ttk.Frame(root, padding=(28, 22, 28, 14))
        main.pack(fill="both", expand=True)
        header = ttk.Frame(main)
        header.pack(fill="x", pady=(0, 20))
        brand = ttk.Frame(header)
        brand.pack(side="left")
        ttk.Label(brand, text="IDENTITY WORKSPACE", style="Eyebrow.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(brand, text="NID Card Reader", style="Title.TLabel").pack(anchor="w")
        ttk.Label(brand, text="import and camera both can be used", style="Muted.TLabel").pack(anchor="w", pady=(3, 0))
        ttk.Label(header, text="LOCAL PROCESSING", style="Badge.TLabel").pack(side="right", anchor="n", pady=10)
        action_card = self.card(main)
        action_card.pack(fill="x", pady=(0, 14))
        toolbar = ttk.Frame(action_card, style="Card.TFrame", padding=(16, 12))
        toolbar.pack(fill="x")
        self.open_button = ttk.Button(toolbar, text="Import image", style="Accent.TButton", command=self.open_image)
        self.open_button.pack(side="left", padx=(0, 8))
        self.camera_button = ttk.Button(toolbar, text="Start camera", command=self.start_camera)
        self.camera_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(toolbar, text="Stop scan", command=self.stop_scan, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.save_button = ttk.Button(toolbar, text="Export result", command=self.save_selected, state="disabled")
        self.save_button.pack(side="right")
        self.status = tk.StringVar(value="")
        self.status_label = ttk.Label(action_card, textvariable=self.status, style="CardMuted.TLabel", padding=(18, 0, 18, 10), wraplength=1100)
        self.status_label.pack(fill="x")
        self.progress = ttk.Progressbar(action_card, mode="indeterminate")
        self.progress.pack(fill="x")
        self.input_source = tk.StringVar(value="No image selected")
        body = ttk.Panedwindow(main, orient="vertical")
        body.pack(fill="both", expand=True)
        preview_section = ttk.Frame(body)
        body.add(preview_section, weight=3)
        previews = ttk.Frame(preview_section, height=360)
        previews.pack(fill="both", expand=True)
        previews.grid_propagate(False)
        previews.rowconfigure(0, weight=1)
        self.preview_labels = {}
        self.preview_meta = {}
        for col, (key, title, subtitle) in enumerate((("source", "Original image", "Your imported image or live camera feed"), ("processed", "Detection preview", "Image preparation and barcode boundaries"))):
            panel = self.card(previews)
            panel.grid(row=0, column=col, sticky="nsew", padx=(0, 8) if col == 0 else (8, 0))
            previews.columnconfigure(col, weight=1, uniform="preview")
            panel.pack_propagate(False)
            panel_header = ttk.Frame(panel, style="Card.TFrame", padding=(16, 12))
            panel_header.pack(fill="x")
            ttk.Label(panel_header, text=title, style="CardTitle.TLabel").pack(side="left")
            meta = tk.StringVar(value="01 / INPUT" if col == 0 else "02 / ANALYSIS")
            self.preview_meta[key] = meta
            ttk.Label(panel_header, textvariable=meta, style="CardMuted.TLabel").pack(side="right")
            ttk.Label(panel, text=subtitle, style="CardMuted.TLabel").pack(anchor="w", padx=16, pady=(0, 10))
            label = tk.Label(panel, bg=self.colors["preview"], fg=self.colors["muted"],
                             font=("Segoe UI", 12), text="Your image will appear here\n\nImport a photo or start the camera" if col == 0 else "Ready to find the details\n\nProcessing previews appear during a scan",
                             height=8, borderwidth=0, highlightthickness=0, cursor="hand2")
            label.pack(fill="both", expand=True, padx=10, pady=(0, 10))
            self.preview_labels[key] = label
            label.bind("<Configure>", lambda event, k=key: self.schedule_preview(k))
            label.bind("<Double-Button-1>", lambda event, k=key: self.open_full_resolution(k))
        self.stage = tk.StringVar(value="Waiting for your first scan")
        preview_footer = ttk.Frame(preview_section, padding=(2, 8))
        preview_footer.pack(side="bottom", fill="x", before=previews)
        ttk.Label(preview_footer, textvariable=self.stage, style="Muted.TLabel").pack(side="left")
        ttk.Label(preview_footer, text="Double-click to inspect full resolution", style="Muted.TLabel").pack(side="right")
        self.tabs = ttk.Notebook(body)
        footer = ttk.Frame(main, padding=(0, 12, 0, 0))
        footer.pack(side="bottom", fill="x", before=body)
        ttk.Label(footer, text="LabeebdexD.Ashhab", style="Muted.TLabel").pack(side="left")
        ttk.Label(footer, text="NID Card Reader  /  Local workspace", style="Muted.TLabel").pack(side="right")
        body.add(self.tabs, weight=2)
        results_tab, raw_tab, log_tab = [ttk.Frame(self.tabs, padding=16, style="Card.TFrame") for _ in range(3)]
        for panel, title in ((results_tab, "Decoded details"), (raw_tab, "Raw payload"), (log_tab, "Activity log")):
            self.tabs.add(panel, text=title)
        summary = ttk.Frame(results_tab, style="Card.TFrame")
        summary.pack(fill="x", pady=(0, 12))
        ttk.Label(summary, text="Scan overview", style="CardTitle.TLabel").pack(side="left")
        self.metrics = tk.StringVar(value="No result yet")
        ttk.Label(summary, textvariable=self.metrics, style="Metric.TLabel").pack(side="right")
        self.source_label = ttk.Label(results_tab, textvariable=self.input_source, style="CardMuted.TLabel", wraplength=1100)
        self.source_label.pack(fill="x", pady=(0, 10))
        self.selector = ttk.Combobox(results_tab, state="readonly")
        self.selector.pack(fill="x", pady=(0, 6))
        self.selector.bind("<<ComboboxSelected>>", lambda _: self.show_record())
        self.tree = ttk.Treeview(results_tab, columns=("field", "value"), show="headings")
        self.tree.heading("field", text="  FIELD", anchor="w")
        self.tree.heading("value", text="  DETAILS", anchor="w")
        self.tree.column("field", width=round(root.winfo_fpixels("2.4i")), stretch=False)
        self.tree.column("value", width=700)
        scrollbar = ttk.Scrollbar(results_tab, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("alternate", background="#F0F4EF")
        self.tree.tag_configure("payload", foreground=self.colors["accent"], font=("Segoe UI", 11, "bold"))
        self.raw = self.text_area(raw_tab)
        self.log = self.text_area(log_tab)
        main.bind("<Configure>", self.resize_text)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(40, self.poll)

    def card(self, parent):
        return tk.Frame(parent, background=self.colors["surface"], highlightbackground=self.colors["line"], highlightthickness=1, borderwidth=0)

    def resize_text(self, event):
        width = max(300, event.width-100)
        self.status_label.configure(wraplength=width)
        self.source_label.configure(wraplength=width)

    def text_area(self, panel):
        text = tk.Text(panel, wrap="word", font=("Consolas", 11), state="disabled", height=8,
                       bg=self.colors["surface"], fg=self.colors["ink"], relief="flat", borderwidth=0,
                       padx=14, pady=14, spacing1=4, spacing3=4, selectbackground=self.colors["soft"],
                       selectforeground=self.colors["ink"], highlightthickness=0)
        bar = ttk.Scrollbar(panel, command=text.yview)
        text.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        return text

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S") + "  " + text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 500:
            self.log.delete("1.0", "100.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def emit(self, kind, data):
        while not self.stop.is_set():
            try:
                self.events.put((kind, data), timeout=.1)
                return
            except queue.Full:
                continue

    def launch(self, target):
        if self.worker and self.worker.is_alive():
            return False
        # A new acquisition must never inherit a previous acquisition's events or data.
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                break
        self.clear_results()
        self.latest_frame = None
        self.preview_frames.clear()
        self.preview_meta["source"].set("01 / INPUT")
        self.preview_meta["processed"].set("02 / ANALYSIS")
        for label in self.preview_labels.values():
            label.configure(image="", text="Waiting for current image")
            label.image = None
        self.stage.set("Waiting for current input...")
        self.stop.clear()
        self.open_button.configure(state="disabled")
        self.camera_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.start(15)
        self.worker = threading.Thread(target=self.run_worker, args=(target,), daemon=True)
        self.worker.start()
        return True

    def clear_results(self):
        self.records.clear()
        self.history_keys.clear()
        self.selector.set("")
        self.selector["values"] = ()
        self.tree.delete(*self.tree.get_children())
        self.raw.configure(state="normal")
        self.raw.delete("1.0", "end")
        self.raw.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.metrics.set("No result yet")

    def run_worker(self, target):
        try:
            target()
        except Exception as exc:
            self.emit("error", f"{type(exc).__name__}: {exc}")

    def process(self, image, source):
        if not source.startswith("camera:"):
            self.emit("source", image)
        processing = dict(self.config["processing"])
        if source.startswith("camera:"):
            processing['max_seconds'] = self.config['camera'].get('max_scan_seconds', 2.0)
        records = scan(image, processing, source,
                       on_stage=lambda name, frame, attempt: self.emit("stage", (name, frame, attempt)),
                       cancelled=self.stop.is_set)
        if self.stop.is_set():
            return
        if records:
            self.emit("results", records)
        else:
            self.emit("no_result", "No barcode decoded from the current input within the search limits. Try a closer, sharper image without glare; severely lost bar detail may need a new capture.")

    def open_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"), ("All files", "*.*")])
        if path:
            self.input_source.set(f"Imported image: {path}")
            self.status.set("Loading image...")
            self.launch(lambda: self.process(load_image(path), path))

    def start_camera(self):
        self.input_source.set(f"Live camera: {self.config['camera']['index']}")
        self.status.set("Opening camera...")
        self.launch(self.camera_loop)

    def camera_loop(self):
        c = self.config["camera"]
        capture = cv2.VideoCapture(c["index"])
        try:
            if not capture.isOpened():
                raise RuntimeError("Cannot open camera. Check its index, Windows camera permissions, and other camera apps.")
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, c["width"])
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, c["height"])
            capture_stop = threading.Event()
            capture_error = []
            def acquire():
                while not self.stop.is_set() and not capture_stop.is_set():
                    ok, frame = capture.read()
                    if self.stop.is_set() or capture_stop.is_set():
                        return
                    if not ok:
                        capture_error.append("Camera stopped returning frames")
                        return
                    self.latest_frame = frame
                    capture_stop.wait(.03)
            reader = threading.Thread(target=acquire, daemon=True)
            reader.start()
            while not self.stop.is_set():
                if capture_error:
                    raise RuntimeError(capture_error[0])
                frame = self.latest_frame
                if frame is not None:
                    self.process(frame.copy(), f"camera:{c['index']}")
                self.stop.wait(c["scan_interval_seconds"])
        finally:
            if "capture_stop" in locals():
                capture_stop.set()
                reader.join(timeout=2)
            capture.release()
            self.latest_frame = None

    def display_image(self, key, frame):
        self.preview_frames[key] = frame
        self.preview_meta[key].set(f"{frame.shape[1]:,} × {frame.shape[0]:,} px")
        self.render_preview(key)

    def schedule_preview(self, key):
        if key in self.resize_jobs:
            self.root.after_cancel(self.resize_jobs[key])
        self.resize_jobs[key] = self.root.after(80, lambda: self.render_preview(key))

    def render_preview(self, key):
        self.resize_jobs.pop(key, None)
        frame = self.preview_frames.get(key)
        if frame is None:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB if frame.ndim == 2 else cv2.COLOR_BGR2RGB)
        image = Image.fromarray(rgb)
        label = self.preview_labels[key]
        image.thumbnail((max(1, label.winfo_width()-8), max(1, label.winfo_height()-8)), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        label.configure(image=photo, text="")
        label.image = photo

    def open_full_resolution(self, key):
        frame = self.preview_frames.get(key)
        if frame is None:
            return
        window = tk.Toplevel(self.root)
        window.title(f"{key.title()} - full resolution (1 image pixel per display pixel)")
        window.geometry("1100x750")
        window.rowconfigure(0, weight=1)
        window.columnconfigure(0, weight=1)
        canvas = tk.Canvas(window, background=self.colors["preview"], highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        horizontal = ttk.Scrollbar(window, orient="horizontal", command=canvas.xview)
        vertical = ttk.Scrollbar(window, orient="vertical", command=canvas.yview)
        horizontal.grid(row=1, column=0, sticky="ew")
        vertical.grid(row=0, column=1, sticky="ns")
        canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB if frame.ndim == 2 else cv2.COLOR_BGR2RGB)
        canvas.image = ImageTk.PhotoImage(Image.fromarray(rgb))
        canvas.create_image(0, 0, anchor="nw", image=canvas.image)
        canvas.configure(scrollregion=(0, 0, frame.shape[1], frame.shape[0]))

    def poll(self):
        if self.latest_frame is not None:
            self.display_image("source", self.latest_frame)
        for _ in range(16):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "source":
                self.display_image("source", data)
            elif kind == "stage":
                name, frame, attempt = data
                self.display_image("processed", frame)
                self.stage.set(f"Attempt {attempt}  /  {name}")
                self.write_log(f"Attempt {attempt}: {name}")
            elif kind == "results":
                self.accept_results(data)
            elif kind == "error":
                self.clear_results()
                self.status.set(data)
                self.write_log(data)
                messagebox.showerror("Scan failed", data)
            elif kind == "no_result":
                self.clear_results()
                self.status.set(data)
            else:
                self.status.set(data)
        if self.worker and not self.worker.is_alive() and self.events.empty():
            self.worker = None
            self.progress.stop()
            self.open_button.configure(state="normal")
            self.camera_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            if self.stop.is_set():
                self.status.set("Stopped.")
        self.root.after(40, self.poll)

    def accept_results(self, records):
        for record in records:
            key = (record["format"], record["sha256"])
            if self.config["output"]["deduplicate"] and key in self.history_keys:
                # Refresh the displayed record to the current frame, even if export is deduplicated.
                index = next(i for i, old in enumerate(self.records)
                             if (old["format"], old["sha256"]) == key)
                self.records[index] = record
                values = list(self.selector["values"])
                values[index] = f"{index+1}. {record['format']} | {record['source']} | {record['timestamp_utc']}"
                self.selector["values"] = values
                self.selector.current(index)
                self.show_record()
                self.status.set("Current input decoded again; duplicate export suppressed.")
                continue
            self.history_keys.add(key)
            self.records.append(record)
            # Bound UI memory during long camera sessions.
            self.records = self.records[-200:]
            self.history_keys = {(r["format"], r["sha256"]) for r in self.records}
            self.selector["values"] = [f"{i+1}. {r['format']} | {r['source']} | {r['timestamp_utc']}" for i, r in enumerate(self.records)]
            self.selector.current(len(self.records)-1)
            self.show_record()
            self.status.set(f"Decoded {record['format']} in {record['elapsed_ms']} ms.")
            if self.config["output"]["auto_save"]:
                self.save_record(record)

    def show_record(self):
        index = self.selector.current()
        if index < 0:
            return
        record = self.records[index]
        self.metrics.set(f"{record['format']}   /   {record['byte_count']} bytes   /   {record['elapsed_ms']} ms")
        self.save_button.configure(state="normal")
        self.tree.delete(*self.tree.get_children())
        for key, value in record["parsed"]["fields"].items():
            self.tree.insert("", "end", values=(f"Payload / {key}", json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)))
        self.tree.insert("", "end", values=("Parser status", record["parsed"]["status"]))
        for key in ("source", "format", "byte_count", "timestamp_utc", "stage", "orientation", "elapsed_ms", "sha256"):
            self.tree.insert("", "end", values=(key.replace("_", " ").title(), record[key]))
        for row, item in enumerate(self.tree.get_children()):
            tags = ["alternate"] if row % 2 else []
            if self.tree.item(item, "values")[0].startswith("Payload /"):
                tags.append("payload")
            self.tree.item(item, tags=tags)
        self.raw.configure(state="normal")
        self.raw.delete("1.0", "end")
        self.raw.insert("end", f"DECODED TEXT (ZXing display representation)\n{record['raw_text']}\n\nLOSSLESS BYTES (Base64)\n{record['raw_bytes_base64']}")
        self.raw.configure(state="disabled")

    def save_record(self, record):
        try:
            paths = self.exporter.save(record)
            self.status.set(f"Saved {len(paths)} file(s) to {self.config['output']['directory']}" if paths else "This payload was already saved in this session.")
            for path in paths:
                self.write_log(f"Saved: {path}")
        except OSError as exc:
            self.status.set("Export failed. Result remains available; use Save selected result to retry.")
            messagebox.showerror("Export failed", str(exc))

    def save_selected(self):
        index = self.selector.current()
        if index >= 0:
            self.save_record(self.records[index])
        else:
            self.status.set("Decode an image before saving a result.")

    def stop_scan(self):
        self.stop.set()
        self.status.set("Stopping after the current decoding operation...")

    def close(self):
        self.stop.set()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Path to TOML configuration")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Configuration error: {exc}\n")
    enable_high_dpi()
    root = tk.Tk()
    ScannerApp(root, config)
    root.mainloop()


if __name__ == "__main__":
    main()
