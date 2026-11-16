# Configurer Azure AI Speech pour le khmer

Google Cloud Text-to-Speech ne propose aucune voix khmère. Le khmer (`km-KH`)
est donc prononcé par **Azure AI Speech**, via son API REST officielle
(`https://<région>.tts.speech.microsoft.com/cognitiveservices/v1`), qui offre
deux voix neuronales :

| Voix | Genre |
| --- | --- |
| `km-KH-SreymomNeural` (par défaut) | féminine |
| `km-KH-PisethNeural` | masculine |

## 1. Créer la ressource Speech

1. Ouvrez <https://portal.azure.com/> et connectez-vous (un compte Microsoft
   suffit ; la création d'un abonnement Azure demande une carte bancaire).
2. **Créer une ressource**, cherchez **Speech** (service « Azure AI Speech »),
   puis **Créer**.
3. Renseignez :
   - **Région** : `Southeast Asia` (Singapour), la plus proche du Cambodge ;
   - **Niveau tarifaire** : `Free F0` pour commencer ;
   - un nom et un groupe de ressources à votre convenance.
4. Validez, puis ouvrez la ressource une fois créée.

## 2. Récupérer la clé et la région

Dans la ressource, menu **Clés et point de terminaison** : copiez **CLÉ 1** et
notez **Emplacement/Région** (par exemple `southeastasia`).

Dans le fichier `.env`, à la racine du projet :

```
AZURE_SPEECH_KEY=votre-clé
AZURE_SPEECH_REGION=southeastasia
```

## 3. Vérifier

```bash
python3 manage.py tts status              # « km-KH azure km-KH-SreymomNeural → prêt »
python3 manage.py tts test --lang km      # crée un premier fichier WAV khmer
python3 manage.py tts voices --lang km    # voix khmères disponibles
```

Pour la voix masculine, dans `config/config.json` :

```json
"km": {"locale": "km-KH", "provider": "azure", "voice": "km-KH-PisethNeural"}
```

## Coût

Le khmer représente environ **500 caractères par leçon**, soit de l'ordre de
15 000 caractères pour les 30 leçons du programme. À la date de rédaction
(novembre 2026), le niveau gratuit `F0` inclut 500 000 caractères de voix
neuronales par mois : l'usage de ce projet en représente environ 3 %. Vérifiez
les conditions en vigueur sur
<https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/>.

Le niveau `F0` ne facture jamais : une fois son quota atteint, le service
refuse les appels jusqu'au mois suivant, et l'application reporte simplement
les audios restants.

## Utiliser Azure pour les trois langues

Si vous ne souhaitez gérer qu'un seul compte, laissez `GOOGLE_TTS_API_KEY`
vide : l'application bascule alors automatiquement le français et l'anglais sur
les voix de secours Azure définies dans `config/config.json`
(`fr-FR-DeniseNeural` et `en-US-JennyNeural`). Dès qu'une clé Google est
ajoutée, Google redevient prioritaire pour ces deux langues ; les fichiers déjà
produits avec Azure restent sur le disque et les nouveaux sont générés avec la
voix Google.

Pour rendre ce choix définitif, indiquez directement Azure comme fournisseur :

```json
"fr": {"locale": "fr-FR", "provider": "azure", "voice": "fr-FR-DeniseNeural", "fallback": null},
"en": {"locale": "en-US", "provider": "azure", "voice": "en-US-JennyNeural", "fallback": null}
```

## En cas de problème

| Message | Cause probable |
| --- | --- |
| `AZURE_SPEECH_KEY absent du fichier .env` | clé non renseignée |
| `AZURE_SPEECH_REGION absent du fichier .env` | région non renseignée |
| `accès refusé (HTTP 401)` | clé erronée, ou région différente de celle de la ressource |
| `requête refusée (HTTP 400)` | nom de voix inexistant (voir `tts voices --lang km`) |
| `service momentanément indisponible (HTTP 429)` | quota du niveau gratuit atteint, ou trop d'appels rapprochés |

La leçon est publiée dans tous les cas ; l'audio khmer manquant est retenté
automatiquement, ou tout de suite avec `python3 manage.py audio repair`.

## Autre moteur

La couche fournisseur est indépendante du reste de l'application. Pour brancher
un moteur local en ligne de commande (par exemple Piper), voir la rubrique
« Fournisseur command » de [CONFIGURATION.md](CONFIGURATION.md). Pour un autre
service en ligne, il suffit d'écrire une classe dérivée de `TTSProvider`
(`frkh/audio/providers/base.py`) et de l'enregistrer avec `register_provider`.
