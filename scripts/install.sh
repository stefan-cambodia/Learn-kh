#!/usr/bin/env bash
# FR-KH Learning — installation sous Linux (et macOS).
#
#   ./scripts/install.sh                installe, puis propose la planification quotidienne
#   ./scripts/install.sh --schedule     installe et active la planification sans poser de question
#   ./scripts/install.sh --no-schedule  installe sans toucher à la planification
#
# Le script peut être relancé sans risque : il ne remplace ni .env, ni la configuration,
# ni la base de données, ni les leçons déjà générées.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
SCHEDULE="ask"
for arg in "$@"; do
  case "$arg" in
    --schedule) SCHEDULE="yes" ;;
    --no-schedule) SCHEDULE="no" ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Option inconnue : $arg" >&2; exit 2 ;;
  esac
done

say() { printf '\n== %s\n' "$1"; }

say "1/5  Python"
PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.9 ou plus récent est nécessaire." >&2
  echo "  Debian/Ubuntu : sudo apt install python3      Fedora : sudo dnf install python3" >&2
  echo "  Arch          : sudo pacman -S python         macOS  : brew install python" >&2
  exit 1
fi
echo "Python trouvé : $PYTHON ($("$PYTHON" -c 'import sys; print(sys.version.split()[0])'))"
"$PYTHON" -c 'import sqlite3, zoneinfo, json' || {
  echo "Les modules sqlite3 et zoneinfo de Python sont nécessaires (paquet python3 complet)." >&2; exit 1; }
echo "Aucune bibliothèque supplémentaire n'est requise."
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Remarque : ffmpeg est absent. Il n'est utile que pour un moteur vocal qui ne fournirait pas de WAV."
fi

say "2/5  Fichier des clés API (.env)"
if [ -f .env ]; then
  echo ".env existe déjà : il est conservé tel quel."
else
  cp .env.example .env
  echo ".env créé à partir de .env.example : ajoutez-y vos clés API."
fi
chmod 600 .env

say "3/5  Dossiers, base de données et configuration"
chmod +x manage.py scripts/*.sh 2>/dev/null || true
"$PYTHON" manage.py init

say "4/5  Vérification générale"
"$PYTHON" manage.py check || true

say "5/5  Génération automatique quotidienne"
if [ "$SCHEDULE" = "ask" ]; then
  if [ -t 0 ]; then
    read -r -p "Activer la génération automatique (07h00, heure du Cambodge) ? [O/n] " answer
    case "${answer:-o}" in [oOyY]*) SCHEDULE="yes" ;; *) SCHEDULE="no" ;; esac
  else
    SCHEDULE="no"
  fi
fi
if [ "$SCHEDULE" = "yes" ]; then
  "$PYTHON" manage.py schedule install
else
  echo "Planification non installée. Pour l'activer plus tard : $PYTHON manage.py schedule install"
fi

cat <<EOF

Installation terminée dans $ROOT

Étapes suivantes :
  1. Clés API   : éditez .env (guides : docs/GOOGLE_CLOUD_TTS.md et docs/AZURE_SPEECH_KHMER.md)
  2. Prénoms    : éditez config/config.json, rubrique « learners » (avant la première leçon)
  3. Essai voix : $PYTHON manage.py tts test
  4. 1re leçon  : ./scripts/run.sh
  5. Lecture    : ouvrez index.html dans votre navigateur
EOF
