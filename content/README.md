# Programme pédagogique — guide de rédaction

Chaque fichier `content/units/uNNN-theme.json` est une **unité** : la matière
d'une leçon de moins de 10 minutes. Le générateur quotidien prend la prochaine
unité non utilisée, y ajoute les révisions espacées, puis produit la page HTML
et les fichiers audio.

Pour ajouter des leçons, il suffit de déposer de nouveaux fichiers ici puis de
lancer `python3 manage.py content check`.

## Les trois profils

Chaque explication existe dans la langue de chaque profil :

- `fr` : le profil francophone apprend le khmer et l'anglais (`note.fr`, `tip.fr`) ;
- `en` : le profil anglophone apprend le khmer et le français (`note.en`, `tip.en`) ;
- `km` : le profil khmer apprend le français et l'anglais (`note.km`, `tip.km`).

Le dialogue de chaque unité se joue entre deux personnages, A et B (Dara et
Alex par défaut, voir `characters` dans la configuration).

## Les langues supplémentaires

Chaque texte à apprendre (mot, exemple, expression, phrase, réplique) existe
aussi en **espagnol** (`es`), **italien** (`it`), **russe** (`ru`, en cyrillique)
et **chinois mandarin** (`zh`, en caractères simplifiés), avec le **pinyin**
(`zh_tr`). La translittération latine du russe est calculée automatiquement
(`ru_tr` permet de l'imposer). Les explications (`note`, `tip`), les titres, les
situations et la question de compréhension restent en `fr`, `en` et `km`.

Une nouvelle unité doit donc comporter ces cinq champs sur chaque entrée :
`python3 manage.py content check` signale ceux qui manquent. Les leçons déjà
créées sont complétées automatiquement à partir des unités (`render --all`,
`audio repair` et la génération quotidienne s'en chargent).

## Format d'une unité

```json
{
  "id": "u004",
  "order": 4,
  "level": "debutant",
  "theme": "famille",
  "title": {"fr": "La famille", "en": "Family", "km": "គ្រួសារ"},
  "tip": {"fr": "conseil sur le khmer, en français", "en": "conseil sur le khmer et le français, en anglais",
          "km": "conseil sur le français ou l'anglais, en khmer"},
  "vocabulary": [
    {
      "fr": "le père", "en": "father", "km": "ឪពុក", "tr": "eu-pouk",
      "es": "el padre", "it": "il padre", "ru": "отец", "zh": "爸爸", "zh_tr": "bàba", "pos": "nom",
      "note": {"fr": "explication en français", "en": "explication en anglais", "km": "explication en khmer"},
      "example": {"fr": "…", "en": "…", "km": "…", "tr": "…",
                  "es": "…", "it": "…", "ru": "…", "zh": "…", "zh_tr": "…"}
    }
  ],
  "expressions": [
    {"fr": "…", "en": "…", "km": "…", "tr": "…", "es": "…", "it": "…", "ru": "…", "zh": "…", "zh_tr": "…",
     "note": {"fr": "…", "en": "…", "km": "…"}}
  ],
  "sentences": [
    {"situation": {"fr": "Au marché", "en": "At the market", "km": "នៅផ្សារ"}, "fr": "…", "en": "…", "km": "…", "tr": "…",
     "es": "…", "it": "…", "ru": "…", "zh": "…", "zh_tr": "…"}
  ],
  "dialogue": {
    "setting": {"fr": "…", "en": "…", "km": "…"},
    "lines": [
      {"speaker": "B", "fr": "…", "en": "…", "km": "…", "tr": "…", "es": "…", "it": "…", "ru": "…", "zh": "…", "zh_tr": "…"},
      {"speaker": "A", "fr": "…", "en": "…", "km": "…", "tr": "…", "es": "…", "it": "…", "ru": "…", "zh": "…", "zh_tr": "…"}
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
   l'anglais à un francophone ; `note.en` explique le khmer et le français à
   un anglophone ; `note.km` explique le français ou l'anglais, en khmer
   simple. Une note peut citer un mot d'une autre langue.
8. **Textes destinés à la synthèse vocale** (`fr`, `en`, `km`, `es`, `it`, `ru`, `zh` hors notes) : pas de
   parenthèses, de barres obliques ni d'abréviations ; une seule formulation.
   Exception admise : `បាទ / ចាស` pour « oui ».
9. **Genre des personnages.** Le genre de A et de B est configurable. Préférer
   des tournures neutres quand A ou B parle de soi (« je vais bien », « j'ai
   faim ») plutôt qu'un adjectif dont la prononciation change au féminin.

10. **Espagnol et italien** : noms avec leur article (`el padre`, `la casa`,
    `il padre`, `l'acqua`), verbes à l'infinitif (`comer`, `mangiare`). Espagnol
    d'Espagne, vouvoiement avec `usted` / `Lei` quand le français dit « vous » à
    un inconnu.
11. **Russe** : cyrillique, noms au nominatif, verbes à l'infinitif imperfectif
    (`есть`, `пить`). Écrire `ё` (avec les deux points) : la translittération et
    la prononciation en dépendent. Pas d'accent tonique noté.
12. **Chinois** : caractères simplifiés, ponctuation chinoise (`，。？！：`).
    Le pinyin (`zh_tr`) porte les tons en diacritiques (`nǐ hǎo`), regroupe les
    syllabes d'un même mot (`péngyou`, `Jiǎnpǔzhài`), commence par une majuscule
    en début de phrase et reprend la ponctuation latine. Noter les changements de
    ton de 不 et 一 (`bú kèqi`, `yí ge`).
13. **Genre des personnages dans ces langues.** L'espagnol, l'italien et le russe
    accordent adjectifs et passé avec le locuteur : les traductions suivent les
    genres par défaut (A, Dara, au féminin ; B, Alex, au masculin). Hors
    dialogue, on emploie le masculin.

## Variables

| Variable | Remplacée par | Autorisée dans |
| --- | --- | --- |
| `{A}`, `{B}` | prénom du personnage (latin ou khmer selon la langue) | partout |
| `{A_yes}`, `{B_yes}` | `បាទ` ou `ចាស` selon le genre du locuteur | `km` et `tr` uniquement |

En russe et en chinois, `{A}` et `{B}` deviennent les prénoms écrits dans ces
langues (`name.ru`, `name.zh`, `name.zh_tr` des personnages : Дара, Алекс ;
达拉 Dálā, 亚历克斯 Yàlìkèsī).

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
| u051 | `la-cuisine-khmere` | La cuisine khmère | la soupe, le poulet, le porc, le bœuf, les nouilles, griller |
| u052 | `les-boissons` | Les boissons | le thé, le jus, la glace, le lait, la bière, le verre |
| u053 | `les-metiers` | Les métiers | le métier, le paysan, le vendeur, le chauffeur, le policier, le cuisinier |
| u054 | `a-la-mer` | À la mer | la mer, la plage, nager, l'île, le bateau, le sable |
| u055 | `les-vacances` | Les vacances | les vacances, visiter, le touriste, le plan, se perdre, partir |
| u056 | `la-sante` | La santé | la santé, le rhume, tousser, la dent, le dentiste, guérir |
| u057 | `les-voisins` | Les voisins | le voisin, le quartier, prêter, emprunter, bruyant, frapper |
| u058 | `comparer` | Comparer | plus, moins, le même, différent, meilleur, comme |
| u059 | `angkor` | Angkor et l'histoire | le temple, ancien, l'histoire, le roi, la sculpture, le siècle |
| u060 | `les-quantites` | Les quantités | beaucoup, peu, assez, trop, la moitié, tout |
| u061 | `les-grands-nombres` | Les grands nombres | vingt, cinquante, cent, mille, dix mille, un million |
| u062 | `la-frequence` | Dire à quelle fréquence | toujours, souvent, parfois, jamais, d'habitude, une fois |
| u063 | `le-logement` | Le logement | louer, l'appartement, le loyer, le propriétaire, déménager, l'électricité |
| u064 | `les-points-cardinaux` | Les points cardinaux et les provinces | le nord, le sud, l'est, l'ouest, la province, la frontière |
| u065 | `faire-du-sport` | Faire du sport | courir, marcher, le football, l'équipe, gagner, le match |
| u066 | `la-pagode-et-les-moines` | La pagode et les moines | le moine, prier, l'offrande, les ancêtres, bénir, l'encens |
| u067 | `les-rendez-vous` | Les rendez-vous | le rendez-vous, libre, accepter, refuser, annuler, oublier |
| u068 | `les-papiers` | Les papiers | remplir, signer, la carte d'identité, le visa, le bureau, la photocopie |
| u069 | `les-plantes` | Les plantes et les fleurs | la fleur, planter, arroser, la feuille, pousser, l'herbe |
| u070 | `les-compliments` | Les compliments | le compliment, féliciter, intelligent, doué, fier, réussir |
| u071 | `les-cinq-sens` | Les cinq sens | voir, regarder, entendre, écouter, sentir, toucher |
| u072 | `situer-les-choses` | Situer les choses | sur, sous, dans, devant, derrière, à côté de |
| u073 | `les-gestes-du-quotidien` | Les gestes du quotidien | donner, prendre, mettre, ouvrir, fermer, tenir |
| u074 | `les-mouvements` | Entrer, sortir, monter, descendre | entrer, sortir, monter, descendre, s'asseoir, se lever |
| u075 | `relier-ses-idees` | Relier ses idées | parce que, mais, donc, si, d'abord, ensuite |
| u076 | `la-duree` | Parler de la durée | depuis, pendant, longtemps, jusqu'à, tout de suite, un moment |
| u077 | `l-argent-et-la-banque` | L'argent et la banque | le compte, retirer, changer, le riel, la monnaie, économiser |
| u078 | `marchander` | Marchander | marchander, la réduction, gratuit, le client, le kilo, peser |
| u079 | `le-ciel-et-la-nature` | Le ciel et la nature | le ciel, la lune, l'étoile, le nuage, la forêt, le lac |
| u080 | `le-mariage` | Le mariage khmer | le mariage, la cérémonie, le marié, la mariée, la bague, l'enveloppe |
| u081 | `pouvoir-devoir-savoir` | Pouvoir, devoir, savoir | pouvoir, devoir, savoir, savoir faire, connaître, avoir besoin de |
| u082 | `il-elle-nous` | Il, elle, nous, ils | il et elle, nous, ils et elles, celui-ci, celui-là, quelqu'un |
| u083 | `les-contraires` | Lourd ou léger, plein ou vide | lourd, léger, long, court, plein, vide |
| u084 | `a-table` | À table : assiettes et couverts | l'assiette, le bol, la cuillère, la fourchette, le couteau, les baguettes |
| u085 | `parler-et-dire` | Parler, dire, demander | parler, dire, demander, expliquer, rire, plaisanter |
| u086 | `a-moto` | À moto | l'essence, le casque, la roue, le frein, le mécanicien, se garer |
| u087 | `les-urgences` | En cas d'urgence | l'accident, blessé, l'ambulance, le voleur, voler, brûler |
| u088 | `la-saison-des-pluies` | La saison des pluies | l'orage, l'inondation, mouillé, sec, la boue, le tonnerre |
| u089 | `epices-et-herbes` | Épices et herbes | le piment, l'ail, le citron vert, le gingembre, le poivre, la citronnelle |
| u090 | `la-fete-des-eaux` | La fête des Eaux | la fête des Eaux, la pirogue, ramer, la course, la foule, le feu d'artifice |

Aux niveaux élémentaire et intermédiaire, les phrases s'allongent ; au niveau
intermédiaire, le dialogue compte 6 à 8 répliques et les notes abordent les
temps (passé avec `បាន` / `ហើយ`, futur avec `នឹង`, et leurs équivalents français
et anglais).
