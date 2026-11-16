# Programme pédagogique — guide de rédaction

Chaque fichier `content/units/uNNN-theme.json` est une **unité** : la matière
d'une leçon de moins de 10 minutes. Le générateur quotidien prend la prochaine
unité non utilisée, y ajoute les révisions espacées, puis produit la page HTML
et les fichiers audio.

Pour ajouter des leçons, il suffit de déposer de nouveaux fichiers ici puis de
lancer `python3 manage.py content check`.

## Les deux apprenants

- **A** : la personne khmère. Elle apprend le français et l'anglais ; ses
  explications sont en khmer (`note.km`, `tip.km`).
- **B** : la personne française. Elle apprend l'anglais et le khmer ; ses
  explications sont en français (`note.fr`, `tip.fr`).

Le dialogue de chaque unité se joue entre A et B.

## Format d'une unité

```json
{
  "id": "u004",
  "order": 4,
  "level": "debutant",
  "theme": "famille",
  "title": {"fr": "La famille", "en": "Family", "km": "គ្រួសារ"},
  "tip": {"fr": "conseil sur le khmer, pour B", "km": "conseil sur le français ou l'anglais, pour A"},
  "vocabulary": [
    {
      "fr": "le père", "en": "father", "km": "ឪពុក", "tr": "eu-pouk", "pos": "nom",
      "note": {"fr": "explication pour B", "km": "explication pour A"},
      "example": {"fr": "…", "en": "…", "km": "…", "tr": "…"}
    }
  ],
  "expressions": [
    {"fr": "…", "en": "…", "km": "…", "tr": "…", "note": {"fr": "…", "km": "…"}}
  ],
  "sentences": [
    {"situation": {"fr": "Au marché", "km": "នៅផ្សារ"}, "fr": "…", "en": "…", "km": "…", "tr": "…"}
  ],
  "dialogue": {
    "setting": {"fr": "…", "en": "…", "km": "…"},
    "lines": [
      {"speaker": "B", "fr": "…", "en": "…", "km": "…", "tr": "…"},
      {"speaker": "A", "fr": "…", "en": "…", "km": "…", "tr": "…"}
    ]
  },
  "comprehension": {
    "question": {"fr": "…", "en": "…", "km": "…"},
    "answer": {"fr": "…", "en": "…", "km": "…"}
  }
}
```

| Section | Quantité | Remarques |
| --- | --- | --- |
| `vocabulary` | 6 (5 à 8) | mots nouveaux, chacun avec `pos`, `note` et `example` |
| `expressions` | 4 (3 à 5) | formules utiles, avec `note` |
| `sentences` | 3 | phrases complètes de la vie réelle, avec `situation` |
| `dialogue.lines` | 5 ou 6 (4 à 8) | A et B parlent tous les deux |
| `comprehension` | 1 | question sur le dialogue, et sa réponse |

`level` : `debutant`, `elementaire` ou `intermediaire`.
`pos` : `nom`, `verbe`, `adjectif`, `adverbe`, `pronom`, `interjection`, `nombre`,
`preposition`, `conjonction`, `particule`, `interrogatif`, `expression`.

## Règles de rédaction

1. **Naturel avant littéral.** Écrire ce qu'un locuteur natif dit réellement dans
   la situation, dans les trois langues. Le khmer est celui de la conversation
   courante et polie, pas un calque du français.
2. **Khmer en caractères khmers**, orthographe standard, phrases terminées par
   `។`, `?` ou `!`. Pas d'espace insécable ni d'espace de largeur nulle.
3. **En cas de doute, le dire.** Ajouter `"uncertain": true` et
   `"uncertain_note": "ce qui est à vérifier"` sur l'entrée. La leçon affichera
   « à vérifier » au lieu de présenter la traduction comme sûre.
4. **Noms français avec leur article** (`le père`, `la maison`, `l'eau`) pour
   apprendre le genre ; verbes à l'infinitif (`manger` / `to eat`) ; noms anglais
   sans article.
5. **Progressivité.** Phrases courtes au niveau débutant. Réutiliser le
   vocabulaire des unités précédentes dans les exemples, les phrases et le
   dialogue ; éviter d'y glisser des mots jamais vus quand un mot connu suffit.
6. **Pas de doublon** : un mot du `vocabulary` ne doit pas déjà figurer dans le
   `vocabulary` d'une autre unité (voir le programme ci-dessous).
7. **Notes courtes** (une ou deux phrases). `note.fr` explique le khmer ou
   l'anglais à B ; `note.km` explique le français ou l'anglais à A, en khmer
   simple. Une note peut citer un mot d'une autre langue.
8. **Textes destinés à la synthèse vocale** (`fr`, `en`, `km` hors notes) : pas de
   parenthèses, de barres obliques ni d'abréviations ; une seule formulation.
   Exception admise : `បាទ / ចាស` pour « oui ».
9. **Genre des personnages.** Le genre de A et de B est configurable. Préférer
   des tournures neutres quand A ou B parle de soi (« je vais bien », « j'ai
   faim ») plutôt qu'un adjectif dont la prononciation change au féminin.

## Variables

| Variable | Remplacée par | Autorisée dans |
| --- | --- | --- |
| `{A}`, `{B}` | prénom de l'apprenant (latin ou khmer selon la langue) | partout |
| `{A_yes}`, `{B_yes}` | `បាទ` ou `ចាស` selon le genre du locuteur | `km` et `tr` uniquement |

En khmer, on s'adresse volontiers à quelqu'un par son prénom plutôt que par
« tu » : `ចុះ {B} វិញ?` est plus naturel que `ចុះអ្នកវិញ?` entre proches.

## Translittération (`tr`)

Aide de lecture pour un francophone ; elle se lit « à la française ». Minuscules,
syllabes d'un même mot reliées par un tiret, mots séparés par une espace, même
ponctuation que le khmer.

| Son | Notation | Exemple |
| --- | --- | --- |
| /u/ | `ou` | មួយ `mouy`, អរគុណ `â-koun` |
| /ɑ/ (a grave) | `â` | ចង់ `tchâng`, សម្រាប់ `sâm-rap` |
| /e/ | `é` | ទេ `té`, កាហ្វេ `ka-fé` |
| /ae/ | `aè` | កែវ `kaèv`, តែ `taè` |
| /ə/, /ɨ/ | `eu` | ទឹក `teuk`, យើង `yeung`, នៅ `neuv` |
| /aə/ | `aeu` | ហើយ `haeuy`, ច្រើន `tchraeun` |
| /iə/, /eə/ | `éa` | មាន `méan`, អ្នក `néak`, ផ្ទះ `phtéah` |
| /uə/ | `ouo` | សួស្តី `souos-dey`, បួន `bouon` |
| /əj/ | `ey` | បី `bey`, អ្វី `ey` |
| ច, ជ | `tch` | ចង់ `tchâng`, ជួប `tchouop` |
| ឆ, ឈ | `tchh` | ឈ្មោះ `tchhmouh` |
| ញ | `gn` | ខ្ញុំ `khgnom`, ញ៉ាំ `gnam` |
| ង | `ng` | ថ្ងៃ `thngay` |
| aspirées ខ ថ ផ | `kh`, `th`, `ph` | ខ្មែរ `khmaè`, ផ្សារ `phsa` |
| ស final, ះ | `h` | ណាស់ `nah`, នេះ `nih` |
| រ final (muet) | non noté | ពីរ `pi`, ខ្មែរ `khmaè` |

## Programme (ordre de progression)

Les trois premières unités servent de modèle de ton et de niveau de détail.

### Niveau débutant

| Unité | Thème (`theme`) | Titre | Vocabulaire nouveau |
| --- | --- | --- | --- |
| u001 | `salutations` | Les salutations | bonjour, au revoir, merci, oui, non, s'il vous plaît |
| u002 | `se-presenter` | Se présenter | je·moi, vous·tu, le nom, le pays, habiter, l'ami |
| u003 | `nombres-1-5` | Les nombres de 1 à 5 | un, deux, trois, quatre, cinq, zéro |
| u004 | `famille` | La famille | le père, la mère, le mari, la femme (épouse), l'enfant, la famille |
| u005 | `nombres-6-10` | Les nombres de 6 à 10 | six, sept, huit, neuf, dix, combien |
| u006 | `manger-et-boire` | Manger et boire | manger, boire, l'eau, le riz, le café, délicieux |
| u007 | `comment-ca-va` | Comment te sens-tu ? | aller bien, fatigué, avoir faim, avoir soif, content, malade |
| u008 | `a-la-maison` | À la maison | la maison, la chambre, la porte, la table, la chaise, le lit |
| u009 | `jours-et-moments` | Les moments de la journée | aujourd'hui, demain, hier, le matin, le soir, la nuit |
| u010 | `questions` | Les mots pour questionner | quoi, qui, où, quand, pourquoi, comment |
| u011 | `couleurs` | Les couleurs | rouge, bleu, vert, blanc, noir, jaune |
| u012 | `verbes-de-base` | Les verbes de base | aller, venir, vouloir, avoir, aimer, comprendre |

### Niveau élémentaire

| Unité | Thème (`theme`) | Titre | Vocabulaire nouveau |
| --- | --- | --- | --- |
| u013 | `au-marche` | Au marché | le marché, acheter, vendre, le prix, cher, bon marché |
| u014 | `fruits-et-legumes` | Fruits et légumes | le fruit, le légume, la mangue, la banane, la noix de coco, frais |
| u015 | `au-restaurant` | Au restaurant | le restaurant, le menu, commander, le plat, l'addition, épicé |
| u016 | `transports` | Les transports | le tuk-tuk, la voiture, la moto, le bus, la route, conduire |
| u017 | `demander-son-chemin` | Demander son chemin | à gauche, à droite, tout droit, près, loin, tourner |
| u018 | `l-heure` | L'heure | l'heure, la minute, maintenant, en avance, en retard, attendre |
| u019 | `faire-des-achats` | Faire des achats | le magasin, l'argent, payer, la taille, essayer, les vêtements |
| u020 | `chez-le-medecin` | Chez le médecin | le médecin, l'hôpital, le médicament, avoir mal, la tête, le ventre |
| u021 | `a-l-hotel` | À l'hôtel | l'hôtel, la clé, réserver, la serviette, la salle de bain, la climatisation |
| u022 | `meteo` | Le temps qu'il fait | chaud, froid, la pluie, le soleil, le vent, la saison |
| u023 | `routine` | La routine quotidienne | se réveiller, dormir, travailler, cuisiner, se doucher, se reposer |
| u024 | `travail-et-ecole` | Le travail et l'école | le travail, l'école, apprendre, l'enseignant, la langue, difficile |

### Niveau intermédiaire

| Unité | Thème (`theme`) | Titre | Vocabulaire nouveau |
| --- | --- | --- | --- |
| u025 | `raconter-au-passe` | Raconter au passé | déjà, avant, la semaine dernière, finir, se souvenir, le voyage |
| u026 | `projets` | Parler de ses projets | la semaine prochaine, le projet, espérer, peut-être, décider, bientôt |
| u027 | `au-telephone` | Au téléphone | le téléphone, appeler, le message, le numéro, répondre, occupé |
| u028 | `resoudre-un-probleme` | Résoudre un problème | le problème, aider, cassé, réparer, perdre, trouver |
| u029 | `donner-son-avis` | Donner son avis | penser, être d'accord, préférer, important, vrai, se tromper |
| u030 | `fetes-et-traditions` | Fêtes et traditions | la fête, le Nouvel An khmer, la pagode, le cadeau, inviter, ensemble |
| u031 | `le-corps` | Le corps | la main, le pied, les yeux, la bouche, le dos, les cheveux |
| u032 | `animaux` | Les animaux | l'animal, le chien, le chat, le poisson, l'oiseau, la vache |
| u033 | `decrire-quelqu-un` | Décrire quelqu'un | grand, petit, jeune, âgé, gentil, drôle |
| u034 | `emotions` | Les émotions | triste, en colère, avoir peur, surpris, s'ennuyer, pleurer |
| u035 | `en-ville` | En ville | la ville, la banque, la poste, la pharmacie, le parc, traverser |
| u036 | `a-la-campagne` | À la campagne | la campagne, la rizière, l'arbre, le fleuve, la montagne, le village |
| u037 | `cuisiner-ensemble` | Cuisiner ensemble | couper, faire frire, le sel, le sucre, l'œuf, la sauce de poisson |
| u038 | `le-menage` | Le ménage | nettoyer, faire la lessive, balayer, faire la vaisselle, sale, propre |
| u039 | `loisirs` | Les loisirs | la musique, chanter, danser, lire, le film, le sport |
| u040 | `la-vie-a-deux` | La vie à deux | l'amour, manquer, se marier, le cœur, la confiance, promettre |
| u041 | `noel` | Noël | Noël, le sapin, la neige, souhaiter, la bougie, le repas |
| u042 | `famille-elargie` | La famille élargie | le grand frère, la petite sœur, le grand-père, la grand-mère, l'oncle, la tante |
| u043 | `les-saveurs` | Les saveurs | sucré, salé, acide, amer, gras, fade |
| u044 | `s-habiller` | S'habiller | la chemise, le pantalon, la jupe, les chaussures, le chapeau, s'habiller |
| u045 | `voyager-en-avion` | Voyager en avion | l'avion, l'aéroport, le passeport, le billet, la valise, arriver |
| u046 | `mois-et-dates` | Les mois et les dates | le mois, l'année, la semaine, la date, l'anniversaire, le calendrier |
| u047 | `les-pieces` | Les pièces de la maison | la cuisine, le salon, la fenêtre, le jardin, l'escalier, le toit |
| u048 | `internet` | Internet et ordinateur | l'ordinateur, internet, la photo, envoyer, le mot de passe, la batterie |
| u049 | `politesse` | La politesse et les coutumes | saluer, poli, respecter, la coutume, l'invité, les aînés |
| u050 | `apprendre-une-langue` | Apprendre une langue | le mot, la phrase, prononcer, écrire, traduire, s'entraîner |

Aux niveaux élémentaire et intermédiaire, les phrases s'allongent ; au niveau
intermédiaire, le dialogue compte 6 à 8 répliques et les notes abordent les
temps (passé avec `បាន` / `ហើយ`, futur avec `នឹង`, et leurs équivalents français
et anglais).
