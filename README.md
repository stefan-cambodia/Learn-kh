# FR-KH Learning

Une leçon de moins de dix minutes, chaque matin, en **français**, **anglais** et
**khmer** (ភាសាខ្មែរ). Chacun choisit son profil selon sa langue, en haut de la
page :

- **FR** — interface et explications en français ; on apprend le khmer et
  l'anglais, avec une translittération du khmer.
- **ENG** — interface et explications en anglais ; on apprend le khmer et le
  français, avec la même translittération.
- **KH** — interface et explications en khmer ; on apprend le français et
  l'anglais.

Les profils se règlent dans `config/config.json` (rubrique `profiles`, voir
[docs/CONFIGURATION.md](docs/CONFIGURATION.md)).

Chaque mot, phrase et réplique existe aussi en **espagnol**, **italien**,
**russe** (avec une translittération latine) et **chinois mandarin** (avec le
pinyin), chacun avec son audio. Le sélecteur **Langues**, en haut de chaque page,
affiche ou masque chacune des sept langues ; le choix est gardé par le navigateur.

Chaque jour à 07h00 (heure du Cambodge), le système choisit le thème suivant du
programme, compose la leçon, ajoute les révisions espacées, génère les fichiers
fichiers audio manquants, écrit la page HTML et met à jour l'index. Le site obtenu
est entièrement local : il se consulte sans connexion Internet.

## Démarrage rapide

```bash
./scripts/install.sh          # Linux / macOS      (Windows : scripts\install.bat)
nano .env                     # clés API : voir docs/GOOGLE_CLOUD_TTS.md et docs/AZURE_SPEECH_KHMER.md
nano config/config.json       # profils et personnages des dialogues (facultatif)
python3 manage.py tts test    # essai des trois voix
./scripts/run.sh --open       # première leçon, puis ouverture du site
```

Ensuite, il suffit d'ouvrir `index.html` chaque jour. Sans clé API, les leçons
sont créées quand même : l'audio est marqué « pas encore disponible » et sera
généré automatiquement dès que les clés seront en place.

## Ce que contient une leçon

| Partie | Durée | Contenu |
| --- | --- | --- |
| 1. Vocabulaire | ≈ 3 min | 6 mots nouveaux (5 à 8) : sept langues, catégorie, explication, exemple, audio |
| 2. Expressions pratiques | ≈ 2 min | 4 expressions utiles (3 à 5) |
| 3. Phrases de la vie quotidienne | ≈ 2 min | 3 phrases complètes, en situation |
| 4. Petit dialogue | ≈ 2 min | un échange entre deux personnages (Dara et Alex), écoute enchaînée, jeu de rôle |
| 5. Révision | ≈ 1 min | mots à revoir (J+1, J+3, J+7, J+14, J+30), 3 questions, traduction, compréhension, réponses masquées |

Le programme fourni compte **30 unités** (12 de niveau débutant, 12 de niveau
élémentaire, 6 de niveau intermédiaire), soit 300 mots et expressions. Quand il
est terminé, le système compose des leçons de révision à partir des acquis les
moins bien maîtrisés ; il suffit de déposer de nouvelles unités dans
`content/units/` pour reprendre la progression (voir `content/README.md`).

## Voix et audio

| Langue | Locale | Fournisseur par défaut | Voix par défaut |
| --- | --- | --- | --- |
| Français | `fr-FR` | Google Cloud Text-to-Speech | `fr-FR-Neural2-F` |
| Anglais | `en-US` (ou `en-GB`) | Google Cloud Text-to-Speech | `en-US-Neural2-F` |
| Khmer | `km-KH` | Azure AI Speech | `km-KH-SreymomNeural` |
| Espagnol | `es-ES` | Google Cloud Text-to-Speech | `es-ES-Neural2-A` |
| Italien | `it-IT` | Google Cloud Text-to-Speech | `it-IT-Neural2-A` |
| Russe | `ru-RU` | Google Cloud Text-to-Speech | `ru-RU-Wavenet-A` |
| Chinois | `zh-CN` | Google Cloud Text-to-Speech | `cmn-CN-Wavenet-A` |

**Google Cloud Text-to-Speech ne propose aucune voix khmère.** Le khmer est donc
confié à l'API officielle Azure AI Speech, derrière la même couche
d'abstraction (`frkh/audio/providers/`). Avec la seule clé Azure, les trois
langues fonctionnent ; un moteur local (Piper, etc.) peut aussi être branché.

Chaque fichier est un MP3 mono (`"format": "mp3"`, environ huit fois plus léger,
recommandé pour un site publié ; nécessite ffmpeg) ou un WAV PCM mono 16 bits
(24 000 Hz par défaut, 22 050 Hz au choix), rangé sous un nom déterministe :

```
audio/fr-FR/bonjour_6688f0a282ea.mp3
            └ texte ┘└ début de l'empreinte SHA-256 ┘
```

L'empreinte couvre le texte, la langue, la locale, le fournisseur, la voix, la
vitesse, la hauteur, le format audio et la version du moteur. Un même texte
prononcé avec les mêmes paramètres n'est donc synthétisé **qu'une seule fois**,
quel que soit le nombre de leçons qui l'utilisent.

## Commandes principales

```bash
python3 manage.py generate                    # leçon du jour, tout de suite
python3 manage.py generate --date 2026-12-01  # leçon d'une date donnée
python3 manage.py render --all                # régénérer les pages HTML et l'index
python3 manage.py audio verify                # contrôler tous les fichiers audio
python3 manage.py audio missing               # lister les audios manquants
python3 manage.py audio repair                # régénérer uniquement les manquants ou corrompus
python3 manage.py audio regen --text "bonjour" --lang fr
python3 manage.py audio convert --format mp3  # convertir toute la bibliothèque (MP3 ⇄ WAV), sans appel TTS
python3 manage.py stats                       # appels TTS, cache, volume de la bibliothèque
python3 manage.py export                      # archive ZIP de toutes les leçons
python3 manage.py check                       # vérification générale du projet
python3 manage.py schedule install            # activer la génération quotidienne
python3 manage.py serve --host 0.0.0.0        # consulter le site depuis un téléphone (progression partagée entre appareils)
python3 manage.py alphabet                    # Alphabets (khmer, latin, cyrillique, chinois) : audios et page
                                              # téléphone : « Ajouter à l'écran d'accueil » installe le site comme une application
```

La liste complète est dans [docs/ADMINISTRATION.md](docs/ADMINISTRATION.md).

## Organisation du projet

```
index.html            page d'accueil : statistiques, recherche, liste des leçons
alphabet.html         module Alphabets : khmer, latin, cyrillique, tons et caractères chinois, avec audio
revision.html         cartes mémoire du vocabulaire des leçons passées (régénérée avec l'index)
lexique.html          tous les mots et expressions vus, avec recherche et audio
lessons/              une page par leçon (lesson-001.html, …)
audio/                bibliothèque audio : fr-FR/, en-US/, km-KH/, es-ES/, it-IT/, ru-RU/, zh-CN/
css/  js/  fonts/     style, comportement, police Noto Sans Khmer embarquée
data/                 lessons.json, vocabulary.json, audio-library.json
database/             learning.db (SQLite) et backups/
config/config.json    configuration personnalisable
.env                  clés API (jamais copiées dans le site)
logs/                 app.log, errors.log, cron.log
content/units/        programme pédagogique : une unité par fichier JSON
content/alphabets.json  données du module Alphabets (consonnes, voyelles, lettres, accents)
templates/            gabarits HTML des pages
frkh/                 code de l'application (Python, sans dépendance externe)
scripts/              installation et lancement manuel (Linux et Windows)
tests/                tests automatiques
docs/                 documentation
manage.py             ligne de commande
```

## Documentation

- [Installation](docs/INSTALLATION.md) — Linux, Windows, planification, accès depuis un téléphone
- [Google Cloud Text-to-Speech](docs/GOOGLE_CLOUD_TTS.md) — clé API pour le français et l'anglais
- [Azure AI Speech](docs/AZURE_SPEECH_KHMER.md) — clé pour les voix khmères
- [Configuration](docs/CONFIGURATION.md) — tous les réglages de `config/config.json`
- [Administration](docs/ADMINISTRATION.md) — commandes, corrections manuelles, dépannage
- [Rédiger des unités](content/README.md) — format du programme pédagogique

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Les tests créent des projets temporaires et n'utilisent ni clé API ni réseau :
un moteur vocal factice (`tests/fake_tts.py`) produit de vrais fichiers WAV, et
de faux serveurs HTTP vérifient les requêtes envoyées à Google et à Azure. Si
Node.js et Firefox sont installés, le site est aussi contrôlé dans un vrai
navigateur (lecture des audios, police khmère, recherche, absence de requête
réseau) : `node tests/browser_check.mjs <dossier du site>`.

## Licences

La police Noto Sans Khmer est distribuée sous licence SIL Open Font License
(`fonts/OFL.txt`). Les fichiers audio sont produits par les services de synthèse
vocale que vous configurez : leur conservation et leur réutilisation relèvent
des conditions d'utilisation de ces services (Google Cloud, Microsoft Azure).
