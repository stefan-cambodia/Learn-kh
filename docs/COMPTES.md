# Comptes utilisateurs (branche `serveur`)

La branche `main` est la version **autonome** : on ouvre `index.html`, rien ne
tourne, chaque navigateur garde sa progression. La branche `serveur` sert le
**même site** derrière une connexion :

- chaque personne a un compte (identifiant et mot de passe) et **sa propre
  progression**, conservée sur le serveur et retrouvée sur tous ses appareils ;
- un **administrateur** crée et gère les comptes depuis la page « Utilisateurs », suit la
  progression de chacun (page « Progression ») et consulte le **journal** des connexions ;
- les pages, les styles et les scripts du site ne changent pas : le menu du
  compte est ajouté au moment où le serveur envoie la page (`js/account.js`,
  `css/account.css`). Ouvertes depuis le disque, les pages se comportent comme
  sur `main`.

Tout reste en Python standard, sans dépendance à installer.

## Démarrer

```bash
python3 manage.py serve --host 0.0.0.0 --port 8000
```

Au premier lancement, aucun compte n'existe. Le terminal affiche un **code
d'installation** :

```
Site disponible sur http://localhost:8000/  (Ctrl+C pour arrêter)
Aucun compte pour l'instant. Ouvrez http://localhost:8000/installation et saisissez le code d'installation : k7mq-x2vd
```

Ouvrez `/installation`, saisissez ce code, puis choisissez l'identifiant et le
mot de passe de l'administrateur. Le code ne sert qu'une fois : il prouve que
vous avez accès à la machine. On peut aussi créer l'administrateur sans passer
par le navigateur :

```bash
python3 manage.py users add stefan --role admin      # le mot de passe est demandé deux fois
```

`python3 manage.py serve --no-accounts` lance l'ancien serveur sans comptes
(site ouvert, progression partagée entre les appareils).

## Ce que chacun peut faire

| Qui | Où | Quoi |
| --- | --- | --- |
| Apprenant | bouton du compte, en haut à droite | voir son nom, ouvrir « Mon compte » ou « Ma progression », se déconnecter |
| Apprenant | `/compte` | changer son nom affiché, sa langue (FR, ENG, KH) et son mot de passe ; voir ses appareils connectés et en déconnecter un ; voir les dernières connexions et tentatives sur son compte ; effacer sa progression |
| Apprenant | `/suivi` | sa progression en détail : leçons terminées, série de jours, calendrier des douze dernières semaines, cartes connues et à revoir par langue |
| Administrateur | `/utilisateurs` | inviter quelqu'un par un lien, créer un compte, changer un rôle ou une langue, désactiver ou réactiver, redonner un mot de passe (lien ou mot de passe provisoire), fermer les sessions, supprimer un compte ; voir les leçons terminées et la série de chacun, ses sessions ouvertes et ses derniers événements |
| Administrateur | `/suivi?u=…` | la même page « Progression » pour n'importe quel compte (bouton « Suivi » de la liste) |
| Administrateur | `/journal` | connexions, échecs et opérations sur les comptes, avec filtres et pages |

Un compte créé sans mot de passe reçoit un **mot de passe provisoire**, affiché
une seule fois à l'administrateur ; la personne doit le changer à sa première
connexion. Il n'y a pas d'envoi de courriel : invitations et mots de passe oubliés
passent par des **liens à usage unique** que l'administrateur transmet lui-même
(messagerie, de vive voix), décrits ci-dessous.

Garde-fous : il reste toujours au moins un administrateur actif, et personne ne
peut désactiver ni supprimer son propre compte.

## Inviter quelqu'un, redonner un mot de passe

Trois façons d'ouvrir un compte, de la plus simple à la plus ouverte :

1. **Lien d'invitation** (page « Utilisateurs », carte « Invitations ») : vous indiquez pour
   qui, le rôle et la langue ; le lien s'affiche **une seule fois**, à copier et à envoyer.
   La personne l'ouvre, choisit son identifiant et son mot de passe, et se retrouve
   connectée — vous ne connaissez jamais son mot de passe. La page s'ouvre dans la langue
   prévue pour elle. Les invitations en attente sont listées et peuvent être annulées.
2. **Compte créé par vous** (carte « Nouveau compte »), avec un mot de passe provisoire.
3. **Inscription ouverte** à tous, avec ou sans code d'invitation commun (section suivante).

Pour un **mot de passe oublié**, la fiche du compte propose « Créer un lien de nouveau mot
de passe » : la personne choisit elle-même son mot de passe, ses autres appareils sont
déconnectés. À défaut, « Définir le mot de passe » donne un mot de passe provisoire.

Ces liens :

- ne servent **qu'une fois** ; les ouvrir ne les consomme pas (une messagerie peut en
  afficher l'aperçu), seul l'envoi du formulaire le fait ;
- expirent : 7 jours pour une invitation (`server.invite_days`), 24 heures pour un nouveau
  mot de passe (`server.reset_hours`) ;
- ne sont pas conservés : la base n'en garde que l'empreinte. Un lien perdu se remplace par
  un nouveau ; un nouveau lien de mot de passe annule le précédent, tout comme un changement
  de mot de passe ou la désactivation du compte.

Un lien donne accès à un compte : envoyez-le par un canal privé, à la bonne personne.

## Suivi et journal

**Progression** (`/suivi`). La page résume ce que le compte a enregistré, toutes langues
d'apprenant confondues : leçons terminées sur les leçons déjà parues, jours d'activité, série
en cours et meilleure série, calendrier des douze dernières semaines, et pour chaque langue
révisée les cartes « connues » (troisième boîte et au-delà) et celles à revoir aujourd'hui.
Chacun voit la sienne ; **l'administrateur voit celle de tous les comptes** — à dire aux
personnes à qui vous ouvrez un compte.

**Appareils connectés** (`/compte`). Chaque session ouverte apparaît avec le navigateur, le
système, l'adresse et la dernière activité (à une heure près). Le bouton « Déconnecter »
ferme celle d'un autre appareil ; un appareil perdu ne garde donc pas l'accès.

**Journal** (`/journal`, administrateur). Y sont notés : connexions et déconnexions,
inscriptions, échecs de connexion, blocages pour trop de tentatives (une ligne par blocage),
changements de mot de passe, créations, modifications, désactivations et suppressions de
comptes, fermetures de sessions, effacements de progression — avec la date, l'adresse et,
quand ce n'est pas le compte lui-même, l'auteur (un administrateur ou la ligne de commande).

- Quand l'identifiant saisi ne correspond à aucun compte, **il n'est pas conservé** : ce
  pourrait être un mot de passe tapé dans la mauvaise case. Le journal dit seulement
  « identifiant inconnu ».
- Le journal survit à la suppression d'un compte, et garde `server.journal_days` jours
  (180 par défaut, 50 000 lignes au plus). Il est dans la table `account_events` de la base.
- Les mêmes lignes vont dans `logs/app.log`.

## Inscription

Par défaut, seul l'administrateur crée les comptes. Pour laisser chacun créer
le sien, dans `config/config.json` :

```json
"server": {"registration": "open", "registration_code": "un-code-a-partager"}
```

Avec `registration_code`, la page `/inscription` demande ce code d'invitation ;
laissez-le vide pour une inscription libre. Une inscription crée toujours un
compte d'apprenant, jamais d'administrateur.

## Ligne de commande

| Commande | Effet |
| --- | --- |
| `users list` | comptes, rôle, état, langue, leçons terminées, dernière connexion |
| `users show dara` | détail d'un compte : progression, sessions ouvertes, derniers événements |
| `users journal` | journal des comptes ; `users journal dara` pour un seul compte, `--type logins`, `failures` ou `accounts`, `--limit 200` |
| `users add dara --name "Dara Sok" --profile km` | crée un compte (mot de passe demandé deux fois) |
| `users add dara --generate` | crée un compte avec un mot de passe provisoire, à changer à la connexion |
| `users add dara --password-stdin` | lit le mot de passe sur l'entrée standard (scripts) |
| `users invite --for "Tante Sophea" --profile km --url https://apprendre.exemple.org` | affiche un lien d'invitation à usage unique (`--role admin`, `--days 3`) ; sans `--url`, le chemin à ajouter à l'adresse du site |
| `users reset-link dara` | affiche un lien pour que la personne choisisse un nouveau mot de passe (`--hours 2`, `--url …`) |
| `users password dara` | change le mot de passe et ferme les sessions du compte (`--generate`, `--password-stdin`) |
| `users role dara admin` | change le rôle (`admin` ou `user`) |
| `users disable dara` / `users enable dara` | interdit ou rétablit la connexion |
| `users logout dara` | ferme toutes les sessions du compte |
| `users delete dara --yes` | supprime le compte et sa progression |
| `users import-progress dara` | reprend dans ce compte la progression partagée de l'ancien serveur sans comptes |

Si le serveur tourne, un changement fait en ligne de commande est pris en compte
en vingt secondes au plus.

## Réglages (`server` dans `config/config.json`)

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `require_login` | `true` | `false` : le site se lit sans compte ; seule la progression en ligne demande de se connecter |
| `registration` | `"closed"` | `"open"` : chacun peut créer son compte sur `/inscription` |
| `registration_code` | `""` | code d'invitation exigé à l'inscription, s'il est renseigné |
| `session_days` | `30` | durée d'une session sans visite ; chaque visite la prolonge |
| `password_min_length` | `8` | longueur minimale des mots de passe (6 à 64) |
| `cookie_secure` | `"auto"` | attribut `Secure` du cookie : `"auto"` (derrière un proxy HTTPS de confiance), `true` ou `false` |
| `trust_proxy` | `false` | `true` derrière un proxy inverse : `X-Forwarded-For`, `-Proto` et `-Host` sont alors crus |
| `journal_days` | `180` | durée de conservation du journal des comptes, en jours (1 à 3650) |
| `invite_days` | `7` | durée de validité d'un lien d'invitation, en jours (1 à 90) |
| `reset_hours` | `24` | durée de validité d'un lien de nouveau mot de passe, en heures (1 à 168) |

## La progression

Le navigateur garde toujours la progression dans son stockage local, comme sur
`main` ; connecté, il l'échange avec le serveur, qui la range **par compte**
(table `user_progress` de `database/learning.db`). Les règles de fusion sont
celles de l'ancienne synchronisation : entrée par entrée, la plus récente gagne.

- **Premier passage d'un navigateur** : la progression qu'il contenait déjà est
  reprise dans le compte qui s'y connecte.
- **Changement de compte sur le même navigateur** : la progression locale du
  compte précédent est effacée de ce navigateur (elle reste sur le serveur),
  celle du nouveau compte est chargée.
- **Déconnexion** : la progression est envoyée une dernière fois, puis effacée
  du navigateur.
- **« Effacer ma progression »** : la remise à zéro vaut pour tous les appareils
  du compte ; ce qu'ils gardaient d'avant est ignoré puis effacé chez eux.

La sauvegarde quotidienne (`manage.py backup`) copie toute la base : les
comptes et les progressions en font partie.

## Sécurité

- **Mots de passe** : jamais stockés, seulement leur empreinte scrypt (N = 2¹⁴,
  r = 8, p = 5) avec un sel par compte ; PBKDF2-SHA256 si Python n'a pas scrypt.
  Les paramètres sont écrits dans l'empreinte : une empreinte plus faible que
  le réglage courant est refaite à la connexion suivante.
- **Sessions** : jeton aléatoire dans un cookie `HttpOnly`, `SameSite=Lax` ; la
  base n'en garde que le SHA-256. Changer de mot de passe ferme les autres
  sessions ; désactiver ou supprimer un compte les ferme toutes.
- **Liens à usage unique** (invitation, nouveau mot de passe) : jeton aléatoire de
  256 bits, dont la base ne garde que le SHA-256 ; usage unique, durée limitée, essais
  de liens au hasard ralentis comme les tentatives de connexion.
- **Formulaires** : jeton anti-CSRF sur chaque formulaire et contrôle de
  l'origine des requêtes POST ; les pages ne s'affichent pas dans un cadre.
- **Tentatives** : cinq échecs pour un identifiant depuis une même adresse (ou
  trente depuis une adresse, tous identifiants confondus) bloquent la connexion
  un quart d'heure. Un identifiant inconnu et un mauvais mot de passe donnent
  la même réponse, dans le même temps.
- **Fichiers privés** : `.env`, la base, la configuration et le code ne sont
  jamais servis, connecté ou non.
- **Journal** : connexions, échecs et opérations sur les comptes sont notés dans la base
  (page « Journal ») et dans `logs/app.log` — jamais les mots de passe, ni un identifiant
  qui ne correspond à aucun compte.

### Hors du réseau local : HTTPS obligatoire

Le serveur parle HTTP. Sur le Wi-Fi de la maison, c'est acceptable ; sur
Internet, les mots de passe circuleraient en clair. Placez alors le serveur
derrière un proxy inverse qui apporte HTTPS, et laissez-le écouter sur
`127.0.0.1`. Avec Caddy :

```
apprendre.exemple.org {
    reverse_proxy 127.0.0.1:8000
}
```

puis, dans `config/config.json` : `"server": {"trust_proxy": true}`. Le cookie
de session reçoit alors l'attribut `Secure`, et l'adresse des visiteurs est lue
dans `X-Forwarded-For`. Avec nginx, transmettez l'hôte et le protocole :
`proxy_set_header Host $host;`, `proxy_set_header X-Forwarded-For $remote_addr;`,
`proxy_set_header X-Forwarded-Proto $scheme;`.

N'activez `trust_proxy` que derrière un proxy : sans lui, n'importe qui
pourrait se faire passer pour une autre adresse.

## Laisser tourner le serveur (Linux, systemd)

`~/.config/systemd/user/fr-kh-serveur.service` :

```ini
[Unit]
Description=FR-KH Learning — serveur avec comptes
After=network.target

[Service]
WorkingDirectory=/chemin/vers/le/projet
ExecStart=/usr/bin/python3 manage.py serve --host 0.0.0.0 --port 8000
Restart=on-failure

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now fr-kh-serveur
journalctl --user -u fr-kh-serveur        # le code d'installation s'y trouve au premier lancement
```

## Garder la branche à jour

Les leçons continuent d'être écrites et générées sur `main`. Pour les
reprendre :

```bash
git switch serveur
git merge main
```

La branche n'a modifié aucune page générée, aucun gabarit, ni `js/app.js` ni
`css/style.css` : les nouvelles leçons arrivent sans conflit. Ce qu'elle ajoute :

| Fichier | Rôle |
| --- | --- |
| `frkh/accounts.py` | comptes, mots de passe, sessions, liens à usage unique, progression par compte, journal |
| `frkh/webapp.py` | serveur : connexion, contrôle d'accès, pages et API |
| `frkh/account_pages.py` | contenu des pages (français, anglais, khmer) |
| `js/account.js`, `css/account.css` | menu du compte et formulaires |
| `tests/test_accounts.py` | tests des comptes et du serveur |

et ce qu'elle retouche : `frkh/admin.py` (le gestionnaire HTTP devient
réutilisable), `frkh/cli.py` (commandes `serve` et `users`), `frkh/config.py`
(rubrique `server`).
