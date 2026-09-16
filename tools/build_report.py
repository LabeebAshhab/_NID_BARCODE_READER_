"""Build the pipeline decision report. Run from any working directory."""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output" / "pdf" / "pipeline_alternatives.pdf"


def build():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle", fontName="Helvetica-Bold", fontSize=30, leading=35, textColor=colors.HexColor("#14263d"), spaceAfter=18))
    styles.add(ParagraphStyle(name="Deck", fontSize=13, leading=19, textColor=colors.HexColor("#476078"), spaceAfter=14))
    styles["BodyText"].fontSize = 10
    styles["BodyText"].leading = 15
    styles["BodyText"].spaceAfter = 9
    styles["Heading2"].textColor = colors.HexColor("#126d76")
    styles.add(ParagraphStyle(name="Cell", fontSize=9, leading=13, alignment=TA_LEFT))
    story = []
    def p(text, style="BodyText"):
        story.append(Paragraph(text, styles[style]))
    def heading(text):
        p(text, "Heading2")
    p("ENGINEERING DECISION NOTE / 16 SEPTEMBER 2026", "Deck")
    p("NID Barcode Studio", "CoverTitle")
    p("A local pipeline for image preparation, barcode decoding and lossless export", "Deck")
    heading("Recommendation")
    p("Use <b>OpenCV + ZXing-C++ Python bindings + Tkinter</b>. OpenCV prepares the image; ZXing reads the barcode; Tkinter shows live input, processing candidates and results. This matches the requested ZXing workflow without introducing a Java runtime.")
    p("ZXing-C++ explicitly supports PDF417 and several other barcode families [1, 2]. OpenCV's dedicated barcode decoder documents EAN/UPC retail support, so it is not a PDF417 replacement [3]. This establishes format suitability, not a measured accuracy advantage on Bangladeshi NIDs.")
    heading("What the project implements")
    p("Image files and camera input; EXIF orientation handling; grayscale and size normalization; heuristic card cropping and perspective correction; barcode-region proposals; denoising, contrast enhancement, thresholding and rotation candidates; structured result display; exact-byte preservation in CSV and JSON.")
    heading("Evidence boundary")
    p("No real NID sample images or authoritative NID payload schema were supplied. The software is designed to attempt PDF417, QR Code, Data Matrix and Code 128. It does not assert that every Bangladesh card generation uses the same format or field layout. Synthetic tests establish software behavior, not production read rates.")
    p("A successful barcode read is not identity or document authentication. Explicit payload labels are displayed as unverified fields. Opaque or encrypted content remains raw; decoding does not decrypt it.")
    heading("Local by design")
    p("No runtime network service or cloud upload is used. Images remain in memory unless already present as input files. Exported records contain plaintext payloads and source paths, so the output directory should be protected according to the operator's data-handling requirements.")
    story.append(PageBreak())
    p("How the pipeline works", "CoverTitle")
    rows = [["Stage", "Purpose and limitation"],
            ["1. Acquire & normalize", "Apply EXIF orientation to files, cap the processing dimension and convert to grayscale. Very large files are rejected before conversion."],
            ["2. Early decode", "Try the full frame first. Native rotation, downscale and inversion searches handle common variations without unnecessary filtering."],
            ["3. Geometry", "Try a large convex card boundary and perspective warp, then gradient-based barcode crops with margins. Keep the full-frame fallback because proposals are heuristic."],
            ["4. Recovery candidates", "Try denoising, CLAHE, Otsu/adaptive thresholds, enlargement and +/-12 degree rotations. Native right-angle rotation search remains enabled."],
            ["5. Decode & inspect", "Stop at the first successful candidate. Return its detected symbols and draw their bounds in that candidate's coordinate system."],
            ["6. Parse & export", "Parse explicit labels only. Preserve raw bytes as Base64 and save matching UUID-named CSV and JSON files, including scan metadata."]]
    table = Table([[Paragraph(cell, styles["Cell"]) for cell in row] for row in rows], colWidths=[125, 370], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dceef0")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f8")]), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story.append(table)
    story.append(Spacer(1, 12))
    heading("Realtime behavior")
    p("Camera acquisition and barcode processing use background threads; Tk draws the latest captured frame and candidate previews. Capture can continue while decoding is busy. Processing cadence depends on resolution, CPU and image quality. Stop takes effect between native decode operations; it is not a hard realtime interrupt.")
    heading("Lossless does not mean human-readable")
    p("Base64 preserves the exact bytes ZXing returns, including binary content. Display text can reflect ZXing's character-set handling. JSON is UTF-8; CSV uses a BOM and spreadsheet-safe text escaping. CSV nested values are JSON strings. Each file is atomic; a failure between formats may leave one member of a pair until retry.")
    story.append(PageBreak())
    p("Alternatives & tradeoffs", "CoverTitle")
    heading("Java ZXing")
    p("The original ZXing project is a viable alternative with broad barcode support [5]. It brings Java deployment and Python integration work. Choose it when an existing Java platform or a benchmark justifies that integration; this Python desktop project benefits from direct native bindings instead.")
    heading("OpenCV-only decoding")
    p("Suitable for the barcode families its decoder supports, and for separate QR workflows. Its documented retail-format decoder is not a general PDF417 engine [3]. Retain OpenCV for preprocessing rather than treating it as a replacement for ZXing in this application.")
    heading("ZBar / pyzbar")
    p("pyzbar documents a focus on one-dimensional barcodes and QR codes [4]. Do not assume PDF417 suitability from the existence of an API constant. Establish actual runtime support and benchmark the target format before considering it for this NID workflow.")
    heading("Commercial PDF417 SDK")
    p("A licensed SDK is a possible second-stage evaluation if the open-source baseline misses required targets on difficult images. Verify its current format support, licensing, offline operation and data flow before adoption. No vendor accuracy claim or price has been relied on here; no commercial dependency is included.")
    heading("OCR or a learned detector")
    p("OCR may separately recover visible printed fields, but cannot substitute for barcode byte recovery or authenticate the document. A learned barcode locator may improve crop proposals on cluttered scenes; it adds model assets, training data and evaluation work. Neither is needed to establish the initial baseline.")
    heading("Decision rule")
    p("Keep ZXing-C++ unless a representative evaluation shows that another engine materially improves exact-payload recovery, latency or operational cost. Preprocessing is not universally helpful: thin bars may be damaged by filters, which is why the original grayscale candidate is tried first.")
    story.append(PageBreak())
    p("Validation & next decisions", "CoverTitle")
    heading("Automated checks included")
    p("The test suite covers synthetic PDF417 codes at four right-angle rotations, a combined blur/noise/skew case, byte-preserving binary decoding, EXIF rotation, blank inputs, cancellation, crop and filter candidates, conservative parsing, CSV/JSON round-trip, deduplication and export failure/retry. These cases are reproducible and contain no real identity data.")
    heading("A practical field benchmark")
    p("Build a consented, access-controlled sample set spanning relevant card generations, phones/cameras, distance, glare, rotation, perspective and wear. Maintain trusted expected barcode bytes where available. Separate tuning samples from a held-out evaluation set.")
    p("Measure exact-byte success rate, false decodes, no-read rate and median/95th-percentile latency. Report results by image condition and card group. Compare the baseline against preprocessing ablations and any alternative SDK under identical input and hardware conditions. Do not report a single accuracy number without the dataset definition.")
    heading("Known limits before deployment")
    p("No guaranteed recovery from glare, missing bars, severe blur or extreme perspective. No validated official field mapping, signature validation, decryption or government lookup. Crops and skew corrections are heuristics. Session deduplication is not persistent. Real camera hardware behavior and real NID decoding need operator validation.")
    heading("Primary references")
    references = [
        ("1. ZXing-C++ project and supported formats", "https://github.com/zxing-cpp/zxing-cpp"),
        ("2. Official Python bindings and examples", "https://github.com/zxing-cpp/zxing-cpp/tree/master/wrappers/python"),
        ("3. OpenCV barcode recognition tutorial", "https://docs.opencv.org/5.0/tutorials/objdetect/barcode_detect_and_decode/barcode_detect_and_decode.html"),
        ("4. pyzbar project and documented scope", "https://github.com/NaturalHistoryMuseum/pyzbar"),
        ("5. Original Java ZXing project", "https://github.com/zxing/zxing"),
    ]
    for label, url in references:
        p(f'<b>{label}</b><br/><link href="{url}" color="#126d76">{url}</link>')
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#d4dee6"))
        canvas.line(50, 43, A4[0]-50, 43)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#476078"))
        canvas.drawString(50, 29, "NID Barcode Studio / Pipeline decision report")
        canvas.drawRightString(A4[0]-50, 29, str(doc.page))
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=50, leftMargin=50, topMargin=48, bottomMargin=58, title="NID Barcode Studio - Pipeline and Alternatives", author="NID Barcode Studio")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    build()
