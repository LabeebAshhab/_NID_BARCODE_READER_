# Image degradation pipeline

This is a separate tool for creating challenging test images. It does not import, call or modify the NID reader, its configuration, preprocessing or exports. It uses the existing OpenCV, NumPy and Pillow requirements.

## Run

Put your high-quality images in `native_raw_img`, then run from the project folder:

```powershell
.\.venv\Scripts\python.exe degrade_images.py
```

Each source produces **mild**, **medium** and **hard** versions. Results go to `low_img/<unique-run-id>/`. Every run gets its own folder, so previous outputs and original images are preserved. Nested input folders are supported. JPG, JPEG, PNG, BMP, TIFF and WebP files are accepted; only the first frame/page is processed for multi-frame formats. EXIF orientation is applied before degradation.

One image or one severity:

```powershell
.\.venv\Scripts\python.exe degrade_images.py --image "native_raw_img\example.jpg"
.\.venv\Scripts\python.exe degrade_images.py --profile hard
.\.venv\Scripts\python.exe degrade_images.py --profile medium --seed 123
```

Open any generated image using **Import image** in the original reader to see how well it decodes. This tool does not run the decoder automatically or guarantee a no-read result. Difficulty depends on the barcode's size, print quality, error correction and the reader. Some hard images may still decode; some mild images may not.

## Effects

The tool combines resolution loss, slight perspective distortion, rotation, defocus blur, horizontal/vertical motion blur, lower contrast, exposure changes, directional shadow, simulated glare, sensor noise and JPEG compression. Effects cover the whole image; the tool does not locate or replace barcode content. Rotation expands the canvas to avoid intentionally cutting off card corners. Small source images can become unreadable quickly.

Edit `degradation.toml` to adjust paths, severity profiles, variants per profile, seed or output format (`jpg`/`png`). PNG output retains the simulated JPEG artifacts in a lossless container. Large images are reduced to a maximum working dimension of 3000 pixels by default to bound processing memory; outputs are generated from that working image. Original files are never resized or rewritten.

Each run's `manifest.json` records source/output filenames and hashes, severity parameters, sampled random settings, original/working/output dimensions and errors. The same source contents, relative filename, profile, seed and library versions reproduce identical output bytes; a different run ID changes only the destination. This is not a calibrated benchmark of real camera artifacts.

Unreadable/corrupt inputs are reported and processing continues. Exit codes: `0` for success (including an empty folder), `1` for failed inputs, `2` for invalid configuration or setup errors. A partial run can retain successfully generated outputs. Input/output folders must not overlap. Both folders are excluded from Git because they can contain identity images.
