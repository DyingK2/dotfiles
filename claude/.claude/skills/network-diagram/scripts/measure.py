"""Measure text widths in headless Chromium; results fill text_metrics' cache for the next layout pass.

Layouts only call text_metrics.text_width; on a cache miss it falls back to an estimate and records the request.
Flow: lay out with estimates (collect requests) → measure(keys, theme) in one batch → lay out with real widths.
"""
from playwright.sync_api import Error, sync_playwright

INSTALL = "uv run --with playwright playwright install chromium-headless-shell"

JS = """
([keys, sans, mono]) => {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  document.body.appendChild(svg);
  return keys.map(([s, size, isMono, bold]) => {
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('font-family', isMono ? mono : sans);
    t.setAttribute('font-size', size);
    if (bold) t.setAttribute('font-weight', 600);
    t.textContent = s;
    svg.appendChild(t);
    const w = t.getComputedTextLength();
    t.remove();
    return w;
  });
}
"""


def launch(p):
    """Start headless Chromium, or exit with the one-line install command when it is missing."""
    try:
        return p.chromium.launch()
    except Error as e:
        if "Executable doesn't exist" in str(e):
            raise SystemExit(f"error: Chromium for Playwright is not installed. Run once:\n  {INSTALL}\n"
                             "(or pass --measure estimate --no-check to render without a browser)") from None
        raise


def measure(keys, theme):
    """keys: [(text, size, mono?, bold?)] → {key: measured width}."""
    keys = sorted(set(keys))
    if not keys:
        return {}
    with sync_playwright() as p:
        b = launch(p)
        pg = b.new_page()
        pg.set_content("<!doctype html><body></body>")
        pg.evaluate("document.fonts.ready")
        widths = pg.evaluate(JS, [[list(k) for k in keys], theme["fonts"]["sans"], theme["fonts"]["mono"]])
        b.close()
    return dict(zip(keys, widths))
