# Configuration

Deux fichiers :

- `.env` — les clés API (secret, jamais publié) ;
- `config/config.json` — tous les autres réglages. Il est créé par
  `python3 manage.py init` avec les valeurs par défaut ; une valeur absente du
  fichier reprend sa valeur par défaut.

Après une modification : `python3 manage.py check` signale les valeurs
invalides.

## Clés API (`.env`)

| Variable | Rôle |
| --- | --- |
| `GOOGLE_TTS_API_KEY` | clé Google Cloud Text-to-Speech (français, anglais) |
| `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_CLOUD_PROJECT` | variante par compte de service |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | clé et région Azure AI Speech (khmer) |

Une variable déjà définie dans l'environnement du système l'emporte sur `.env`.

## Profils (`profiles`)

Un profil par langue de l'apprenant : c'est la langue de l'interface et des
explications. Le bouton « Réglages » (globe, en haut à droite de chaque page)
propose les profils dans l'ordre de cette rubrique, sous « Ma langue ». Dans une
fiche, la langue de l'apprenant sert de titre ; viennent ensuite les langues de
`learns`, dans l'ordre, puis les autres.

```json
"profiles": {
  "fr": {"label": "FR", "learns": ["km", "en"]},
  "en": {"label": "ENG", "learns": ["km", "fr"]},
  "km": {"label": "KH", "learns": ["fr", "en"]}
}
```

- La clé (`fr`, `en`, `km`) est la langue de l'apprenant. Seules ces trois
  langues ont une interface traduite ; un nouveau profil demande de traduire
  l'interface (`frkh/render.py`, `js/app.js`, `js/review.js`) et les
  explications des unités.
- `label` : le texte du bouton.
- `learns` : les langues étudiées, la principale en premier (jeu de rôle,
  compteur « à réviser aujourd'hui », langue proposée d'abord dans « Réviser »).

La progression (leçons terminées, cartes mémoire, série de jours) est gardée
séparément pour chaque profil.

## Personnages des dialogues (`characters`)

```json
"characters": {
  "A": {"name": {"latin": "Dara", "km": "ដារ៉ា", "tr": "da-ra"}, "gender": "f"},
  "B": {"name": {"latin": "Alex", "km": "អាឡិច", "tr": "a-lech"}, "gender": "m"}
}
```

- `A` et `B` sont les deux personnages des dialogues (`{A}` et `{B}` dans les
  unités). Ils n'ont aucun lien avec les profils.
- `name.latin` et `name.km` : le prénom tel qu'il apparaît dans les textes
  français et anglais, et dans les textes khmers. `name.tr` (facultatif) :
  sa translittération dans les aides de lecture.
- `gender` : `"f"` ou `"m"`. Il fixe la particule de politesse khmère du
  personnage (`ចាស` pour une femme, `បាទ` pour un homme).

Les prénoms sont inscrits dans les leçons au moment de leur création. Après
les avoir changés ici, reportez-les dans les leçons déjà générées (les audios
manquants sont créés, puis les pages refaites) :

```bash
python3 manage.py content refresh
python3 manage.py audio prune          # supprime les audios des anciennes répliques
```

L'ancienne rubrique `learners` est encore lue si `characters` est absente.

## Planification (`schedule`)

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `time` | `"07:00"` | heure à partir de laquelle la leçon du jour est générée |
| `timezone` | `"Asia/Phnom_Penh"` | fuseau dans lequel cette heure et la date du jour sont interprétées |
| `check_every_minutes` | `15` | fréquence de la tâche planifiée (relancer `schedule install` après modification) |

## Leçon (`lesson`)

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `new_words` | `6` | mots nouveaux par leçon (5 à 8) |
| `expressions` | `4` | expressions par leçon (3 à 5) |
| `sentences` | `3` | phrases de la vie quotidienne |
| `max_duration_minutes` | `10` | durée maximale ; le nombre de mots puis d'expressions est réduit si la leçon la dépasserait |
| `level` | `"auto"` | `auto` suit le programme dans l'ordre ; `debutant`, `elementaire` ou `intermediaire` restreint aux unités de ce niveau |
| `themes` | `[]` | thèmes à traiter en priorité, par exemple `["au-marche", "chez-le-medecin"]` (identifiants de `content/units/`) |

## Révision espacée (`review`)

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `intervals_days` | `[1, 3, 7, 14, 30]` | échéances de révision après l'apprentissage d'un mot |
| `max_items` | `10` | nombre maximal de mots revus par leçon |

Une leçon ne dure que dix minutes : chaque jour, la partie « Révision » présente
au plus `max_items` mots arrivés à échéance, choisis à tour de rôle parmi les
échéances (ceux d'hier, d'il y a 3 jours, 7 jours…), en commençant par les
moins révisés. Les mots non présentés restent en file d'attente. Un mot est
considéré comme acquis après la dernière échéance ; il n'est alors plus
proposé. Suivi : `python3 manage.py progress show`.

## Langues et voix (`languages`)

```json
"languages": {
  "fr": {"locale": "fr-FR", "provider": "google", "voice": "fr-FR-Neural2-F",
         "fallback": {"provider": "azure", "voice": "fr-FR-DeniseNeural"}},
  "en": {"locale": "en-US", "provider": "google", "voice": "en-US-Neural2-F",
         "fallback": {"provider": "azure", "voice": "en-US-JennyNeural"}},
  "km": {"locale": "km-KH", "provider": "azure", "voice": "km-KH-SreymomNeural"},
  "es": {"locale": "es-ES", "provider": "google", "voice": "es-ES-Neural2-A"},
  "it": {"locale": "it-IT", "provider": "google", "voice": "it-IT-Neural2-A"},
  "ru": {"locale": "ru-RU", "provider": "google", "voice": "ru-RU-Wavenet-A"},
  "zh": {"locale": "zh-CN", "provider": "google", "voice": "cmn-CN-Wavenet-A"}
}
```

- `fr`, `en`, `km` sont les langues des profils (obligatoires). `es` (espagnol),
  `it` (italien), `ru` (russe) et `zh` (chinois mandarin) sont des langues
  supplémentaires : retirer l'une d'elles de `languages` la fait disparaître des
  pages et arrête la génération de ses audios.
- `locale` : `fr-FR`, `en-US` ou `en-GB`, `km-KH`, `es-ES`, `it-IT`, `ru-RU`,
  `zh-CN`. Elle détermine aussi le dossier de rangement (`audio/en-GB/…`).
- `provider` : `google`, `azure` ou `command`.
- `voice` : nom exact de la voix (`python3 manage.py tts voices --lang fr`).
- `fallback` : fournisseur de secours, utilisé seulement si le fournisseur
  principal n'est pas configuré (clé absente). `null` pour le désactiver.
- `speaking_rate`, `pitch` (facultatifs) : réglages propres à une langue, qui
  remplacent ceux de la rubrique `audio`.

## Audio (`audio`)

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `format` | `"wav"` | `"mp3"` (environ huit fois plus léger, recommandé pour un site publié ; nécessite ffmpeg) ou `"wav"` |
| `mp3_bitrate_kbps` | `48` | débit des fichiers MP3 (mono) |
| `sample_rate_hz` | `24000` | fréquence d'échantillonnage : `24000` ou `22050` |
| `speaking_rate` | `0.9` | vitesse de lecture (1.0 = normale ; 0.5 à 1.5) |
| `pitch` | `0.0` | hauteur de la voix, en demi-tons |
| `include_examples` | `true` | générer aussi l'audio des phrases d'exemple du vocabulaire |

Les fichiers sont des MP3 mono ou des WAV PCM mono 16 bits. Pour changer de
format sans rien demander au fournisseur vocal, modifiez `format` puis lancez
`python3 manage.py audio convert` : chaque fichier est converti, vérifié, puis
l'ancien est supprimé. Modifier un autre réglage change l'empreinte des audios :
de nouveaux fichiers sont générés, les anciens restent jusqu'à
`python3 manage.py audio prune`.

## Langues affichées (`display`)

```json
"display": {"languages": ["fr", "en", "km", "es", "it", "ru", "zh"]}
```

Langues visibles à la première visite. Chacun peut ensuite cocher ou décocher
des langues dans les réglages (« Langues affichées ») ; ce choix est gardé
par le navigateur. Une langue masquée disparaît des leçons, du lexique, des
cartes de révision et de la page Alphabets.

## Synthèse vocale (`tts`)

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `timeout_seconds` | `30` | délai maximal d'un appel |
| `retries` | `3` | tentatives en cas de panne passagère (réseau, erreur 429 ou 5xx) |
| `retry_backoff_seconds` | `2.0` | attente avant la 2e tentative, doublée à chaque fois |
| `limits.max_calls_per_run` | `400` | appels maximum par exécution |
| `limits.max_chars_per_day` | `20000` | caractères maximum par jour |
| `limits.max_chars_per_month` | `300000` | caractères maximum par mois |

Une limite à `0` est désactivée. Quand une limite est atteinte, la leçon est
publiée et les audios restants sont reportés à une exécution ultérieure. Une
leçon consomme environ 1 700 caractères (2 400 au plus) : les valeurs par
défaut laissent une large marge tout en bornant la dépense en cas d'erreur.

Un fournisseur dont la clé est refusée, ou qui échoue pour deux textes de
suite, est mis en pause jusqu'à l'exécution suivante.

### Fournisseur `command` (moteur vocal local)

Tout moteur pilotable en ligne de commande peut remplacer un service en ligne.
Exemple avec Piper, entièrement hors ligne :

```json
"languages": {
  "fr": {"locale": "fr-FR", "provider": "command", "voice": "/chemin/fr_FR-siwis-medium.onnx", "fallback": null}
},
"tts": {"providers": {"command": {
  "command": ["piper", "--model", "{voice}", "--output_file", "{output}"],
  "output_format": "wav",
  "engine_version": "piper-1.2"
}}}
```

Le texte est transmis sur l'entrée standard. Variables disponibles dans la
commande : `{text}`, `{output}`, `{voice}`, `{locale}`, `{lang}`, `{rate}`,
`{pitch}`, `{sample_rate}`. Le résultat est converti en WAV PCM mono 16 bits à
la fréquence configurée (ffmpeg est nécessaire si le moteur produit un format
compressé). `engine_version` entre dans l'empreinte des fichiers : changez-la
quand vous changez de moteur ou de modèle.

## Autres rubriques

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `site.title` | `"FR-KH Learning"` | titre du site |
| `site.default_profile` | `"fr"` | profil affiché à la première visite (`fr`, `en` ou `km`) |
| `backup.keep` | `14` | nombre de sauvegardes quotidiennes de la base conservées |
| `logging.level` | `"INFO"` | niveau de détail des journaux |
| `logging.max_bytes`, `logging.backups` | `1048576`, `5` | rotation des fichiers de `logs/` |

## Apparence

- `templates/` : gabarits HTML (variables `$nom`). `python3 manage.py render --all`
  applique une modification à toutes les pages.
- `css/style.css` : une couleur par langue (variables `--fr`, `--en`, `--km`,
  `--es`, `--it`, `--ru`, `--zh` en tête de fichier), thème clair et thème sombre
  automatiques.
- `fonts/` : police Noto Sans Khmer embarquée, pour un affichage correct du
  khmer sans connexion, et Fraunces (titres), pour le même rendu sur tous les
  appareils.
