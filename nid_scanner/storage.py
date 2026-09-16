import csv
import io
import json
import os
from pathlib import Path
import tempfile


def safe_cell(value, enabled=True):
    value = str(value)
    return "'" + value if enabled and value.lstrip().startswith(("=", "+", "-", "@")) else value


class Exporter:
    def __init__(self, config):
        self.config = config
        self.seen = set()

    def save(self, record):
        key = (record["format"], record["sha256"])
        if self.config["deduplicate"] and key in self.seen:
            return []
        folder = Path(self.config["directory"])
        folder.mkdir(parents=True, exist_ok=True)
        stem = record["id"]
        documents = {}
        if "json" in self.config["formats"]:
            documents["json"] = json.dumps(record, ensure_ascii=False, indent=2)
        if "csv" in self.config["formats"]:
            row = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                   for k, v in record.items()}
            row = {k: safe_cell(v, self.config["csv_excel_safe"]) for k, v in row.items()}
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
            documents["csv"] = buffer.getvalue()
        written = []
        # Each file is atomic; a filesystem failure between formats may leave one file.
        # IDs stay stable on retry and the record is only marked seen after all writes.
        for extension, content in documents.items():
            target = folder / f"{stem}.{extension}"
            fd, temp = tempfile.mkstemp(dir=folder, prefix=".pending-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8-sig" if extension == "csv" else "utf-8", newline="") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, target)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
            written.append(str(target))
        self.seen.add(key)
        return written
