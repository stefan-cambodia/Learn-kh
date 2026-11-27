# Administration

Toutes les commandes se lancent depuis le dossier du projet :

```bash
python3 manage.py <commande> [options]      # Windows : python manage.py …
python3 manage.py --help
python3 manage.py <commande> --help
```

Code de retour : `0` succès, `1` erreur, `2` une autre génération est déjà en
cours (verrou).

## Leçons

| Commande | Effet |
| --- | --- |
| `generate` | génère la leçon du jour immédiatement (sans attendre 07h00) |
| `generate --date 2026-12-01` | génère la leçon d'une date donnée |
| `generate --force` | repasse sur une leçon existante (audio manquant, page), sans la dupliquer |
| `generate --no-audio` | crée la leçon sans appeler la synthèse vocale |
| `daily` | tâche planifiée : sauvegarde, reprise des leçons interrompues, leçon du jour si l'heure est passée, nouvelle tentative pour les audios en attente |
| `daily --now` | la même chose, sans attendre l'heure configurée |
| `lesson list` | liste des leçons, avec leur état |
| `render 12` | régénère la page HTML de la leçon 12 (et l'index) |
| `render --all` | régénère toutes les pages, l'index et les fichiers de `data/` |
| `export` | archive ZIP autonome : site complet et une fiche JSON par leçon (`--no-audio` pour l'alléger, `--out dossier`) |

Une seule leçon peut exister par date : relancer `generate` pour une date déjà
traitée ne crée rien. Une leçon dont la génération a été interrompue reste à
l'état « brouillon », n'apparaît pas dans l'index et est terminée à
l'exécution suivante.

## Audio

| Commande | Effet |
| --- | --- |
| `audio verify` | contrôle chaque fichier (présence, format WAV PCM mono 16 bits, fréquence, durée, silence) ; `--deep` compare aussi l'empreinte du contenu ; `--fix` répare dans la foulée |
| `audio missing` | liste les audios manquants ou corrompus, avec la raison |
| `audio repair` | régénère **uniquement** les audios manquants ou corrompus, puis met les pages à jour (`--lesson 12` pour une seule leçon) |
| `audio regen --text "bonjour" --lang fr` | régénère un audio précis (aussi : `--file nom.wav` ou `--hash début-de-l'empreinte`) |
| `audio prune` | supprime les audios qui ne servent plus à aucune leçon (`--dry-run` pour voir sans supprimer) |
| `tts status` | fournisseurs, voix configurées, consommation du jour et du mois |
| `tts voices --lang km` | voix proposées par le fournisseur pour une langue |
| `tts test` | synthétise une phrase d'essai par langue |

Un fichier audio valide n'est jamais écrasé par une tentative ratée : le nouveau
fichier est écrit à part, contrôlé, puis mis en place d'un seul coup.

## Statistiques et vérification

| Commande | Effet |
| --- | --- |
| `stats` | leçons publiées, mots appris, **appels TTS effectués**, **audios réutilisés depuis le cache**, **volume de la bibliothèque audio**, progression (`--json` pour une sortie exploitable) |
| `check` | vérification générale : configuration, clés, base, programme, pages, audio, fonctionnement hors ligne, absence de clé dans le site, planification (`--deep` pour un contrôle audio approfondi) |
| `progress show` | maîtrise par profil (fr, en, km) et prochaines révisions |
| `progress forget --learner km --word "merci"` | remet un mot à zéro : il sera revu dès demain (`--learner all` : tous les profils) |
| `progress master --learner fr --word "merci"` | marque un mot comme acquis : il ne sera plus proposé |
| `content refresh` | reporte les unités modifiées (explications, dialogues, prénoms des personnages) dans les leçons déjà générées |
| `backup` | sauvegarde immédiate de la base dans `database/backups/` |
| `schedule show` / `install` / `remove` | planification quotidienne |
| `serve` | serveur web avec comptes utilisateurs (`--host 0.0.0.0` pour le réseau local ; `--no-accounts` pour l'ancien serveur ouvert) : voir [COMPTES.md](COMPTES.md) |
| `users list` / `show` / `add` / `password` / `role` / `disable` / `enable` / `logout` / `delete` | comptes du serveur : voir [COMPTES.md](COMPTES.md) |
| `users invite` / `users reset-link <identifiant>` | lien à usage unique : invitation à créer son compte, ou choix d'un nouveau mot de passe |
| `users journal` | journal des comptes : connexions, échecs, opérations (`--type`, `--limit`, ou un identifiant) |

## Corriger un contenu

Les traductions fournies ont été rédigées avec soin, mais aucune relecture par
un locuteur natif n'a eu lieu. Les entrées jugées incertaines portent la
mention « à vérifier » dans les pages ; `python3 manage.py content check --all`
en donne la liste.

**Remplacer un texte partout** (leçons déjà générées, vocabulaire, unités
sources) :

```bash
python3 manage.py correct --find "texte fautif" --replace "texte corrigé" --lang km --dry-run
python3 manage.py correct --find "texte fautif" --replace "texte corrigé" --lang km
```

`--lang` vaut `fr`, `en`, `km` ou `tr` (translittération) ; `--lesson 12` limite
à une leçon. Les pages sont refaites et seul l'audio du texte modifié est
généré.

**Retoucher une leçon entière** :

```bash
python3 manage.py lesson export 12            # crée exports/lesson-012.json
# … modifier le fichier …
python3 manage.py lesson import exports/lesson-012.json
```

**Lever une mention « à vérifier »** : dans l'unité concernée
(`content/units/`), supprimez `"uncertain": true` et `"uncertain_note"`, ou,
pour une leçon déjà générée, faites-le par `lesson export` / `lesson import`.

## Ajouter des leçons au programme

Déposez de nouveaux fichiers `uNNN-theme.json` dans `content/units/` en suivant
le guide `content/README.md`, puis :

```bash
python3 manage.py content check     # 0 erreur attendu
python3 manage.py content list      # ordre de passage
```

Une unité qui contient une erreur de structure (texte manquant, khmer écrit en
lettres latines, signe khmer mal placé…) est écartée : elle ne sera jamais
servie telle quelle.

## Sauvegardes et reprise

- La tâche quotidienne copie la base une fois par jour dans
  `database/backups/` et conserve les 14 dernières copies (`backup.keep`).
- Pour restaurer : arrêtez la planification, remplacez `database/learning.db`
  par la copie voulue, puis lancez `python3 manage.py render --all`. Les
  fichiers audio présents sur le disque sont reconnus et réutilisés.
- Un verrou (`database/.generation.lock`) empêche deux générations
  simultanées ; il est libéré par le système si le processus s'arrête
  brutalement.

## Journaux

| Fichier | Contenu |
| --- | --- |
| `logs/app.log` | toutes les opérations (étapes de génération, audios créés) |
| `logs/errors.log` | avertissements et erreurs uniquement |
| `logs/cron.log` | sortie de la tâche planifiée (Linux, cron) |

Les journaux tournent automatiquement (1 Mo, 5 fichiers). Ils ne contiennent
jamais les clés API.

## Dépannage

| Symptôme | À faire |
| --- | --- |
| « Audio pas encore disponible » dans une page | `python3 manage.py tts status`, puis `audio missing` pour la raison, puis `audio repair` |
| La leçon du jour n'apparaît pas | `python3 manage.py schedule show` (planification installée ?), `logs/errors.log`, puis `python3 manage.py daily --now` |
| Un audio est mal prononcé | corrigez le texte (`correct`), ou régénérez-le après avoir changé de voix (`audio regen`) |
| Le khmer s'affiche en carrés | vérifiez que le dossier `fonts/` accompagne bien le site (`check` le signale) |
| Le profil n'est pas mémorisé | certains navigateurs isolent le stockage des fichiers ouverts depuis le disque : le profil suit alors les liens de page en page ; avec `manage.py serve`, il est mémorisé |
| « Une génération est déjà en cours » | une autre exécution tourne ; attendez sa fin |
| Message « limite quotidienne … atteinte » | normal après une grosse régénération : la suite sera traitée le lendemain, ou relevez `tts.limits` |
