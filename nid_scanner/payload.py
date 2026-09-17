"""Conservative parsing: never infer field positions or decrypt unknown payloads.

Two Bangladeshi NID barcode payload layouts are recognised explicitly:

* Older laminated cards use XML-like leaf tags, e.g. ``<pin>...<name>...``.
* Newer Smart/chip cards use a control-character-delimited record: a short
  header, then ``<code><value>`` fields separated by GS (0x1d) / RS (0x1e) and
  terminated by EOT (0x04), e.g. ``NMMd. Ruhul Amin`` then ``BR19850121``.

Both are decoded losslessly by ZXing; this module only labels what is explicitly
present. Field values are shown verbatim (dates and numbers are not reformatted),
unknown two-letter codes are surfaced under their own code rather than guessed,
and signatures/checksums are kept as-is. Anything unrecognised stays available in
the raw payload.
"""
import json
import re

# High-confidence Smart-NID field codes, cross-checked against the printed card
# and the machine-readable zone. Unlisted codes are shown under their raw code.
SMART_NID_CODES = {
    "NM": "Name",
    "NW": "NID number",
    "BR": "Date of birth",
    "DT": "Issue date",
    "SG": "Digital signature",
}

# ZXing renders control bytes in its text view as these mnemonics; used only when
# the raw bytes are unavailable.
_MNEMONICS = {"<GS>": "\x1d", "<RS>": "\x1e", "<FS>": "\x1c", "<US>": "\x1f", "<EOT>": "\x04"}


def _parse_delimited(raw):
    """Parse a control-character-delimited Smart-NID record into ordered fields."""
    fields = {}
    for segment in re.split(rb"[\x1c\x1d\x1e\x1f\x04]+", raw):
        token = segment.decode("utf-8", "replace").strip("\x00").strip()
        match = re.fullmatch(r"([A-Za-z]{2})(.+)", token)
        if not match:
            continue  # header or empty segment: nothing explicit to label
        code, value = match.groups()
        label = SMART_NID_CODES.get(code.upper(), code.upper())
        if label in fields:
            if not isinstance(fields[label], list):
                fields[label] = [fields[label]]
            fields[label].append(value)
        else:
            fields[label] = value
    return fields


def parse_payload(text, raw=None):
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return {"status": "JSON object", "fields": value}
    except (ValueError, TypeError):
        pass
    # Newer Smart/chip NID: control-character-delimited fields. Prefer the exact
    # bytes; fall back to translating ZXing's text mnemonics when bytes are absent.
    if raw is None:
        candidate = text
        for mnemonic, char in _MNEMONICS.items():
            candidate = candidate.replace(mnemonic, char)
        raw = candidate.encode("utf-8", "replace")
    if any(sep in raw for sep in (b"\x1d", b"\x1e", b"\x1c", b"\x1f")):
        fields = _parse_delimited(raw)
        if fields:
            return {"status": "Smart NID fields (unverified)", "fields": fields}
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
