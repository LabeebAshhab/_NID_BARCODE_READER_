"""Headless image scanning using the same pipeline as the desktop app."""
import argparse
from nid_scanner.config import load_config
from nid_scanner.pipeline import load_image, scan
from nid_scanner.storage import Exporter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images", nargs="+")
    parser.add_argument("--config")
    args = parser.parse_args()
    config = load_config(args.config)
    exporter = Exporter(config["output"])
    failed = False
    for path in args.images:
        try:
            results = scan(load_image(path), config["processing"], path)
            if not results:
                print(f"No barcode: {path}")
                failed = True
            for result in results:
                files = exporter.save(result)
                print(f"{result['format']}: {len(files)} export(s); {result['byte_count']} bytes")
        except Exception as exc:
            print(f"Failed {path}: {exc}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
