import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from degrade_images import ROOT, degrade, encode_image, load_settings, run_batch


def test_repeatable_degradation_preserves_input():
    profile = load_settings(ROOT / 'degradation.toml')['profiles']['hard']
    image = np.random.default_rng(1).integers(0, 256, (120, 200, 3), dtype=np.uint8)
    original = image.copy()
    first, params = degrade(image, profile, 42)
    again, repeated = degrade(image, profile, 42)
    other, _ = degrade(image, profile, 43)
    assert np.array_equal(image, original)
    assert np.array_equal(first, again)
    assert params == repeated
    assert first.shape != other.shape or not np.array_equal(first, other)
    assert encode_image(first, profile, 'jpg').startswith(b'\xff\xd8')
    assert encode_image(first, profile, 'png').startswith(b'\x89PNG')


def test_batch_outputs_and_originals(tmp_path):
    settings = load_settings(ROOT / 'degradation.toml')
    source, output = tmp_path / 'originals', tmp_path / 'degraded'
    source.mkdir()
    settings['batch'].update(input_directory=source, output_directory=output)
    image = source / 'test.png'
    Image.new('RGB', (180, 100), 'white').save(image)
    before = hashlib.sha256(image.read_bytes()).hexdigest()
    first, errors = run_batch(settings)
    assert errors == 0
    assert len(list(first.glob('*.jpg'))) == 3
    assert hashlib.sha256(image.read_bytes()).hexdigest() == before
    manifest = json.loads((first / 'manifest.json').read_text())
    assert {item['profile'] for item in manifest['outputs']} == {'mild', 'medium', 'hard'}
    assert all(item['source_sha256'] == before for item in manifest['outputs'])
    second, _ = run_batch(settings)
    assert first != second
    assert [item['output_sha256'] for item in json.loads((second / 'manifest.json').read_text())['outputs']] == [item['output_sha256'] for item in manifest['outputs']]
    (source / 'broken.jpg').write_bytes(b'not an image')
    third, errors = run_batch(settings)
    assert errors == 1 and len(list(third.glob('*.jpg'))) == 3


def test_empty_input_creates_folders(tmp_path):
    settings = load_settings(ROOT / 'degradation.toml')
    settings['batch'].update(input_directory=tmp_path / 'native', output_directory=tmp_path / 'low')
    assert run_batch(settings) == (None, 0)
    assert (tmp_path / 'native').is_dir() and (tmp_path / 'low').is_dir()
