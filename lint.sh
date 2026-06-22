#!/usr/bin/env bash
# Linter de los markdown de F4: estructura markdown + LaTeX embebido.
# Uso:
#   ./lint.sh              -> valida todos los .md de Resources/Exactas/Fisica 4/
#   ./lint.sh archivo.md   -> valida los archivos indicados
set -uo pipefail
cd "$(dirname "$0")"

if [ "$#" -gt 0 ]; then
  FILES=("$@")
else
  FILES=("Resources/Exactas/Fisica 4/"*.md)
fi

status=0

echo "== markdownlint =="
markdownlint-cli2 "${FILES[@]}" || status=1

echo
echo "== LaTeX (KaTeX) =="
node scripts/lint-latex.mjs "${FILES[@]}" || status=1

exit $status