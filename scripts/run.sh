#!/usr/bin/env bash
# FR-KH Learning — lancement manuel (Linux, macOS).
#
#   ./scripts/run.sh                      génère la leçon du jour (sans attendre 07h00)
#   ./scripts/run.sh --date 2026-01-31    génère la leçon d'une date précise
#   ./scripts/run.sh --open               génère, puis ouvre le site dans le navigateur
#
# Sans danger si la leçon existe déjà : rien n'est créé en double, seuls les
# fichiers audio manquants sont complétés.

set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON" ]; then
  echo "Python 3 est introuvable : lancez d'abord ./scripts/install.sh" >&2
  exit 1
fi

OPEN="no"
ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--open" ]; then OPEN="yes"; else ARGS+=("$arg"); fi
done

"$PYTHON" manage.py generate ${ARGS[@]+"${ARGS[@]}"}

echo
echo "Site : $(pwd)/index.html"
if [ "$OPEN" = "yes" ]; then
  if command -v xdg-open >/dev/null 2>&1; then xdg-open index.html >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open index.html
  fi
fi
