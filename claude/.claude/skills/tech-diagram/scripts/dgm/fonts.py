"""Fonts: find real font files, measure text with their advance widths, embed used glyphs as WOFF2.

Layout needs text widths before anything is drawn. Instead of guessing, the widths come from the actual
font files (fontTools cmap + hmtx), and the SVG embeds a subset of exactly those fonts, so what was measured
is what renders — in a browser, in the PNG, on another machine.

Roles: `sans` (names, prose), `mono` (values, types, ports, code) and `cjk` (per-character fallback for
both, e.g. Chinese). A character missing from the role font falls back to `cjk`, then to an estimate.
Without fontconfig or fontTools everything degrades to estimates (slightly looser, unembedded).
"""
import base64
import io
import shutil
import subprocess
import unicodedata

try:
    from fontTools import subset as ft_subset
    from fontTools.ttLib import TTFont
except ImportError:  # pragma: no cover - estimates only
    TTFont = None

# fontconfig weight → CSS weight
_FC_W = [(0, 100), (40, 200), (50, 300), (55, 350), (75, 400), (80, 400), (100, 500), (180, 600), (200, 700),
         (205, 800), (210, 900), (215, 950)]


def _css_weight(fc):
    return min(_FC_W, key=lambda p: abs(p[0] - fc))[1]


class Face:
    """One font file face with lazy metrics."""

    def __init__(self, path, index, weight, family):
        self.path, self.index, self.weight, self.family = path, index, weight, family
        self._font = None
        self.used = set()

    def load(self):
        if self._font is None:
            self._font = TTFont(self.path, fontNumber=self.index, lazy=True)
            self.cmap = self._font.getBestCmap() or {}
            self.hmtx = self._font["hmtx"].metrics
            self.upem = self._font["head"].unitsPerEm
        return self

    def advance(self, ch):
        g = self.cmap.get(ord(ch))
        if g is None:
            return None
        return self.hmtx[g][0] / self.upem

    def woff2(self):
        """Subset to the characters used so far → base64 WOFF2 (or WOFF/TTF if brotli is missing)."""
        font = TTFont(self.path, fontNumber=self.index)
        opts = ft_subset.Options()
        opts.layout_features = ["kern"]
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        opts.hinting = False
        opts.desubroutinize = True
        sub = ft_subset.Subsetter(opts)
        sub.populate(text="".join(sorted(self.used)))
        sub.subset(font)
        for flavor, mime in (("woff2", "font/woff2"), ("woff", "font/woff")):
            try:
                font.flavor = flavor
                buf = io.BytesIO()
                font.save(buf)
                return mime, flavor, base64.b64encode(buf.getvalue()).decode()
            except Exception:  # brotli missing → try the next flavor
                continue
        font.flavor = None
        buf = io.BytesIO()
        font.save(buf)
        return "font/ttf", "truetype", base64.b64encode(buf.getvalue()).decode()


def _fc_faces(family):
    if not shutil.which("fc-list"):
        return []
    out = subprocess.run(["fc-list", "--format", "%{file}\t%{index}\t%{weight}\t%{style}\t%{family}\n",
                          f":family={family}"], capture_output=True, text=True).stdout
    faces = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        path, idx, w, style, fams = parts
        if any(s in style for s in ("Italic", "Oblique")):
            continue
        if family not in [f.strip() for f in fams.split(",")]:
            continue
        try:
            fcw = float(w.split()[0].strip("[]"))  # variable fonts print "[100 900]"
        except ValueError:
            continue
        faces.append((path, int(idx), _css_weight(fcw)))
    return faces


class FontSet:
    """Resolved faces per role and weight; measures strings and remembers which glyphs were used."""

    def __init__(self, spec):
        self.spec = spec
        self.faces = {}  # (role, weight) → Face | None
        self.ok = TTFont is not None
        self._cands = {}

    def _candidates(self, role):
        if role not in self._cands:
            found = []
            for fam in self.spec[role]["families"]:
                found = _fc_faces(fam) if self.ok else []
                if found:
                    found = [(p, i, w, fam) for p, i, w in found]
                    break
            self._cands[role] = found
        return self._cands[role]

    def face(self, role, weight):
        key = (role, weight)
        if key not in self.faces:
            cands = self._candidates(role)
            best = None
            if cands:
                p, i, w, fam = min(cands, key=lambda c: (abs(c[2] - weight), -c[2]))
                try:
                    best = Face(p, i, weight, fam).load()
                except Exception:
                    best = None
            self.faces[key] = best
        return self.faces[key]

    def width(self, s, size, role="sans", weight=400, ls=0.0):
        """Width of `s` in px. `ls` = letter-spacing in em."""
        prim = self.face(role, weight)
        cjk = self.face("cjk", 400 if weight < 500 else (500 if weight < 600 else 700))
        total = 0.0
        for ch in s:
            adv = None
            for f in (prim, cjk):
                if f is not None:
                    adv = f.advance(ch)
                    if adv is not None:
                        f.used.add(ch)
                        break
            if adv is None:
                adv = _estimate(ch, role == "mono")
            total += adv
        return total * size + ls * size * len(s)

    def css_faces(self):
        """@font-face rules for every (role, weight) face that was used."""
        rules = []
        for (role, weight), f in sorted(self.faces.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            if f is None or not f.used:
                continue
            mime, fmt, data = f.woff2()
            rules.append(f"@font-face{{font-family:'dgm-{role}';font-weight:{weight};font-style:normal;"
                         f"src:url(data:{mime};base64,{data}) format('{fmt}');}}")
        return "\n".join(rules)

    def stack(self, role, embed):
        """CSS font-family stack for a role."""
        own = [f"'dgm-{role}'", "'dgm-cjk'"] if embed else []
        fams = self.spec[role]["families"] + self.spec["cjk"]["families"]
        return ", ".join(own + [f"'{f}'" if " " in f else f for f in fams] + [self.spec[role]["generic"]])

    def report(self):
        lines = []
        for role in ("sans", "mono", "cjk"):
            c = self._candidates(role)
            lines.append(f"{role}: {c[0][3] if c else 'not found (estimated widths)'}")
        return "; ".join(lines)


def _estimate(ch, mono):
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 1.0
    if mono:
        return 0.6
    if ch == " ":
        return 0.28
    if ch in "ilI.,:;|!'()[]/-·":
        return 0.32
    if ch in "mwMW":
        return 0.88
    if ch.isupper() or ch.isdigit():
        return 0.66
    return 0.57
