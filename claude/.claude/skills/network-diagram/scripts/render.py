# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6", "playwright>=1.40"]
# ///
"""CLI: topology.yaml → SVG, then PNG + layout self-check.

usage: uv run scripts/render.py topology.yaml [--view l3|l2] [--layout tb|lr] [--measure browser|estimate]
                                [-o out.svg] [--no-check]
Output defaults to <yaml dir>/<stem>-<view>[-lr].svg (+ .png). Exit 1 when the check finds conflicts.
"""
import argparse
import json
import pathlib
import sys

import yaml

import icons
from model import ModelError, build_model

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_theme():
    return json.loads((ROOT / "theme.json").read_text())


def render_svg(model, theme, measure="browser", view="l3", orient=None):
    """measure="browser": lay out with estimated text widths, measure every string in Chromium, lay out again.
    measure="estimate": estimated widths only (no browser needed, slightly looser spacing)."""
    import text_metrics
    from svg_writer import render
    orient = orient or "tb"
    if view == "l2":
        from layout_l2 import layout
    elif orient == "lr":
        from layout_lr import layout
    else:
        from layout import layout
    symbols = icons.build_symbols(theme)
    text_metrics.MEASURED.clear()
    text_metrics.REQUESTS = set()
    scene = layout(model, theme)
    if measure == "browser":
        from measure import measure as run_measure
        for _ in range(2):  # a relayout can request a few new strings; measure those once more
            keys, text_metrics.REQUESTS = set(text_metrics.REQUESTS), set()
            if not keys:
                break
            text_metrics.MEASURED.update(run_measure(keys, theme))
            scene = layout(model, theme)
    for w in scene["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    return render(scene, theme, symbols)


def main():
    ap = argparse.ArgumentParser(description="Render a topology YAML to a document-quality SVG + PNG.")
    ap.add_argument("yaml")
    ap.add_argument("--view", default="l3", choices=["l3", "l2"], help="l3 logical topology / l2 host bridge view")
    ap.add_argument("--layout", choices=["tb", "lr"], default="tb", help="L3 direction: tb portrait (default) / lr landscape")
    ap.add_argument("--measure", default="browser", choices=["browser", "estimate"])
    ap.add_argument("-o", "--out", help="output .svg path")
    ap.add_argument("--no-check", action="store_true", help="skip PNG + conflict check")
    a = ap.parse_args()
    src = pathlib.Path(a.yaml)
    theme = load_theme()
    try:
        model = build_model(yaml.safe_load(src.read_text()))
    except yaml.YAMLError as e:
        sys.exit(f"YAML syntax error: {e}")
    except ModelError as e:
        sys.exit(f"error: {e}")
    for w in model["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    name = f"{src.stem}-{a.view}" + ("-lr" if a.view == "l3" and a.layout == "lr" else "")
    out = pathlib.Path(a.out or src.with_name(f"{name}.svg"))
    if out.suffix.lower() != ".svg":
        out = out.with_name(out.name + ".svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_svg(model, theme, a.measure, a.view, a.layout))
    print(f"SVG: {out}")
    if a.no_check:
        return
    from check import check
    r = check(out)
    print(f"PNG: {r['png']}")
    for h in r["hits"]:
        print(f"  [{h['type']}] {h['a']}  <->  {h['b']}")
    print(f"{len(r['hits'])} conflict(s)" if r["hits"] else "0 conflicts")
    sys.exit(1 if r["hits"] else 0)


if __name__ == "__main__":
    main()
