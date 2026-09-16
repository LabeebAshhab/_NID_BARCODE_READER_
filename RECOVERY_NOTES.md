# Reader recovery update

The main reader now includes a second recovery stage after the original fast path. The degradation tool, original images and generated variants are unchanged.

## Measured local results

Tested on the supplied `IMG_1456` original and its generated variants. Successful variant decodes were checked against the original's exact payload hash. Ground truth was used only for evaluation; the reader never looks up the original or reuses stored data.

| Input | Previous fast pipeline | Updated pipeline |
|---|---|---|
| Original | Decoded | Decoded |
| Mild | Decoded | Decoded, exact payload match |
| Medium | No read | Decoded, exact payload match |
| Hard | No read | Still no read |

The medium variant was recovered by measuring and correcting approximately 5.42 degrees of tilt. It decoded in about 0.85 seconds on this machine in the recorded benchmark; this is one sample, not a general performance claim.

The supplied hard variant remains unresolved. An additional offline search tested 4,950 combinations of geometry, scaling, filtering and thresholding and 576 deblurring candidates without a valid read. These exploratory sweeps are not run during normal scans. The hard degradation combines quarter-scale detail loss, blur, motion blur, noise, lighting changes and heavy JPEG compression. The observed failure is consistent with severe loss of narrow-bar detail, but the experiments do not prove that no decoder could ever recover it.

No software can guarantee decoding in every environment or from every damaged image. The app reports a no-read instead of substituting the original's payload. A higher-resolution synthetic barcode does survive the same hard profile and is covered by an exact-byte regression test; this does not imply the supplied hard NID image is recoverable.

## What changed

- Edge-based tilt estimation with expanded-canvas correction.
- Aligned full-frame and barcode-crop recovery candidates.
- Uneven-light normalization and contrast normalization.
- Additional scales and nearby rotation candidates.
- Unsharp masking, Sauvola and adaptive thresholds.
- Local-average, global-histogram and fixed-threshold ZXing modes.
- Separate image/camera time budgets and bounded recovery attempts.
- Explicit rejection of invalid image arrays and continued stale-result prevention.

Only valid ZXing decodes are returned. Restoration transforms do not infer text or reconstruct identity data. Coordinates and preview images remain tied to the successful transformed candidate.

## Reproduce

```powershell
.\.venv\Scripts\python.exe tools/benchmark_reader.py
.\.venv\Scripts\python.exe -m pytest -q
```

The benchmark reads the originals and degradation manifests solely to compare exact payload hashes. It writes timing/read-status metadata to `tmp/reader_benchmark.json`, without decoded identity fields. It leaves images unchanged. The private medium fixture test skips if the local image files are not present. The generated synthetic hard test is portable and contains no identity data.

Production defaults: 20 fast candidates, up to 160 additional recovery calls, a 20-second image budget and 2-second camera-pass budget. Native operations may finish after the nominal deadline; a valid result from such an operation is retained unless the user cancelled. All runtime validation here was on Windows; other operating systems and camera drivers have not been hardware-tested.

For the unresolved hard image, use a less degraded input or a new capture. Alternative commercial decoders could be benchmarked separately, but none has been validated or introduced as a dependency in this update.
