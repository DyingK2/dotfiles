# Concept illustrations with Codex `$imagegen`

`scripts/imagegen.sh` asks the Codex CLI (logged in with the user's ChatGPT account, no API key) to generate
one image with its built-in image tool and copies the PNG to the path you give.

```bash
scripts/imagegen.sh "<prompt>" <out.png> [--size 1536x1024] [--ref existing.png] [--timeout 600]
```
Prints the absolute path on success. Exit 1 = precondition (codex missing / not logged in → ask the user to run
`! codex login`), 2 = no image produced (log tail on stderr), 124 = timeout.

## When — and when not

- **Yes**: a metaphor or scene that makes an abstract idea tangible (cache hierarchy as desk / shelf /
  warehouse), a hero picture for a doc, an illustration of a physical thing (a rack, a cable, a chip).
- **No**: anything with structure, steps, data, values or labels — those are code-rendered, always. A bitmap
  cannot be diffed, edited, or trusted to spell text correctly.
- Each call spends the user's ChatGPT quota and takes about a minute. Say what you want to generate and get a
  yes first; one image per request unless asked for variants. Run it in the background when possible
  (`run_in_background`), and keep working on the code-rendered parts meanwhile.

## Prompt template

Match the diagram's look so the picture and the SVG sit together:

```
Editorial flat illustration explaining <concept> as a metaphor: <3–4 concrete visual elements and how they
are arranged, mapping to the parts of the concept>. Calm, minimal, lots of white space, off-white background
#fafaf9, ink #1d2330 thin line work with muted greys, one accent colour orange #e8590c used only on
<the focal element>. No text, no letters, no numbers, no logos.
```

- Always "no text": labels are added in SVG (`d.text`, `d.note`, a `d.table` beside it), where they are exact
  and translatable.
- Name the focal element explicitly and give it the accent colour — the same colour as the `focal`/`accent`
  elements in the diagram.
- `--size`: `1536x1024` (landscape, default choice), `1024x1024` (fastest), `1024x1536` (portrait).
- Edits: `--ref old.png` + a prompt describing only the change.

## Composing

```python
img = d.image("assets/concept-cache.png", w=560).at(0, 0)
t = d.table([...], [...]).right_of(img, gap=40, align="top")
d.note("Takeaway …", title="Takeaway", w=t.w).below(t, gap=20, align="left")
d.footer("Illustration generated with Codex $imagegen; figures are typical for …")
```
Read the generated PNG before using it (does it match the metaphor? any stray text?); regenerate at most twice.
Keep the prompt in the scene's docstring so the image can be reproduced. Example: `examples/cache-concept.py`.
