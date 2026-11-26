# Installation

## Ce qu'il faut

| Élément | Détail |
| --- | --- |
| Python | 3.9 ou plus récent. **Aucune bibliothèque à installer** : l'application n'utilise que la bibliothèque standard. |
| Navigateur | Firefox, Chrome, Edge ou Safari récents, sur ordinateur, tablette ou téléphone. |
| Clés API | Google Cloud Text-to-Speech (français, anglais) et Azure AI Speech (khmer). Voir les deux guides dédiés. |
| ffmpeg | Facultatif. Utile seulement si vous branchez un moteur vocal qui ne produit pas de WAV. |
| Espace disque | Environ 3 à 4 Mo d'audio par leçon (WAV non compressé, 24 kHz). |

Connexion Internet : nécessaire uniquement au moment de générer les audios.
Les leçons déjà produites se consultent hors ligne.

## Linux et macOS

```bash
cd /chemin/vers/fr-kh-learning
./scripts/install.sh
```

Le script vérifie Python, crée `.env` à partir de `.env.example`, prépare les
dossiers, la base SQLite et `config/config.json`, lance la vérification générale
puis propose d'activer la génération quotidienne. Options : `--schedule`
(activer sans poser la question) et `--no-schedule`.

Il peut être relancé sans risque : il ne remplace ni `.env`, ni la configuration,
ni la base, ni les leçons existantes.

## Windows

1. Installez Python depuis <https://www.python.org/downloads/> en cochant
   **Add python.exe to PATH** (ou : `winget install Python.Python.3.12`).
2. Double-cliquez sur `scripts\install.bat`.

Le script PowerShell fait la même chose que sous Linux. Il installe aussi le
paquet `tzdata` (fuseaux horaires) si Python ne le fournit pas ; sans lui, le
décalage fixe du Cambodge (UTC+7) est utilisé.

## Après l'installation

1. **Clés API** — ouvrez `.env` et renseignez :
   - `GOOGLE_TTS_API_KEY` : [guide Google Cloud Text-to-Speech](GOOGLE_CLOUD_TTS.md) ;
   - `AZURE_SPEECH_KEY` et `AZURE_SPEECH_REGION` : [guide Azure AI Speech](AZURE_SPEECH_KHMER.md).
2. **Profils et personnages** (facultatif) — dans `config/config.json`, la
   rubrique `profiles` règle les profils FR, ENG et KH, et la rubrique
   `characters` les deux personnages des dialogues (prénom en lettres latines
   et en khmer, genre `"f"` ou `"m"`, qui détermine la particule de politesse
   `ចាស` ou `បាទ`). Voir [CONFIGURATION.md](CONFIGURATION.md).
3. **Essai des voix** :
   ```bash
   python3 manage.py tts status     # fournisseurs et voix configurés
   python3 manage.py tts test       # synthétise une phrase d'essai par langue
   ```
4. **Première leçon** :
   ```bash
   ./scripts/run.sh --open          # Windows : scripts\run.bat --open
   ```
5. **Vérification** : `python3 manage.py check`

## Activer la génération automatique

```bash
python3 manage.py schedule install     # active
python3 manage.py schedule show        # affiche l'état et la commande planifiée
python3 manage.py schedule remove      # désactive
```

| Système | Mécanisme utilisé |
| --- | --- |
| Linux avec cron actif | une ligne dans la crontab de l'utilisateur |
| Linux sans cron (Arch, Fedora…) | une minuterie systemd utilisateur (`fr-kh-learning.timer`) |
| Windows | une tâche du Planificateur de tâches, « FR-KH Learning », sans fenêtre |

Pour forcer un mécanisme : `--method cron`, `--method systemd` ou
`--method windows`.

La tâche s'exécute toutes les 15 minutes et lance `manage.py daily`. Tant qu'il
n'est pas 07h00 à Phnom Penh, ou si la leçon du jour existe déjà, elle ne fait
rien. Conséquences pratiques :

- un ordinateur éteint à 07h00 génère la leçon dès qu'il est rallumé ;
- une génération interrompue (coupure de courant) est reprise à l'exécution
  suivante, sans doublon ;
- les audios restés en attente (panne du fournisseur, clé absente) sont
  retentés au plus une fois par heure ;
- la base est sauvegardée une fois par jour dans `database/backups/`.

L'heure et le fuseau se règlent dans `config/config.json` (`schedule.time`,
`schedule.timezone`). L'heure est toujours interprétée dans ce fuseau, quel que
soit celui de l'ordinateur.

Sous Linux avec systemd, pour que la minuterie tourne aussi quand aucune
session n'est ouverte : `loginctl enable-linger $USER`.

## Consulter le site

- **Sur l'ordinateur** : ouvrez `index.html` (double-clic). Aucun serveur n'est
  nécessaire.
- **Sur un téléphone ou une tablette du même réseau Wi-Fi** :
  ```bash
  python3 manage.py serve --host 0.0.0.0 --port 8000
  ```
  puis ouvrez `http://<adresse IP de l'ordinateur>:8000/`. Ce serveur ne
  distribue que le site (jamais `.env`, la base ni la configuration).
- **Copie autonome** : `python3 manage.py export` crée une archive ZIP
  contenant le site complet, à copier sur une clé USB ou un autre appareil.

Dans la page, le bouton « Réglages » (globe, en haut à droite) choisit le profil
(FR, ENG ou KH), les langues affichées et la taille du texte ; le bouton de
vitesse (« 1× ») passe la lecture audio en « 0,75× ».

## Mettre à jour ou déplacer le projet

Tout est contenu dans le dossier du projet. Pour le déplacer : copiez le
dossier entier, puis relancez `python3 manage.py schedule install` pour que la
tâche planifiée pointe vers le nouvel emplacement.

Pour repartir de zéro : supprimez
`database/learning.db`, le contenu de `lessons/`, de `data/` et `index.html`,
puis lancez `python3 manage.py init`. La bibliothèque `audio/` peut être
conservée : les fichiers valides sont reconnus et réutilisés sans nouvel appel.

## Désinstaller

```bash
python3 manage.py schedule remove
```

puis supprimez le dossier du projet.
