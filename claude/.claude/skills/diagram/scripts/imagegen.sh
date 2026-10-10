#!/usr/bin/env bash
# imagegen.sh — generate (or edit) one raster image with Codex CLI's built-in $imagegen
# (gpt-image via the user's ChatGPT login; no API key).
#
# usage: imagegen.sh "<prompt>" <out.png> [--size WxH] [--ref <image>]... [--timeout SEC]
#
#   --size WxH     e.g. 1024x1024 (fastest), 1536x1024, 1024x1536. Omit unless the aspect matters.
#   --ref FILE     reference / source image (repeatable, max 4). With a ref the prompt describes an edit.
#   --timeout SEC  abort after SEC seconds (default 600).
#
# stdout: absolute path of the written PNG.  exit: 0 ok · 1 usage/precondition · 2 no image · 124 timeout
#
# Codex runs sandboxed in a private temp dir and is told to save out.png there; the wrapper copies it to
# the requested path. If Codex leaves the image only in $CODEX_HOME/generated_images, the newest PNG
# created during this run is used instead. (Approach adapted from oakplank/gpt-image-bridge and
# Sateezg/codex-bridge, both MIT.)
set -uo pipefail

err() { printf 'imagegen: %s\n' "$*" >&2; }
usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 1; }

[ $# -ge 2 ] || usage
PROMPT="$1"; OUT="$2"; shift 2
SIZE=""; TIMEOUT=600; REFS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --size) SIZE="${2:-}"; shift 2 ;;
    --ref) REFS+=("${2:-}"); shift 2 ;;
    --timeout) TIMEOUT="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) err "unknown argument: $1"; usage ;;
  esac
done
[ -n "$PROMPT" ] || { err "empty prompt"; exit 1; }
[ "${#REFS[@]}" -le 4 ] || { err "at most 4 --ref images"; exit 1; }

command -v codex >/dev/null 2>&1 || {
  err "codex CLI not found. Install it (npm i -g @openai/codex) and run 'codex login'."; exit 1; }
codex login status >/dev/null 2>&1 || {
  err "codex is not logged in. Ask the user to run: ! codex login"; exit 1; }

case "$OUT" in /*) ;; *) OUT="$(pwd)/$OUT" ;; esac
mkdir -p "$(dirname "$OUT")" || exit 1
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/imagegen.XXXXXX")"
LOG="$WORK.log"
START="$(date +%s)"

ARGS=(exec --skip-git-repo-check -s workspace-write -C "$WORK")
for r in "${REFS[@]}"; do
  [ -f "$r" ] || { err "reference image not found: $r"; exit 1; }
  ARGS+=(-i "$(cd "$(dirname "$r")" && pwd)/$(basename "$r")")
done

SAVE="Save the final PNG as ./out.png in the current working directory (relative path, overwrite allowed). \
You MUST produce the image with the image generation tool; do not draw it with code, Python, curl or any other way. \
Do nothing else and reply with only: out.png"
if [ "${#REFS[@]}" -gt 0 ]; then
  TASK="Use \$imagegen to edit the attached image(s). Keep everything not mentioned unchanged. Change: ${PROMPT}"
else
  TASK="Use \$imagegen to generate exactly one image. Image description: ${PROMPT}"
fi
[ -n "$SIZE" ] && TASK="${TASK} Image size: ${SIZE}."
# `--` matters: -i is variadic and would otherwise swallow the prompt.
ARGS+=(-- "${TASK} ${SAVE}")

if command -v timeout >/dev/null 2>&1; then
  timeout "$TIMEOUT" codex "${ARGS[@]}" </dev/null >"$LOG" 2>&1; STATUS=$?
else
  codex "${ARGS[@]}" </dev/null >"$LOG" 2>&1; STATUS=$?
fi
[ "$STATUS" -eq 124 ] && { err "timed out after ${TIMEOUT}s (log: $LOG)"; exit 124; }

is_png() { [ -s "$1" ] && [ "$(head -c 4 "$1" | od -An -tx1 | tr -d ' \n')" = "89504e47" ]; }
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0; }

IMG=""
if is_png "$WORK/out.png"; then
  IMG="$WORK/out.png"
else
  best=0
  for f in "$WORK"/*.png "${CODEX_HOME:-$HOME/.codex}"/generated_images/*/*.png; do
    [ -f "$f" ] && is_png "$f" || continue
    m="$(mtime "$f")"
    if [ "$m" -ge "$START" ] && [ "$m" -gt "$best" ]; then IMG="$f"; best="$m"; fi
  done
fi

if [ -z "$IMG" ]; then
  err "no image produced (codex exit $STATUS). Last lines of the log:"
  tail -n 25 "$LOG" >&2
  err "(full log: $LOG)"
  exit 2
fi
cp "$IMG" "$OUT"
rm -rf "$WORK" "$LOG" 2>/dev/null || true
printf '%s\n' "$OUT"
