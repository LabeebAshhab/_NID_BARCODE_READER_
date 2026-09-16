"""Compare fast-only and recovery modes on degradation manifests, without exporting payloads."""
import argparse
import json
import hashlib
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nid_scanner.config import ROOT, load_config
from nid_scanner.pipeline import load_image, scan


def benchmark():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'tmp' / 'reader_benchmark.json'))
    args = parser.parse_args()
    config = load_config()['processing']
    originals = (ROOT / 'native_raw_img').resolve()
    rows = []
    cache = {}
    for manifest_path in sorted((ROOT / 'low_img').rglob('manifest.json')):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        for entry in manifest.get('outputs', []):
            source = (originals / entry['source']).resolve()
            path = (manifest_path.parent / entry['output']).resolve()
            if not source.is_relative_to(originals) or not path.is_relative_to(manifest_path.parent.resolve()):
                continue
            if not source.is_file() or not path.is_file():
                continue
            if hashlib.sha256(source.read_bytes()).hexdigest() != entry['source_sha256']:
                continue
            if source not in cache:
                cache[source] = {r['sha256'] for r in scan(load_image(source), config)}
            image = load_image(path)
            row = {'image': str(path.relative_to(ROOT)), 'profile': entry['profile'], 'modes': {}}
            for mode in ('fast_only', 'recovery'):
                started = time.perf_counter()
                results = scan(image, dict(config, recovery=mode == 'recovery'))
                row['modes'][mode] = {'decoded': bool(results),
                    'exact_payload_match': ({r['sha256'] for r in results} == cache[source]) if results and cache[source] else None,
                    'elapsed_ms': round((time.perf_counter()-started)*1000, 1),
                    'stages': [r['stage'] for r in results]}
            rows.append(row)
            print(entry['profile'], json.dumps(row['modes']), flush=True)
    report = Path(args.output)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({'note': 'Originals are used only as evaluation ground truth, never as decoder input for degraded images.', 'results': rows}, indent=2), encoding='utf-8')
    print(f'Benchmark report: {report}')


if __name__ == '__main__':
    benchmark()
