# Configurer Google Cloud Text-to-Speech

Google Cloud Text-to-Speech prononce le **français** et l'**anglais**.
L'application appelle l'API REST officielle
(`https://texttospeech.googleapis.com/v1/text:synthesize`) et demande
directement du WAV PCM 16 bits (`LINEAR16`).

> Google Cloud Text-to-Speech ne propose pas de voix khmère (`km-KH`). Pour le
> khmer, voir [AZURE_SPEECH_KHMER.md](AZURE_SPEECH_KHMER.md).

## 1. Créer le projet et activer l'API

1. Ouvrez <https://console.cloud.google.com/> et connectez-vous.
2. Créez un projet (menu des projets, en haut → **Nouveau projet**), par
   exemple `fr-kh-learning`.
3. Associez un **compte de facturation** au projet (menu **Facturation**).
   Google l'exige même pour rester dans le volume gratuit.
4. Menu **API et services → Bibliothèque**, cherchez **Cloud Text-to-Speech
   API**, puis cliquez sur **Activer**.

## 2. Créer une clé API restreinte

1. Menu **API et services → Identifiants**.
2. **Créer des identifiants → Clé API**. Copiez la clé affichée.
3. Ouvrez la clé pour la modifier :
   - **Restrictions relatives aux API** → *Restreindre la clé* → cochez
     uniquement **Cloud Text-to-Speech API** ;
   - **Restrictions relatives aux applications** : *Aucune*, ou *Adresses IP* si
     votre connexion a une adresse fixe.
4. Enregistrez.

## 3. Renseigner la clé

Dans le fichier `.env`, à la racine du projet :

```
GOOGLE_TTS_API_KEY=votre-clé
```

La clé est envoyée dans un en-tête HTTP, jamais dans une adresse. Elle n'est
écrite ni dans les pages, ni dans les données, ni dans les journaux ;
`python3 manage.py check` le vérifie.

## 4. Vérifier

```bash
python3 manage.py tts status              # « fr-FR google … → prêt »
python3 manage.py tts test --lang fr      # crée un premier fichier WAV
python3 manage.py tts test --lang en
python3 manage.py tts voices --lang fr    # voix françaises disponibles
python3 manage.py tts voices --lang en
```

## Choisir les voix

Dans `config/config.json`, rubrique `languages` :

```json
"fr": {"locale": "fr-FR", "provider": "google", "voice": "fr-FR-Neural2-F"},
"en": {"locale": "en-US", "provider": "google", "voice": "en-US-Neural2-F"}
```

- Anglais britannique : `"locale": "en-GB", "voice": "en-GB-Neural2-A"`.
- Familles de voix : `Standard` (la plus économique), `Wavenet`, `Neural2`
  (valeur par défaut, naturelle) et `Chirp3-HD` (la plus expressive, par
  exemple `fr-FR-Chirp3-HD-Achernar`). La commande `tts voices` donne les noms
  exacts.
- Vitesse : `audio.speaking_rate` (0,9 par défaut, un peu plus lent que la
  normale, pratique pour apprendre). Si une voix refuse un réglage (message
  « requête refusée »), fixez pour cette langue
  `"speaking_rate": 1.0` et `"pitch": 0` dans sa rubrique.

Changer de voix, de vitesse ou de fréquence change l'empreinte des fichiers :
les anciens audios sont conservés, les nouveaux sont générés à la prochaine
exécution (`python3 manage.py audio repair` pour le faire tout de suite, puis
`python3 manage.py audio prune` pour supprimer ceux qui ne servent plus).

## Coût

Une leçon représente environ **1 200 caractères** en français et en anglais
réunis (une cinquantaine de courts fichiers audio), soit de l'ordre de
**37 000 caractères pour les 30 leçons du programme**. Comme chaque texte
n'est synthétisé qu'une fois, les révisions et les leçons de révision ne
coûtent rien.

À la date de rédaction (novembre 2026), le volume gratuit mensuel annoncé par
Google est de 1 million de caractères pour les voix Neural2 et de 4 millions
pour les voix Standard et WaveNet : l'usage de ce projet en représente quelques
pour cent. Vérifiez les conditions en vigueur sur
<https://cloud.google.com/text-to-speech/pricing>.

Deux protections complémentaires :

- dans `config/config.json`, `tts.limits` plafonne les appels par exécution et
  les caractères par jour et par mois ; une fois la limite atteinte, les audios
  restants sont simplement reportés ;
- dans la console Google Cloud, **Facturation → Budgets et alertes** permet de
  recevoir un courriel dès le premier centime dépensé.

## Variante : compte de service

Si vous préférez un compte de service à une clé API :

```bash
pip install google-auth requests
```

```
GOOGLE_APPLICATION_CREDENTIALS=/chemin/vers/compte-de-service.json
GOOGLE_CLOUD_PROJECT=identifiant-du-projet
```

Le compte doit avoir accès à l'API Cloud Text-to-Speech. Si
`GOOGLE_TTS_API_KEY` est aussi définie, c'est elle qui est utilisée.

## En cas de problème

| Message | Cause probable |
| --- | --- |
| `GOOGLE_TTS_API_KEY absent du fichier .env` | la clé n'est pas renseignée, ou `.env` n'est pas à la racine du projet |
| `accès refusé (HTTP 403)` | API non activée, facturation non associée, ou clé restreinte à une autre API ou à une autre adresse IP |
| `requête refusée (HTTP 400)` | nom de voix inexistant pour la locale (voir `tts voices`), ou réglage non accepté par la voix |
| `service momentanément indisponible (HTTP 429)` | quota dépassé : l'application réessaie, puis reporte les audios restants |
| `réseau indisponible` | pas de connexion : la leçon est créée, l'audio sera généré plus tard |

Dans tous les cas, la leçon est publiée et l'audio manquant est retenté
automatiquement ; `python3 manage.py audio repair` force une nouvelle tentative.
