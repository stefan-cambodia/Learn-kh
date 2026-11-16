#!/usr/bin/env python3
"""FR-KH Learning — point d'entrée en ligne de commande.

Exemples :
    python3 manage.py init                 préparer le projet
    python3 manage.py generate             générer la leçon du jour
    python3 manage.py generate --date 2026-01-31
    python3 manage.py check                vérification générale
    python3 manage.py --help               toutes les commandes
"""

import sys

if sys.version_info < (3, 9):
    sys.exit("FR-KH Learning nécessite Python 3.9 ou plus récent (version détectée : %s)."
             % sys.version.split()[0])

from frkh.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
