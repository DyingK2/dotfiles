"""Text width: prefer the browser-measured cache (populated by measure.py); on a miss, fall back to a
conservative estimate and log the request."""
import unicodedata

ASC, DESC = 0.8, 0.25  # ascent/descent relative to font size
MARGIN = 1.04

_NARROW = set(" ·.,:;|!il'I()[]/-")


def _char(ch, mono):
    if unicodedata.east_asian_width(ch) in ("W", "F") or ch in "→←":
        return 1.0
    if mono:
        return 0.6
    if ch == " ":
        return 0.28
    if ch in _NARROW:
        return 0.32
    if ch in "mwMW":
        return 0.86
    if ch.isupper() or ch.isdigit():
        return 0.64
    return 0.56


MEASURED = {}      # (text, size, mono?, bold?) → measured width
REQUESTS = set()   # cache-miss requests, for measure.py to batch-measure
MEASURED_PAD = 1.02  # 2% margin on measured values (rendering-side font differences)


def text_width(s, size, mono=False, bold=False):
    key = (s, float(size), bool(mono), bool(bold))
    if key in MEASURED:
        return MEASURED[key] * MEASURED_PAD
    REQUESTS.add(key)
    w = sum(_char(c, mono) for c in s) * size
    return w * (1.06 if bold and not mono else 1.0) * MARGIN


def text_box(x, y, s, size, anchor="start", mono=False, bold=False):
    """Return the text bounding box (x0, y0, x1, y1); y is the baseline."""
    w = text_width(s, size, mono, bold)
    x0 = {"start": x, "middle": x - w / 2, "end": x - w}[anchor]
    return (x0, y - ASC * size, x0 + w, y + DESC * size)
