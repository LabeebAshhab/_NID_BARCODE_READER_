"""Independent image degradation tool. Does not import or call the NID reader."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tomllib
from uuid import uuid4

import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}
LIMITS = {
    'scale': (.05, 1), 'blur_sigma': (0, 10), 'motion_pixels': (1, 51),
    'noise_sigma': (0, 80), 'contrast': (.05, 1.5), 'brightness': (.1, 2),
    'shadow': (0, .9), 'glare': (0, .9), 'rotation_degrees': (0, 45),
    'perspective': (0, .2), 'jpeg_quality': (1, 100),
}


def load_settings(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        settings = tomllib.load(stream)
    batch = settings['batch']
    for name in ('input_directory', 'output_directory'):
        batch[name] = (path.parent / batch[name]).resolve()
    source, dest = batch['input_directory'], batch['output_directory']
    if source == dest or source in dest.parents or dest in source.parents:
        raise ValueError('Input and output directories must be separate, non-nested folders')
    if batch['output_format'] not in ('jpg', 'png'):
        raise ValueError('output_format must be jpg or png')
    if type(batch['variants_per_profile']) is not int or not 1 <= batch['variants_per_profile'] <= 20:
        raise ValueError('variants_per_profile must be an integer from 1 to 20')
    if type(batch['seed']) is not int or batch['seed'] < 0:
        raise ValueError('seed must be a nonnegative integer')
    if not 320 <= batch['max_processing_dimension'] <= 6000:
        raise ValueError('max_processing_dimension must be between 320 and 6000')
    if not 1 <= batch['max_input_pixels'] <= 100_000_000:
        raise ValueError('max_input_pixels must be between 1 and 100000000')
    if type(batch['recursive']) is not bool:
        raise ValueError('recursive must be boolean')
    if not batch['profiles'] or not set(batch['profiles']) <= settings['profiles'].keys():
        raise ValueError('batch.profiles must contain existing profile names')
    for name, profile in settings['profiles'].items():
        if not name.replace('_', '').isalnum():
            raise ValueError('Profile names must contain only letters, numbers or underscores')
        for key, (low, high) in LIMITS.items():
            value = profile[key]
            if type(value) not in (int, float) or not low <= value <= high:
                raise ValueError(f'{name}.{key} must be between {low} and {high}')
        for key in ('motion_pixels', 'jpeg_quality'):
            if type(profile[key]) is not int:
                raise ValueError(f'{name}.{key} must be an integer')
    return settings


def read_image(path, batch):
    with Image.open(path) as image:
        if image.width * image.height > batch['max_input_pixels']:
            raise ValueError('Input exceeds max_input_pixels')
        image = ImageOps.exif_transpose(image).convert('RGB')
        original_size = image.size
        limit = batch['max_processing_dimension']
        image.thumbnail((limit, limit), Image.Resampling.LANCZOS)
        return np.array(image), original_size


def degrade(image, profile, seed):
    """RGB -> degraded RGB plus sampled parameters. Never modifies the input array."""
    rng = np.random.default_rng(seed)
    h, w = image.shape[:2]
    small = cv2.resize(image, (max(1, round(w*profile['scale'])), max(1, round(h*profile['scale']))), interpolation=cv2.INTER_AREA)
    work = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    offset = rng.uniform(0, profile['perspective'], (4, 2)).astype(np.float32)
    corners = np.float32([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]])
    target = corners + offset * np.float32([[w, h], [-w, h], [-w, -h], [w, -h]])
    work = cv2.warpPerspective(work, cv2.getPerspectiveTransform(corners, target), (w, h), borderValue=(245, 245, 245))
    angle = float(rng.uniform(-profile['rotation_degrees'], profile['rotation_degrees']))
    matrix = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    nw, nh = int(np.ceil(h*sin+w*cos)), int(np.ceil(h*cos+w*sin))
    matrix[:, 2] += ((nw-w)/2, (nh-h)/2)
    work = cv2.warpAffine(work, matrix, (nw, nh), borderValue=(245, 245, 245))
    sigma = profile['blur_sigma']
    if sigma > 0:
        work = cv2.GaussianBlur(work, (0, 0), sigma)
    size = profile['motion_pixels']
    vertical = bool(rng.integers(0, 2))
    if size > 1:
        kernel = np.zeros((size, size), np.float32)
        if vertical:
            kernel[:, size//2] = 1/size
        else:
            kernel[size//2, :] = 1/size
        work = cv2.filter2D(work, -1, kernel)
    work = (work.astype(np.float32)-127.5)*profile['contrast']+127.5
    work *= profile['brightness']
    yy, xx = np.ogrid[0:nh, 0:nw]
    gradient = xx / max(nw-1, 1)
    reverse_shadow = bool(rng.integers(0, 2))
    if reverse_shadow:
        gradient = 1-gradient
    work *= (1-profile['shadow']*gradient)[..., None]
    cx, cy = rng.uniform(.2, .8, 2)
    glow = np.exp(-(((xx/nw-cx)/.23)**2+((yy/nh-cy)/.30)**2)/2)
    alpha = (glow*profile['glare'])[..., None]
    work = work*(1-alpha)+255*alpha
    work += rng.normal(0, profile['noise_sigma'], work.shape).astype(np.float32)
    work = np.clip(work, 0, 255).astype(np.uint8)
    return work, {'rotation_degrees': angle, 'perspective_offsets': offset.tolist(),
                  'motion_direction': 'vertical' if vertical else 'horizontal',
                  'shadow_reversed': reverse_shadow, 'glare_center_fraction': [float(cx), float(cy)]}


def encode_image(rgb, profile, extension):
    # JPEG loss is part of the degradation even when the requested container is PNG.
    ok, jpeg = cv2.imencode('.jpg', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                            [cv2.IMWRITE_JPEG_QUALITY, profile['jpeg_quality']])
    if not ok:
        raise ValueError('JPEG encoding failed')
    if extension == 'jpg':
        return jpeg.tobytes()
    decoded = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
    ok, png = cv2.imencode('.png', decoded)
    if not ok:
        raise ValueError('PNG encoding failed')
    return png.tobytes()


def run_batch(settings, image_path=None):
    batch = settings['batch']
    source, output = batch['input_directory'], batch['output_directory']
    if image_path:
        paths = [Path(image_path).resolve()]
        if not paths[0].is_file():
            raise ValueError(f'Image does not exist: {paths[0]}')
        if output == paths[0] or output in paths[0].parents:
            raise ValueError('Choose an original outside the output directory')
    else:
        source.mkdir(parents=True, exist_ok=True)
        candidates = source.rglob('*') if batch['recursive'] else source.glob('*')
        paths = sorted(p for p in candidates if p.is_file() and not p.is_symlink() and p.suffix.lower() in EXTENSIONS)
    output.mkdir(parents=True, exist_ok=True)
    if not paths:
        print(f'No images found. Add images to {source} and run again.')
        return None, 0
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uuid4().hex[:8]
    run_dir = output / run_id
    run_dir.mkdir(exist_ok=False)
    report = {'run_id': run_id, 'seed': batch['seed'], 'opencv_version': cv2.__version__,
              'numpy_version': np.__version__, 'outputs': [], 'errors': []}
    for path in paths:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            image, original_size = read_image(path, batch)
            source_name = str(path.relative_to(source)) if path.is_relative_to(source) else str(path)
            source_id = hashlib.sha256(source_name.encode()).hexdigest()[:8]
            for name in batch['profiles']:
                profile = settings['profiles'][name]
                for index in range(batch['variants_per_profile']):
                    seed_data = f"{batch['seed']}:{digest}:{source_name}:{name}:{index}"
                    seed = int.from_bytes(hashlib.sha256(seed_data.encode()).digest()[:8], 'little')
                    degraded, sampled = degrade(image, profile, seed)
                    content = encode_image(degraded, profile, batch['output_format'])
                    filename = f"{path.stem[:70]}_{source_id}_{name}_{index+1:02d}.{batch['output_format']}"
                    with (run_dir / filename).open('xb') as stream:
                        stream.write(content)
                    report['outputs'].append({'source': source_name, 'source_sha256': digest,
                        'output': filename, 'output_sha256': hashlib.sha256(content).hexdigest(),
                        'profile': name, 'parameters': profile, 'sampled': sampled, 'seed': seed,
                        'original_size': list(original_size), 'working_size': [image.shape[1], image.shape[0]],
                        'output_size': [degraded.shape[1], degraded.shape[0]]})
        except Exception as exc:
            report['errors'].append({'source': str(path), 'error': f'{type(exc).__name__}: {exc}'})
            print(f'Could not finish {path.name}: {exc}')
    with (run_dir / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(f"Created {len(report['outputs'])} degraded image(s) in {run_dir}")
    print(f"Failed inputs: {len(report['errors'])}. Settings and source mapping: manifest.json")
    return run_dir, len(report['errors'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default=str(ROOT / 'degradation.toml'))
    parser.add_argument('--image', help='Process one image instead of the input folder')
    parser.add_argument('--profile', help='Process only this configured profile (default: all configured profiles)')
    parser.add_argument('--seed', type=int, help='Override the repeatable random seed')
    args = parser.parse_args()
    try:
        settings = load_settings(args.config)
        if args.profile:
            if args.profile not in settings['profiles']:
                raise ValueError(f'Unknown profile: {args.profile}')
            settings['batch']['profiles'] = [args.profile]
        if args.seed is not None:
            if args.seed < 0:
                raise ValueError('seed must be nonnegative')
            settings['batch']['seed'] = args.seed
        _, failures = run_batch(settings, args.image)
        return 1 if failures else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'Degradation error: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
