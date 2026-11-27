"""Serveur web avec comptes utilisateurs : « python3 manage.py serve ».

Il distribue le même site que la version autonome — les pages, les styles et les scripts ne
sont pas modifiés — mais derrière une connexion :

- chaque visiteur a un compte (identifiant, mot de passe) et sa propre progression, conservée
  sur le serveur et retrouvée sur tous ses appareils ;
- un administrateur gère les comptes depuis la page « Utilisateurs » ;
- le menu du compte est ajouté aux pages au moment de les servir (``js/account.js``,
  ``css/account.css``), sans toucher aux fichiers générés.

Pages : ``/connexion``, ``/inscription`` (si elle est ouverte), ``/installation`` (premier
démarrage), ``/compte``, ``/utilisateurs``. API : ``/api/me``, ``/api/progress``, ``/api/profile``.

Protections : cookie de session ``HttpOnly`` et ``SameSite=Lax``, jeton anti-CSRF sur chaque
formulaire, contrôle de l'origine des requêtes POST, tentatives de connexion limitées, et les
fichiers privés du projet (.env, base, configuration, code) restent inaccessibles, connecté ou non.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import logging
import math
import posixpath
import re
import secrets
import threading
import time
import urllib.parse
from collections import OrderedDict

from . import account_pages as pages
from . import admin
from .accounts import PLAIN_ALPHABET, AccountError, Accounts, Throttle, generate_password, message_texts, normalize_login
from .render import SiteRenderer

SESSION_COOKIE = "frkh_session"
FORM_COOKIE = "frkh_form"                 # jeton anti-CSRF des formulaires sans session (connexion, inscription)
ASSET_DIRS = ("css", "fonts", "js")       # nécessaires à la page de connexion : servis sans compte
ROUTES = ("connexion", "deconnexion", "inscription", "installation", "compte", "utilisateurs")
MAX_FORM = 64 * 1024
MAX_PROGRESS = 2 * 1024 * 1024
ROOT_RE = re.compile(r'<html[^>]*\bdata-root="((?:\.|\.\.)(?:/\.\.)*)"')
CHARSET_RE = re.compile(r"<meta\s+charset=[^>]*>", re.IGNORECASE)
HEAD_RE = re.compile(r"<head[^>]*>", re.IGNORECASE)
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "same-origin"),
    ("Content-Security-Policy", "frame-ancestors 'none'; form-action 'self'; base-uri 'self'"),
)

# Exécuté dans l'en-tête de chaque page, avant le reste : si un autre compte se connecte sur ce
# navigateur, la progression gardée localement est effacée (celle du compte arrive du serveur),
# et la langue du compte est reprise. Une progression locale sans compte est adoptée.
HEAD_SCRIPT = (
    '(function(){var a=window.FRKH_ACCOUNT,u=a&&a.user;if(u||(a&&!a.login)){document.documentElement.classList.add("has-account");}'
    'if(!u){return;}try{var s=window.localStorage,'
    'p=s.getItem("frkh-user"),id=String(u.id),k=[],i;if(p!==null&&p!==id){for(i=0;i<s.length;i++){k.push(s.key(i));}'
    'k.forEach(function(n){if(/^frkh-(done2?|days|boxes|review|quiz)-/.test(n||"")){s.removeItem(n);}});}'
    'if(p!==id){s.setItem("frkh-user",id);if(u.profile){s.setItem("frkh-profile",u.profile);}}}catch(e){}})();')


def safe_next(value) -> str:
    """Page où revenir après la connexion : uniquement un chemin du site, relatif à sa racine."""
    value = str(value or "")
    if (not value.startswith("/") or value.startswith("//") or len(value) > 300
            or any(c in value for c in "\\\r\n\t\x00") or "://" in value):
        return ""
    path = value[1:]
    first = path.split("?", 1)[0].split("/", 1)[0]
    if first in ROUTES or first == "api":
        return ""
    return path


class WebApp:
    """État partagé par toutes les requêtes : comptes, limitation des tentatives, messages à afficher."""

    def __init__(self, config, logger: logging.Logger | None = None, clock=time.time):
        self.config = config
        self.clock = clock
        self.log = logger or logging.getLogger("frkh.accounts")
        self.accounts = Accounts(config, clock)
        self.renderer = SiteRenderer(config, None, None)
        self.pair_throttle = Throttle(5, 900, clock)      # échecs pour un identifiant donné depuis une adresse
        self.ip_throttle = Throttle(30, 900, clock)       # échecs depuis une adresse, tous identifiants confondus
        self.signup_throttle = Throttle(10, 3600, clock)  # comptes créés depuis une adresse
        self.setup_code = ""
        self._flash: dict[str, list] = {}
        self._gzip: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()

    def close(self) -> None:
        self.accounts.close()

    # --- réglages -----------------------------------------------------------------------------
    def require_login(self) -> bool:
        return bool(self.config.get("server.require_login", True))

    def registration_open(self) -> bool:
        return str(self.config.get("server.registration", "closed")).lower() == "open"

    def registration_code(self) -> str:
        return str(self.config.get("server.registration_code", "") or "").strip()

    def trust_proxy(self) -> bool:
        return bool(self.config.get("server.trust_proxy", False))

    def site_title(self) -> str:
        return str(self.config.get("site.title", "FR-KH Learning"))

    def ensure_setup_code(self, announce: bool = True) -> str:
        """Code demandé pour créer le premier compte : seul celui qui voit le terminal (ou le journal)
        du serveur le connaît. Il ne sert qu'une fois."""
        with self._lock:
            if not self.setup_code:
                self.setup_code = "-".join("".join(secrets.choice(PLAIN_ALPHABET) for _ in range(4)) for _ in range(2))
                if announce:
                    self.log.warning("Aucun compte : code d'installation %s (à saisir sur la page /installation)", self.setup_code)
            return self.setup_code

    def asset_version(self) -> str:
        stamp = 0
        for rel in ("css/account.css", "js/account.js"):
            try:
                stamp = max(stamp, int((self.config.paths.root / rel).stat().st_mtime))
            except OSError:
                pass
        return str(stamp)

    # --- messages à afficher une fois (après une redirection) --------------------------------------
    def flash(self, session, kind: str, message: dict) -> None:
        with self._lock:
            if len(self._flash) > 2000:
                self._flash.clear()
            self._flash.setdefault(session.token_hash, []).append((kind, message))

    def pop_flash(self, session) -> list:
        with self._lock:
            return self._flash.pop(session.token_hash, [])

    # --- pages compressées ------------------------------------------------------------------------
    def gzip_cached(self, key: str) -> bytes | None:
        with self._lock:
            data = self._gzip.get(key)
            if data is not None:
                self._gzip.move_to_end(key)
            return data

    def gzip_store(self, key: str, data: bytes) -> None:
        if len(data) > 4 * 1024 * 1024:
            return
        with self._lock:
            self._gzip[key] = data
            while len(self._gzip) > 32:
                self._gzip.popitem(last=False)


def public_user(user) -> dict:
    return {"id": user.id, "login": user.login, "name": user.name, "role": user.role, "profile": user.profile}


def make_handler(app: WebApp):
    """Gestionnaire HTTP : celui du site public, placé derrière les comptes."""
    base = admin.make_handler(app.config)
    config = app.config
    root = config.paths.root
    index = root / "index.html"
    asset_dirs = [(root / name).resolve() for name in ASSET_DIRS]
    manifest = (root / "manifest.webmanifest").resolve()
    accounts = app.accounts
    unset = object()

    class Handler(base):
        server_version = "FRKH"
        sys_version = ""

        # --- contexte de la requête -------------------------------------------------------------
        def _begin(self) -> None:
            self._cookies_out: list[str] = []
            self._session = unset
            self._cache_control = None
            self._query: dict = {}
            self._url = urllib.parse.urlsplit("/")
            self._url = urllib.parse.urlsplit(self.path)        # ValueError si l'adresse est malformée
            if len(self._url.query) < 2000:
                try:
                    self._query = urllib.parse.parse_qs(self._url.query, keep_blank_values=True, max_num_fields=20)
                except ValueError:
                    pass

        def _arg(self, name: str) -> str:
            return (self._query.get(name) or [""])[-1]

        def _cookie(self, name: str) -> str:
            for part in self.headers.get("Cookie", "").split(";"):
                key, _, value = part.strip().partition("=")
                if key == name:
                    return value.strip('"')
            return ""

        @property
        def session(self):
            if self._session is unset:
                self._session = accounts.session(self._cookie(SESSION_COOKIE))
            return self._session

        def _client_ip(self) -> str:
            ip = self.client_address[0]
            if app.trust_proxy():
                forwarded = self.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
                ip = forwarded or ip
            return ip[:64]

        def _secure(self) -> bool:
            setting = config.get("server.cookie_secure", "auto")
            if isinstance(setting, bool):
                return setting
            return app.trust_proxy() and self.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower() == "https"

        def _same_origin(self) -> bool:
            """Refuse les requêtes POST lancées depuis un autre site (en plus des jetons anti-CSRF)."""
            host = (self.headers.get("X-Forwarded-Host", "").split(",")[0].strip() if app.trust_proxy() else "") \
                or self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            if origin:
                return origin != "null" and urllib.parse.urlsplit(origin).netloc.lower() == host.lower()
            site = self.headers.get("Sec-Fetch-Site")
            return site in (None, "same-origin", "none")

        def _set_cookie(self, name: str, value: str, *, max_age: int | None, same_site: str = "Lax") -> None:
            cookie = f"{name}={value}; Path=/; HttpOnly; SameSite={same_site}"
            if max_age is not None:
                cookie += f"; Max-Age={max_age}"
            if self._secure():
                cookie += "; Secure"
            self._cookies_out.append(cookie)

        def end_headers(self):
            for cookie in getattr(self, "_cookies_out", ()):
                self.send_header("Set-Cookie", cookie)
            self._cookies_out = []
            for name, value in SECURITY_HEADERS:
                self.send_header(name, value)
            if getattr(self, "_cache_control", None):
                self.send_header("Cache-Control", self._cache_control)
                self._cache_control = None
            super().end_headers()

        def _is_sync(self) -> bool:
            return False        # l'ancienne synchronisation partagée n'existe plus : la progression est par compte

        # --- réponses -------------------------------------------------------------------------------
        def _root_prefix(self) -> str:
            clean = posixpath.normpath(urllib.parse.unquote(self._url.path) or "/")
            return "../" * max(0, clean.count("/") - 1) or "./"

        def _redirect(self, target: str = "", status: int = 303) -> None:
            self.send_response(status)
            self.send_header("Location", self._root_prefix() + target)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _send_bytes(self, status: int, body: bytes, content_type: str, headers=()) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _send_json(self, status: int, payload) -> None:
            self._send_bytes(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                             "application/json; charset=utf-8", (("Cache-Control", "no-store"),))

        def _plain(self, status: int, text: str) -> None:
            self._send_bytes(status, text.encode("utf-8"), "text/plain; charset=utf-8", (("Cache-Control", "no-store"),))

        def _accepts_gzip(self) -> bool:
            return "gzip" in self.headers.get("Accept-Encoding", "").lower()

        def _send_html(self, status: int, html: str) -> None:
            body, headers = html.encode("utf-8"), [("Cache-Control", "no-store"), ("Vary", "Accept-Encoding, Cookie")]
            if self._accepts_gzip() and len(body) > 1400:
                body = gzip.compress(body, 5)
                headers.append(("Content-Encoding", "gzip"))
            self._send_bytes(status, body, "text/html; charset=utf-8", headers)

        # --- habillage des pages ----------------------------------------------------------------------
        def _account_json(self) -> str:
            session = self.session
            payload = {"user": public_user(session.user) if session else None,
                       "csrf": session.csrf_token if session else "",
                       "registration": app.registration_open(), "login": app.require_login()}
            text = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

        def _inject(self, html: str, page_root: str | None = None) -> str:
            """Ajoute à une page le style et le script du menu du compte, et l'identité du visiteur."""
            if page_root is None:
                found = ROOT_RE.search(html[:2000])
                page_root = found.group(1) if found else self._root_prefix().rstrip("/")
            version = app.asset_version()
            script = f'<script>window.FRKH_ACCOUNT={self._account_json()};{HEAD_SCRIPT}</script>'
            style = f'<link rel="stylesheet" href="{page_root}/css/account.css?v={version}">'
            tail = f'<script src="{page_root}/js/account.js?v={version}" defer></script>'
            # Le script d'identité passe avant tout le reste ; la feuille de style, après celle du site.
            anchor = CHARSET_RE.search(html) or HEAD_RE.search(html)
            html = html[:anchor.end()] + script + html[anchor.end():] if anchor else script + html
            end = html.find("</head>")
            html = html[:end] + style + html[end:] if end != -1 else style + html
            end = html.rfind("</body>")
            return html[:end] + tail + html[end:] if end != -1 else html + tail

        def _render(self, body_class: str, title_key: str, content: str, status: int = 200) -> None:
            title = f"{pages.TEXT[title_key][0]} — {app.site_title()}"
            page = app.renderer._page(root=".", title=title, description=pages.TEXT[title_key][0],
                                      body_class=body_class, content=content)
            self._send_html(status, self._inject(page, "."))

        def _error_page(self, status: int) -> None:
            key = "e403" if status == 403 else "e404"
            self._render("page-account" if self.session else "page-auth", f"{key}_title",
                         pages.error_page(f"{key}_title", f"{key}_text"), status)

        def _serve_page_file(self, target) -> None:
            """Une page du site (fichier .html), complétée par le menu du compte. Le navigateur la garde
            en cache mais la revalide à chaque visite : elle dépend du compte connecté."""
            try:
                stat = target.stat()
                if not target.is_file():
                    raise OSError("pas un fichier")
            except OSError:
                return self.send_error(404, "Introuvable")
            seed = f"{target}:{stat.st_mtime_ns}:{stat.st_size}:{self._account_json()}:{app.asset_version()}"
            stamp = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
            compress = self._accepts_gzip()
            etag = f'"{stamp}{"-gz" if compress else ""}"'
            headers = [("ETag", etag), ("Cache-Control", "private, no-cache"), ("Vary", "Accept-Encoding, Cookie")]
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                for name, value in headers:
                    self.send_header(name, value)
                return self.end_headers()
            body = app.gzip_cached(stamp) if compress else None
            if body is None:
                try:
                    html = target.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    return self.send_error(404, "Introuvable")
                body = self._inject(html).encode("utf-8")
                if compress:
                    body = gzip.compress(body, 5)
                    app.gzip_store(stamp, body)
            if compress:
                headers.append(("Content-Encoding", "gzip"))
            self._send_bytes(200, body, "text/html; charset=utf-8", headers)

        # --- formulaires --------------------------------------------------------------------------------
        def _form(self) -> dict | None:
            kind = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if kind != "application/x-www-form-urlencoded" or not 0 <= length <= MAX_FORM:
                return None
            try:
                raw = self.rfile.read(length).decode("utf-8")
                fields = urllib.parse.parse_qs(raw, keep_blank_values=True, max_num_fields=40)
            except (ValueError, UnicodeDecodeError):
                return None
            return {key: values[-1] for key, values in fields.items()}

        def _form_token(self) -> str:
            """Jeton des formulaires sans session : le même dans un cookie et dans un champ caché."""
            token = self._cookie(FORM_COOKIE)
            if not 20 <= len(token) <= 80:
                token = secrets.token_urlsafe(24)
                self._set_cookie(FORM_COOKIE, token, max_age=None, same_site="Strict")
            return token

        def _form_token_ok(self, form: dict) -> bool:
            token = self._cookie(FORM_COOKIE)
            return bool(token) and self._same_origin() and hmac.compare_digest(token, str(form.get("csrf", "")))

        def _csrf_ok(self, form: dict) -> bool:
            session = self.session
            return bool(session) and self._same_origin() and hmac.compare_digest(session.csrf_token, str(form.get("csrf", "")))

        def _start_session(self, user) -> None:
            token, session = accounts.create_session(user.id, user_agent=self.headers.get("User-Agent", ""), ip=self._client_ip())
            self._session = session
            self._set_cookie(SESSION_COOKIE, token, max_age=accounts.session_seconds())
            self._set_cookie(FORM_COOKIE, "", max_age=0, same_site="Strict")

        def _login_target(self) -> str:
            """Adresse de la page de connexion, avec la page demandée pour y revenir ensuite."""
            wanted = self._url.path + (f"?{self._url.query}" if self._url.query else "")
            target = safe_next(wanted)
            return "connexion" + (f"?suite={urllib.parse.quote('/' + target, safe='/')}" if target else "")

        # --- aiguillage -------------------------------------------------------------------------------
        def do_GET(self):
            self._dispatch()

        def do_HEAD(self):
            self._dispatch()

        def do_POST(self):
            self._dispatch()

        def _dispatch(self) -> None:
            """Une requête : adresse malformée → 400 ; erreur imprévue → 500, avec la trace dans le journal."""
            try:
                try:
                    self._begin()
                except ValueError:
                    return self._plain(400, "Adresse invalide.\n")
                self._route()
            except (BrokenPipeError, ConnectionResetError):
                pass                                    # le visiteur est parti avant la fin de la réponse
            except Exception:
                app.log.exception("Erreur inattendue : %s %s", self.command, self.path[:200])
                try:
                    self._plain(500, "Erreur interne.\n")
                except Exception:
                    pass

        def _route(self) -> None:
            name = self._url.path.strip("/") if self._url.path.count("/") == 1 else ""
            if name in ROUTES:
                return getattr(self, f"_page_{name}")()
            if self._url.path.startswith("/api/"):
                return self._api(self._url.path[5:])
            if self.command == "POST":
                return self.send_error(405, "Méthode non autorisée")
            return self._static()

        def _static(self) -> None:
            target = self._target()
            if target == manifest or any(folder == target or folder in target.parents for folder in asset_dirs):
                self._cache_control = "no-cache"
                return self._base()
            if not self._public(target):
                return self.send_error(404, "Introuvable")
            is_page = target == root or target.suffix == ".html"
            session = self.session
            if session is None and app.require_login():
                if is_page:
                    return self._redirect(self._login_target(), 302)
                return self._plain(401, "Connexion requise.\n")
            if session is not None and session.user.must_change_password and is_page:
                return self._redirect("compte", 302)
            if is_page:
                return self._serve_page_file(index if target == root else target)
            self._cache_control = "private, max-age=604800" if (root / "audio").resolve() in target.parents else "private, no-cache"
            return self._base()

        def _base(self) -> None:
            if self.command == "HEAD":
                return base.do_HEAD(self)
            return base.do_GET(self)

        # --- API ----------------------------------------------------------------------------------------
        def _api(self, name: str) -> None:
            session = self.session
            if name not in ("me", "progress", "profile"):
                return self._send_json(404, {"error": "introuvable"})
            if session is None:
                return self._send_json(401, {"error": "connexion requise"})
            if name == "me":
                return self._send_json(200, {"user": public_user(session.user)})
            if self.command != "POST":
                if name == "progress":
                    return self._send_json(200, {"data": accounts.exchange_progress(session.user.id, {})})
                return self._send_json(405, {"error": "méthode non autorisée"})
            if not self._same_origin():
                return self._send_json(403, {"error": "origine refusée"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= MAX_PROGRESS:
                return self._send_json(413, {"error": "taille invalide"})
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self._send_json(415, {"error": "JSON attendu"})
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("objet JSON attendu")
            except (ValueError, UnicodeDecodeError) as exc:
                return self._send_json(400, {"error": str(exc)})
            if name == "progress":
                incoming = payload.get("data")
                if not isinstance(incoming, dict):
                    return self._send_json(400, {"error": "champ « data » attendu"})
                return self._send_json(200, {"data": accounts.exchange_progress(session.user.id, incoming)})
            if not hmac.compare_digest(session.csrf_token, self.headers.get("X-CSRF-Token", "")):
                return self._send_json(403, {"error": "jeton refusé"})
            try:
                accounts.update_user(session.user.id, profile=str(payload.get("profile", "")))
            except AccountError as exc:
                return self._send_json(400, {"error": str(exc)})
            return self._send_json(200, {"ok": True})

        # --- connexion, déconnexion --------------------------------------------------------------------------
        def _login_form(self, *, status: int = 200, login: str = "", next_path: str = "", messages=()) -> None:
            self._render("page-auth", "login_title", pages.login_page(
                csrf=self._form_token(), next_path=next_path, login=login, messages=list(messages),
                registration_open=app.registration_open()), status)

        def _page_connexion(self) -> None:
            if self.command != "POST":
                next_path = safe_next(self._arg("suite"))
                if self.session is not None:
                    return self._redirect(next_path, 302)
                if accounts.count_users() == 0:
                    return self._redirect("installation", 302)
                notice = [("ok", pages.texts("ok_logout"))] if self._arg("sortie") else []
                return self._login_form(next_path="/" + next_path if next_path else "", messages=notice)
            form = self._form()
            if form is None:
                return self._plain(400, "Formulaire invalide.\n")
            login, next_path = normalize_login(form.get("identifiant"))[:64], safe_next(form.get("suite"))
            shown_next = "/" + next_path if next_path else ""
            if not self._form_token_ok(form):
                return self._login_form(status=403, login=login, next_path=shown_next,
                                        messages=[("error", message_texts("csrf"))])
            ip = self._client_ip()
            pair = f"{ip}|{login}"
            wait = max(app.pair_throttle.blocked(pair), app.ip_throttle.blocked(ip))
            if wait:
                app.log.warning("Connexion refusée (trop de tentatives) : « %s » depuis %s", login, ip)
                return self._login_form(status=429, login=login, next_path=shown_next,
                                        messages=[("error", message_texts("throttled", minutes=math.ceil(wait / 60)))])
            user = accounts.authenticate(login, form.get("motdepasse", ""))
            if user is None:
                app.pair_throttle.hit(pair)
                app.ip_throttle.hit(ip)
                app.log.warning("Échec de connexion : « %s » depuis %s", login, ip)
                return self._login_form(status=401, login=login, next_path=shown_next,
                                        messages=[("error", message_texts("credentials"))])
            app.pair_throttle.reset(pair)
            self._start_session(user)
            app.log.info("Connexion : %s depuis %s", user.login, ip)
            return self._redirect("compte" if user.must_change_password else next_path)

        def _page_deconnexion(self) -> None:
            session = self.session
            if self.command != "POST":
                return self._redirect("" if session else "connexion", 302)
            form = self._form() or {}
            if session is not None:
                if not self._csrf_ok(form):
                    app.flash(session, "error", message_texts("csrf"))
                    return self._redirect("compte")
                accounts.revoke_session(self._cookie(SESSION_COOKIE))
                app.pop_flash(session)
                app.log.info("Déconnexion : %s", session.user.login)
            self._set_cookie(SESSION_COOKIE, "", max_age=0)
            return self._redirect("connexion?sortie=1")

        # --- inscription, premier démarrage --------------------------------------------------------------------
        def _new_account(self, form: dict, role: str):
            if form.get("motdepasse", "") != form.get("motdepasse2", ""):
                raise AccountError("password_mismatch")
            return accounts.create_user(form.get("identifiant"), form.get("nom") or form.get("identifiant"),
                                        form.get("motdepasse", ""), role=role, profile=form.get("profil"))

        def _page_inscription(self) -> None:
            if not app.registration_open():
                return self._error_page(404)
            if self.session is not None:
                return self._redirect("", 302)
            needs_code = bool(app.registration_code())

            def show(values: dict, messages=(), status: int = 200) -> None:
                self._render("page-auth", "register_title", pages.register_page(
                    config, csrf=self._form_token(), values=values, messages=list(messages),
                    min_length=accounts.password_min_length(), needs_code=needs_code), status)

            if self.command != "POST":
                return show({})
            form = self._form()
            if form is None:
                return self._plain(400, "Formulaire invalide.\n")
            if not self._form_token_ok(form):
                return show(form, [("error", message_texts("csrf"))], 403)
            ip = self._client_ip()
            wait = app.signup_throttle.blocked(ip)
            if wait:
                return show(form, [("error", message_texts("throttled", minutes=math.ceil(wait / 60)))], 429)
            try:
                if needs_code and not hmac.compare_digest(app.registration_code().encode("utf-8"),
                                                          str(form.get("code", "")).strip().encode("utf-8")):
                    app.signup_throttle.hit(ip)
                    raise AccountError("invite_code")
                user = self._new_account(form, "user")
            except AccountError as exc:
                return show(form, [("error", exc.texts())], 422)
            app.signup_throttle.hit(ip)
            self._start_session(user)
            app.log.info("Inscription : %s depuis %s", user.login, ip)
            return self._redirect("")

        def _page_installation(self) -> None:
            if accounts.count_users() > 0:
                return self._error_page(404)
            code = app.ensure_setup_code()

            def show(values: dict, messages=(), status: int = 200) -> None:
                self._render("page-auth", "setup_title", pages.setup_page(
                    config, csrf=self._form_token(), values=values, messages=list(messages),
                    min_length=accounts.password_min_length()), status)

            if self.command != "POST":
                return show({})
            form = self._form()
            if form is None:
                return self._plain(400, "Formulaire invalide.\n")
            if not self._form_token_ok(form):
                return show(form, [("error", message_texts("csrf"))], 403)
            ip = self._client_ip()
            wait = app.ip_throttle.blocked(ip)
            if wait:
                return show(form, [("error", message_texts("throttled", minutes=math.ceil(wait / 60)))], 429)
            try:
                typed = str(form.get("code", "")).strip().lower().replace(" ", "")
                if not hmac.compare_digest(code.encode("utf-8"), typed.encode("utf-8")):
                    app.ip_throttle.hit(ip)
                    raise AccountError("setup_code")
                user = self._new_account(form, "admin")
            except AccountError as exc:
                return show(form, [("error", exc.texts())], 422)
            app.setup_code = ""
            self._start_session(user)
            app.log.warning("Premier démarrage : compte administrateur « %s » créé depuis %s", user.login, ip)
            return self._redirect("")

        # --- mon compte ---------------------------------------------------------------------------------------
        def _page_compte(self) -> None:
            session = self.session
            if session is None:
                return self._redirect("connexion?suite=/compte", 302)
            user = session.user
            if self.command != "POST":
                content = pages.account_page(
                    config, user=user, csrf=session.csrf_token, messages=app.pop_flash(session),
                    summary=accounts.progress_summary(user.id), sessions=accounts.count_sessions(user.id),
                    min_length=accounts.password_min_length())
                return self._render("page-account", "account_title", content)
            form = self._form()
            if form is None:
                return self._plain(400, "Formulaire invalide.\n")
            if not self._csrf_ok(form):
                app.flash(session, "error", message_texts("csrf"))
                return self._redirect("compte")
            action, token = form.get("action", ""), self._cookie(SESSION_COOKIE)
            try:
                if action == "profil":
                    accounts.update_user(user.id, name=form.get("nom"), profile=form.get("profil") or None)
                    app.flash(session, "ok", pages.texts("ok_profile"))
                elif action == "motdepasse":
                    key = f"motdepasse|{user.id}"
                    wait = app.pair_throttle.blocked(key)
                    if wait:
                        raise AccountError("throttled", minutes=math.ceil(wait / 60))
                    if not accounts.check_current_password(user.id, form.get("actuel", "")):
                        app.pair_throttle.hit(key)
                        raise AccountError("password_wrong")
                    if form.get("motdepasse", "") != form.get("motdepasse2", ""):
                        raise AccountError("password_mismatch")
                    if form.get("motdepasse", "") == form.get("actuel", ""):
                        raise AccountError("password_unchanged")
                    accounts.set_password(user.id, form.get("motdepasse", ""), keep_token=token)
                    app.pair_throttle.reset(key)
                    app.flash(session, "ok", pages.texts("ok_password"))
                    app.log.info("Mot de passe changé : %s", user.login)
                elif action == "sessions":
                    closed = accounts.revoke_user_sessions(user.id, keep_token=token)
                    app.flash(session, "ok", pages.texts("ok_sessions", n=closed))
                elif action == "progression":
                    if form.get("confirmer") != "1":
                        raise AccountError("confirm_required")
                    accounts.reset_progress(user.id)
                    app.flash(session, "ok", pages.texts("ok_progress_reset"))
                    app.log.info("Progression effacée : %s", user.login)
            except AccountError as exc:
                app.flash(session, "error", exc.texts())
            return self._redirect("compte")

        # --- utilisateurs (administrateur) ------------------------------------------------------------------------
        def _users_view(self, session, *, values: dict | None = None, messages=(), status: int = 200) -> None:
            users = accounts.list_users()
            target = accounts.get_user(self._arg("u")) if self._arg("u") else None
            content = pages.users_page(
                config, user=session.user, csrf=session.csrf_token, messages=list(messages), users=users,
                summaries={user.id: accounts.progress_summary(user.id) for user in users}, target=target,
                values=values or {}, min_length=accounts.password_min_length())
            self._render("page-account", "users_title", content, status)

        def _page_utilisateurs(self) -> None:
            session = self.session
            if session is None:
                return self._redirect("connexion?suite=/utilisateurs", 302)
            if session.user.must_change_password:
                return self._redirect("compte", 302)
            if not session.user.is_admin:
                return self._error_page(403)
            if self.command != "POST":
                return self._users_view(session, messages=app.pop_flash(session))
            form = self._form()
            if form is None:
                return self._plain(400, "Formulaire invalide.\n")
            if not self._csrf_ok(form):
                app.flash(session, "error", message_texts("csrf"))
                return self._redirect("utilisateurs")
            actor, action, token = session.user, form.get("action", ""), self._cookie(SESSION_COOKIE)
            if action == "creer":
                try:
                    password, generated = form.get("motdepasse", ""), False
                    if not password:
                        password, generated = generate_password(), True
                    created = accounts.create_user(form.get("identifiant"), form.get("nom") or form.get("identifiant"), password,
                                                   role=form.get("role") or "user", profile=form.get("profil"),
                                                   must_change_password=generated)
                except AccountError as exc:
                    return self._users_view(session, values=form, messages=[("error", exc.texts())], status=422)
                app.flash(session, "ok", pages.texts("ok_created", login=created.login))
                if generated:
                    app.flash(session, "ok", pages.texts("temp_password", login=created.login, password=password))
                app.log.info("Compte créé : %s (%s) par %s", created.login, created.role, actor.login)
                return self._redirect("utilisateurs")
            target = accounts.get_user(form.get("id"))
            back = f"utilisateurs?u={target.id}" if target else "utilisateurs"
            try:
                if target is None:
                    raise AccountError("user_missing")
                if action == "modifier":
                    accounts.update_user(target.id, name=form.get("nom"), role=form.get("role") or None,
                                         profile=form.get("profil") or None, active=form.get("actif") == "1",
                                         actor_id=actor.id)
                    app.flash(session, "ok", pages.texts("ok_updated", login=target.login))
                    app.log.info("Compte modifié : %s par %s", target.login, actor.login)
                elif action == "motdepasse":
                    password, generated = form.get("motdepasse", ""), False
                    if not password:
                        password, generated = generate_password(), True
                    accounts.set_password(target.id, password, must_change_password=generated or form.get("changer") == "1",
                                          keep_token=token if target.id == actor.id else None)
                    app.flash(session, "ok", pages.texts("ok_password_set", login=target.login))
                    if generated:
                        app.flash(session, "ok", pages.texts("temp_password", login=target.login, password=password))
                    app.log.info("Mot de passe de %s redéfini par %s", target.login, actor.login)
                elif action == "sessions":
                    closed = accounts.revoke_user_sessions(target.id, keep_token=token if target.id == actor.id else None)
                    app.flash(session, "ok", pages.texts("ok_sessions_closed", login=target.login, n=closed))
                elif action == "supprimer":
                    if form.get("confirmer") != "1":
                        raise AccountError("confirm_required")
                    accounts.delete_user(target.id, actor_id=actor.id)
                    app.flash(session, "ok", pages.texts("ok_deleted", login=target.login))
                    app.log.warning("Compte supprimé : %s par %s", target.login, actor.login)
                    back = "utilisateurs"
            except AccountError as exc:
                app.flash(session, "error", exc.texts())
            return self._redirect(back)

    return Handler


def make_server(config, host: str = "127.0.0.1", port: int = 8000, app: WebApp | None = None):
    """Serveur avec comptes ; ``server.app`` donne accès aux comptes (tests, arrêt propre)."""
    app = app or WebApp(config)
    server = admin.make_server(config, host, port, handler=make_handler(app))
    server.app = app
    return server


def serve(config, host: str = "127.0.0.1", port: int = 8000, logger: logging.Logger | None = None) -> None:
    app = WebApp(config, logger)
    try:
        with make_server(config, host, port, app) as httpd:
            shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
            address = f"http://{shown}:{httpd.server_address[1]}/"
            print(f"Site disponible sur {address}  (Ctrl+C pour arrêter)", flush=True)
            if host == "0.0.0.0":
                print("Accessible aussi depuis les autres appareils du réseau local, à l'adresse IP de cet ordinateur.", flush=True)
            if app.accounts.count_users() == 0:
                print(f"Aucun compte pour l'instant. Ouvrez {address}installation et saisissez le code "
                      f"d'installation : {app.ensure_setup_code(announce=False)}", flush=True)
                print("  (ou créez l'administrateur ici : python3 manage.py users add <identifiant> --role admin)", flush=True)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\nServeur arrêté.")
    finally:
        app.close()
