#!/usr/bin/env bash
# Build the proposal PDF. Runs on macOS and on Windows via Git Bash (or WSL).
set -euo pipefail

cd "$(dirname "$0")"

SRC="main.tex"
BUILD_DIR=build

# macOS: PATH may point at BasicTeX, which lacks packages required by
# neurips_2026.sty (e.g. environ.sty). Prefer a full TeX Live if installed.
if [ "$(uname -s)" = "Darwin" ]; then
  for d in $(ls -d /usr/local/texlive/*/bin/universal-darwin 2>/dev/null | grep -v basic | sort -r || true); do
    if [ -x "$d/latexmk" ]; then export PATH="$d:$PATH"; break; fi
  done
fi

command -v latexmk >/dev/null 2>&1 || {
  echo "latexmk not found — install TeX Live (macOS) or MiKTeX/TeX Live (Windows) and put it in PATH." >&2
  exit 1
}

mkdir -p "$BUILD_DIR"

if latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir="$BUILD_DIR" "$SRC" >"$BUILD_DIR/build.log" 2>&1; then
  echo "OK: $BUILD_DIR/${SRC%.tex}.pdf"
else
  echo "Build failed — last lines of $BUILD_DIR/build.log:" >&2
  tail -n 20 "$BUILD_DIR/build.log" >&2
  exit 1
fi
