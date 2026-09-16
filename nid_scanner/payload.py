"""Conservative parsing: never infer field positions or decrypt unknown payloads."""
import json
import re


def parse_payload(text):
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return {"status": "JSON object", "fields": value}
    except (ValueError, TypeError):
        pass
    # Supports repeated XML-like leaf tags, without executing XML entities.
    pairs = re.findall(r"<([A-Za-z_][\w.-]*)>([^<>]*)</\1>", text)
    if not pairs:
        pairs = []
        for line in re.split(r"[\r\n|\x1d]+", text):
            match = re.fullmatch(r"\s*([\w .-]{1,60})\s*[:=]\s*(.*?)\s*", line)
            if match:
                pairs.append(match.groups())
    fields = {}
    for key, value in pairs:
        if key in fields:
            if not isinstance(fields[key], list):
                fields[key] = [fields[key]]
            fields[key].append(value)
        else:
            fields[key] = value
    return {"status": "Explicit labels (unverified)" if fields else "Unstructured / opaque payload",
            "fields": fields}
