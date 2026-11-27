"""Tests des comptes utilisateurs : mots de passe, sessions, progression par compte, et le
serveur web qui les met en œuvre (connexion, protections, gestion des utilisateurs).

Aucun réseau : le serveur écoute sur 127.0.0.1, dans un projet temporaire.
"""

from __future__ import annotations

import datetime as dt
import gzip
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import ROOT, clean_env, make_wav  # noqa: E402

from frkh import accounts as accounts_module  # noqa: E402
from frkh import db, progress_sync, webapp  # noqa: E402
from frkh.accounts import (AccountError, Accounts, Throttle, generate_password, hash_password,  # noqa: E402
                           needs_rehash, verify_password)
from frkh.config import load_config  # noqa: E402

SECRET = "CLE-SECRETE-DU-FICHIER-ENV"
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"
CHROME_ANDROID = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0.0.0 Mobile Safari/537.36")
PAGE = ('<!DOCTYPE html><html lang="fr" data-profile="fr" data-root="{root}"><head><meta charset="utf-8">'
        '<title>t</title></head><body><p>{body}</p></body></html>')


class AccountsCase(unittest.TestCase):
    """Base : un projet vide dans un dossier temporaire, et un hachage volontairement rapide."""

    server_config: dict = {}

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="frkh-comptes-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        for patcher in (mock.patch.dict(os.environ, clean_env(), clear=True),
                        mock.patch.multiple(accounts_module, SCRYPT_N=2 ** 8, SCRYPT_P=1)):
            patcher.start()
            self.addCleanup(patcher.stop)
        (self.root / "config").mkdir()
        (self.root / "config" / "config.json").write_text(json.dumps({"server": self.server_config}), encoding="utf-8")
        self.config = load_config(self.root)
        self.config.paths.ensure()
        self.now = 1_800_000_000.0

    def clock(self) -> float:
        return self.now

    def store(self) -> Accounts:
        store = Accounts(self.config, self.clock)
        self.addCleanup(store.close)
        return store


class PasswordTest(unittest.TestCase):
    def test_hash_is_salted_verifiable_and_never_the_password(self):
        with mock.patch.multiple(accounts_module, SCRYPT_N=2 ** 8, SCRYPT_P=1):
            first, second = hash_password("correct horse"), hash_password("correct horse")
            self.assertTrue(first.startswith("scrypt$256$8$1$"))
            self.assertNotEqual(first, second, "un sel différent à chaque fois")
            self.assertNotIn("correct horse", first)
            self.assertTrue(verify_password("correct horse", first))
            self.assertFalse(verify_password("correct horsf", first))
            self.assertFalse(verify_password("", first))
            self.assertFalse(needs_rehash(first))
        self.assertTrue(needs_rehash(first), "paramètres plus faibles que le réglage courant : à refaire")

    def test_unicode_passwords_match_whatever_the_keyboard(self):
        with mock.patch.multiple(accounts_module, SCRYPT_N=2 ** 8, SCRYPT_P=1):
            stored = hash_password("café-ខ្មែរ")
            self.assertTrue(verify_password("café-ខ្មែរ", stored), "é précomposé ou décomposé : même mot de passe")

    def test_unreadable_or_absurd_hashes_are_refused(self):
        for stored in ("", "clair", "scrypt$16384$8$5$@@@$@@@", "scrypt$1073741824$8$1$AAAA$AAAA", "scrypt$15$8$1$AAAA$AAAA",
                       "pbkdf2_sha256$0$AAAA$AAAA", "md5$abc", None):
            self.assertFalse(verify_password("x", stored), repr(stored))

    def test_pbkdf2_is_used_when_scrypt_is_missing(self):
        """Python compilé sans scrypt : PBKDF2 prend le relais, et ses empreintes restent vérifiables."""
        import hashlib
        import types
        limited = types.SimpleNamespace(pbkdf2_hmac=hashlib.pbkdf2_hmac, sha256=hashlib.sha256)
        with mock.patch.object(accounts_module, "hashlib", limited), mock.patch.object(accounts_module, "PBKDF2_ITERATIONS", 1000):
            stored = hash_password("mot de passe")
            self.assertFalse(needs_rehash(stored))
        self.assertTrue(stored.startswith("pbkdf2_sha256$1000$"))
        self.assertTrue(verify_password("mot de passe", stored))
        self.assertFalse(verify_password("autre", stored))
        self.assertTrue(needs_rehash(stored), "avec scrypt disponible, l'empreinte sera refaite à la connexion")

    def test_generated_passwords_are_readable_and_distinct(self):
        values = {generate_password() for _ in range(50)}
        self.assertEqual(len(values), 50)
        for value in values:
            self.assertRegex(value, r"^[a-hjkmnp-z2-9]{4}-[a-hjkmnp-z2-9]{4}-[a-hjkmnp-z2-9]{4}$")


class ThrottleTest(unittest.TestCase):
    def test_blocks_after_the_limit_then_reopens(self):
        now = [1000.0]
        throttle = Throttle(3, 60, lambda: now[0])
        for _ in range(3):
            self.assertEqual(throttle.blocked("a"), 0)
            throttle.hit("a")
        self.assertGreater(throttle.blocked("a"), 0)
        self.assertEqual(throttle.blocked("b"), 0, "les autres clés ne sont pas touchées")
        now[0] += 61
        self.assertEqual(throttle.blocked("a"), 0)
        throttle.hit("a")
        throttle.reset("a")
        self.assertEqual(throttle.blocked("a"), 0)


class AccountStoreTest(AccountsCase):
    def test_accounts_are_validated(self):
        store = self.store()
        user = store.create_user(" Dara ", "  Dara   Sok ", "motdepasse-dara", profile="km")
        self.assertEqual((user.login, user.name, user.role, user.profile, user.active), ("dara", "Dara Sok", "user", "km", True))
        cases = (("da", "x", "motdepasse-1", {}, "login_invalid"), ("Dara Sok", "x", "motdepasse-1", {}, "login_invalid"),
                 ("../etc", "x", "motdepasse-1", {}, "login_invalid"), ("dara", "x", "motdepasse-1", {}, "login_taken"),
                 ("DARA", "x", "motdepasse-1", {}, "login_taken"), ("alex", "x" * 61, "motdepasse-1", {}, "name_invalid"),
                 ("alex", "x", "court", {}, "password_short"), ("alex", "x", "x" * 300, {}, "password_long"),
                 ("alexandre", "x", "Alexandre", {}, "password_same_as_login"),
                 ("alex", "x", "motdepasse-1", {"role": "root"}, "role_invalid"),
                 ("alex", "x", "motdepasse-1", {"profile": "de"}, "profile_invalid"))
        for login, name, password, extra, code in cases:
            with self.assertRaises(AccountError, msg=f"{login} / {code}") as caught:
                store.create_user(login, name, password, **extra)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(set(caught.exception.texts()), {"fr", "en", "km"})
        self.assertEqual(store.count_users(), 1)

    def test_passwords_are_stored_hashed_and_checked(self):
        store = self.store()
        user = store.create_user("dara", "Dara", "motdepasse-dara")
        raw = self.root.joinpath("database", "learning.db").read_bytes()
        self.assertNotIn(b"motdepasse-dara", raw)
        self.assertEqual(store.authenticate("DARA ", "motdepasse-dara").id, user.id)
        for login, password in (("dara", "motdepasse-darA"), ("dara", ""), ("inconnu", "motdepasse-dara"), ("", ""),
                                ("dara", "x" * 5000)):
            self.assertIsNone(store.authenticate(login, password), f"{login!r}")
        store.update_user(user.id, active=False)
        self.assertIsNone(store.authenticate("dara", "motdepasse-dara"), "un compte désactivé ne se connecte pas")

    def test_weaker_hashes_are_upgraded_at_login(self):
        store = self.store()
        user = store.create_user("dara", "Dara", "motdepasse-dara")
        with mock.patch.object(accounts_module, "SCRYPT_N", 2 ** 9):
            self.assertIsNotNone(store.authenticate("dara", "motdepasse-dara"))
            row = store._conn.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
            self.assertTrue(row["password_hash"].startswith("scrypt$512$"))
            self.assertIsNotNone(store.authenticate("dara", "motdepasse-dara"))

    def test_sessions_expire_slide_and_can_be_revoked(self):
        store = self.store()
        user = store.create_user("dara", "Dara", "motdepasse-dara")
        token, session = store.create_session(user.id, user_agent="Navigateur", ip="10.0.0.2")
        self.assertEqual((session.user.login, session.ip), ("dara", "10.0.0.2"))
        self.assertGreaterEqual(len(token), 40)
        self.assertNotIn(token.encode(), self.root.joinpath("database", "learning.db").read_bytes(),
                         "la base ne garde que l'empreinte du jeton")
        self.assertIsNone(store.session("un-autre-jeton"))
        self.assertIsNone(store.session(""))
        self.now += 20 * 86400
        self.assertIsNotNone(store.session(token), "session encore valable, et prolongée")
        self.now += 20 * 86400
        self.assertIsNotNone(store.session(token), "une visite repousse l'échéance")
        self.now += 31 * 86400
        self.assertIsNone(store.session(token), "trente jours sans visite : session expirée")

        first, _ = store.create_session(user.id)
        second, _ = store.create_session(user.id)
        self.assertEqual(store.count_sessions(user.id), 2)
        self.assertEqual(store.revoke_user_sessions(user.id, keep_token=first), 1)
        self.assertIsNotNone(store.session(first))
        self.assertIsNone(store.session(second))
        store.set_password(user.id, "nouveau-motdepasse")
        self.assertIsNone(store.session(first), "changer le mot de passe ferme les sessions")
        third, _ = store.create_session(user.id)
        store.update_user(user.id, active=False)
        self.assertIsNone(store.session(third), "désactiver un compte ferme ses sessions")

    def test_last_administrator_and_own_account_are_protected(self):
        store = self.store()
        admin = store.create_user("admin", "Admin", "motdepasse-admin", role="admin")
        user = store.create_user("dara", "Dara", "motdepasse-dara")
        for action in (lambda: store.update_user(admin.id, role="user"), lambda: store.update_user(admin.id, active=False),
                       lambda: store.delete_user(admin.id)):
            with self.assertRaises(AccountError) as caught:
                action()
            self.assertEqual(caught.exception.code, "last_admin")
        store.update_user(user.id, role="admin")
        for action in (lambda: store.delete_user(admin.id, actor_id=admin.id),
                       lambda: store.update_user(admin.id, active=False, actor_id=admin.id)):
            with self.assertRaises(AccountError) as caught:
                action()
            self.assertEqual(caught.exception.code, "self_forbidden")
        store.update_user(admin.id, role="user", actor_id=admin.id)       # un autre administrateur existe
        self.assertEqual(store.get_user(admin.id).role, "user")
        store.delete_user(admin.id, actor_id=user.id)
        self.assertIsNone(store.get_user(admin.id))
        with self.assertRaises(AccountError):
            store.delete_user(admin.id)

    def test_progress_belongs_to_each_account(self):
        store = self.store()
        dara = store.create_user("dara", "Dara", "motdepasse-dara")
        alex = store.create_user("alex", "Alex", "motdepasse-alex")
        sent = {"frkh-done2-km": json.dumps({"1": {"d": 1, "t": 1000}, "2": {"d": 1, "t": 2000}}),
                "frkh-days-km": json.dumps(["2026-03-01"]),
                "frkh-boxes-km-fr": json.dumps({"bonjour": {"b": 2, "t": 1500}}),
                "frkh-profile": "km", "n-importe-quoi": "{}", "frkh-done2-km-x": "{}"}
        state = store.exchange_progress(dara.id, sent)
        self.assertEqual(set(state), {"frkh-done2-km", "frkh-days-km", "frkh-boxes-km-fr"}, "seules les clés de progression")
        self.assertEqual(store.exchange_progress(alex.id, {}), {}, "un autre compte ne voit rien")
        # Un autre appareil du même compte : fusion entrée par entrée, la plus récente gagne.
        merged = store.exchange_progress(dara.id, {
            "frkh-done2-km": json.dumps({"2": {"d": 0, "t": 3000}, "3": {"d": 1, "t": 500}}),
            "frkh-days-km": json.dumps(["2026-03-02", "pas une date"])})
        self.assertEqual(json.loads(merged["frkh-done2-km"]),
                         {"1": {"d": 1, "t": 1000.0}, "2": {"d": 0, "t": 3000.0}, "3": {"d": 1, "t": 500.0}})
        self.assertEqual(json.loads(merged["frkh-days-km"]), ["2026-03-01", "2026-03-02"])
        self.assertEqual(store.progress_summary(dara.id), {"lessons": 2, "days": 2, "streak": 0, "cards": 1, "last": 3000.0})
        store.delete_user(dara.id)
        self.assertEqual(store._conn.execute("SELECT COUNT(*) FROM user_progress").fetchone()[0], 0,
                         "la progression disparaît avec le compte")

    def test_reset_is_not_undone_by_another_device(self):
        store = self.store()
        user = store.create_user("dara", "Dara", "motdepasse-dara")
        before, after = int(self.now * 1000) - 5000, int(self.now * 1000) + 5000
        old = {"frkh-done2-fr": json.dumps({"1": {"d": 1, "t": before}}), "frkh-days-fr": json.dumps(["2020-01-01"]),
               "frkh-boxes-fr-km": json.dumps({"ខ្ញុំ": {"b": 3, "t": before}})}
        store.exchange_progress(user.id, old)
        store.reset_progress(user.id)
        self.assertEqual(store.progress_summary(user.id)["lessons"], 0)
        # L'autre appareil renvoie son ancienne progression : elle est ignorée, et on lui dit de l'effacer.
        state = store.exchange_progress(user.id, old)
        self.assertEqual(state, {"frkh-done2-fr": "{}", "frkh-days-fr": "[]", "frkh-boxes-fr-km": "{}"})
        self.assertEqual(store.exchange_progress(user.id, {}), {})
        fresh = store.exchange_progress(user.id, {"frkh-done2-fr": json.dumps({"1": {"d": 1, "t": before}, "2": {"d": 1, "t": after}})})
        self.assertEqual(json.loads(fresh["frkh-done2-fr"]), {"2": {"d": 1, "t": float(after)}}, "ce qui suit la remise à zéro est gardé")

    def test_shared_progress_of_the_old_server_can_be_imported(self):
        store = self.store()
        user = store.create_user("dara", "Dara", "motdepasse-dara")
        progress_sync.exchange(self.config, {"frkh-done2-fr": json.dumps({"4": {"d": 1, "t": 10}})})
        self.assertEqual(store.import_shared_progress(user.id), 1)
        self.assertEqual(store.progress_summary(user.id)["lessons"], 1)

    def test_progress_detail_counts_streaks_known_cards_and_due_reviews(self):
        store = self.store()
        user = store.create_user("dara", "Dara", "motdepasse-dara")
        today, now, hour, day = store.today(), int(self.now * 1000), 3600000, 86400000

        def ago(days: int) -> str:
            return (today - dt.timedelta(days=days)).isoformat()

        store.exchange_progress(user.id, {
            "frkh-done2-km": json.dumps({"1": {"d": 1, "t": now - hour}, "2": {"d": 0, "t": now}}),
            "frkh-done2-fr": json.dumps({"2": {"d": 1, "t": now - day}}),
            "frkh-days-km": json.dumps([ago(0), ago(1), ago(2), ago(10), ago(11), ago(12), ago(13)]),
            # Même langue étudiée sous deux profils : pour une même carte, la révision la plus récente compte.
            "frkh-boxes-km-fr": json.dumps({"bonjour": {"b": 1, "t": now - 2 * day}, "merci": {"b": 1, "t": now - 2 * day}}),
            "frkh-boxes-fr-fr": json.dumps({"bonjour": {"b": 5, "t": now}, "pardon": {"b": 2, "t": now - 10 * day}}),
            "frkh-boxes-km-en": json.dumps({"hello": {"b": 3, "t": now - hour}})})
        detail = store.progress_detail(user.id)
        self.assertEqual(detail["lessons"], {1: float(now - hour), 2: float(now - day)}, "terminée sous un profil : terminée")
        self.assertEqual((detail["streak"], detail["best_streak"], len(detail["days"])), (3, 4, 7))
        self.assertEqual(detail["langs"]["fr"], {"cards": 3, "known": 1, "due": 2, "boxes": [1, 1, 0, 0, 1], "last": float(now)})
        self.assertEqual((detail["langs"]["en"]["known"], detail["langs"]["en"]["due"]), (1, 0), "boîte 3 : revue dans quatre jours")
        self.assertEqual((detail["cards"], detail["due"], detail["last"]), (4, 2, float(now)))
        # La série tient encore si le dernier jour actif est hier ; elle tombe après un jour sans rien.
        self.assertEqual(accounts_module.streaks([ago(1), ago(2)], today), (2, 2))
        self.assertEqual(accounts_module.streaks([ago(2), ago(3), "pas une date"], today), (0, 2))
        self.assertEqual(accounts_module.streaks([], today), (0, 0))
        self.assertEqual(store.lessons(), [], "pas encore de table des leçons : liste vide, pas d'erreur")
        # Un navigateur peut envoyer n'importe quelle clé : ce qui n'est pas un numéro de leçon est ignoré.
        store.exchange_progress(user.id, {"frkh-done2-en": json.dumps({"²": {"d": 1, "t": now}, "x": {"d": 1, "t": now},
                                                                       "1234567": {"d": 1, "t": now}, "٣": {"d": 1, "t": now}})})
        self.assertEqual(sorted(store.progress_detail(user.id)["lessons"]), [1, 2])

    def test_sessions_are_listed_and_closed_one_by_one(self):
        store = self.store()
        dara = store.create_user("dara", "Dara", "motdepasse-dara")
        alex = store.create_user("alex", "Alex", "motdepasse-alex")
        laptop, _ = store.create_session(dara.id, user_agent=FIREFOX_LINUX, ip="192.168.1.20")
        self.now += 60
        phone, session = store.create_session(dara.id, user_agent=CHROME_ANDROID, ip="192.168.1.21")
        other, _ = store.create_session(alex.id)
        listed = store.list_sessions(dara.id)
        self.assertEqual([(item.ip, item.public_id == session.public_id) for item in listed],
                         [("192.168.1.21", True), ("192.168.1.20", False)], "la plus récemment active d'abord")
        self.assertEqual(len(session.public_id), 16)
        self.assertNotIn(session.public_id, phone, "l'identifiant public ne dit rien du jeton")
        for owner, wanted in ((alex.id, session.public_id), (dara.id, "0" * 16), (dara.id, ""), (dara.id, "%" * 16), (dara.id, None)):
            self.assertFalse(store.revoke_session_id(owner, wanted), repr(wanted))
        self.assertEqual(store.count_sessions(dara.id), 2)
        self.assertTrue(store.revoke_session_id(dara.id, session.public_id))
        self.assertIsNone(store.session(phone))
        self.assertIsNotNone(store.session(laptop))
        self.assertIsNotNone(store.session(other))
        self.now += store.session_seconds() + 1
        self.assertEqual(store.list_sessions(dara.id), [], "les sessions expirées ne sont pas listées")
        self.assertEqual(store.list_sessions(9999), [])

    def test_invitation_links_work_once_and_expire(self):
        store = self.store()
        with self.assertRaises(AccountError):
            store.create_invite(role="roi")
        with self.assertRaises(AccountError):
            store.create_invite(profile="de")
        token, link = store.create_invite(role="admin", profile="km", note="  Tante   Sophea ", created_by="stefan")
        self.assertEqual((link.kind, link.role, link.profile, link.note, link.created_by), ("invite", "admin", "km", "Tante Sophea", "stefan"))
        self.assertEqual(link.expires_at - link.created_at, 7 * 86400)
        stored = "\n".join(str(tuple(row)) for row in store._conn.execute("SELECT * FROM account_links"))
        self.assertNotIn(token, stored, "la base ne garde que l'empreinte du lien")
        self.assertEqual(store.get_link(token, "invite"), link)
        for wrong in ("", None, token + "x", "x" * 300):
            self.assertIsNone(store.get_link(wrong, "invite"), repr(wrong))
        self.assertIsNone(store.get_link(token, "reset"), "une invitation ne sert pas à changer un mot de passe")
        # Une saisie refusée ne consomme pas le lien.
        store.create_user("dara", "Dara", "motdepasse-dara")
        for login, password in (("dara", "motdepasse-sophea"), ("sophea", "court")):
            with self.assertRaises(AccountError):
                store.use_invite(token, login, "Sophea", password)
        self.assertIsNotNone(store.get_link(token, "invite"))
        user, used = store.use_invite(token, "Sophea", "", "motdepasse-sophea")
        self.assertEqual((user.login, user.name, user.role, user.profile, used.public_id), ("sophea", "Sophea", "admin", "km", link.public_id))
        with self.assertRaises(AccountError) as refused:
            store.use_invite(token, "autre", "Autre", "motdepasse-autre")
        self.assertEqual(refused.exception.code, "link_invalid")
        # Expiration, liste des invitations en attente, annulation.
        short, _ = store.create_invite(days=1)
        kept, pending = store.create_invite(note="Alex")
        self.assertEqual([item.note for item in store.list_links("invite")], ["Alex", ""])
        self.now += 86400 + 1
        self.assertIsNone(store.get_link(short, "invite"))
        self.assertEqual([item.note for item in store.list_links("invite")], ["Alex"])
        for wrong in ("", "zz", "0" * 16, None):
            self.assertIsNone(store.revoke_link(wrong))
        self.assertEqual(store.revoke_link(pending.public_id).note, "Alex")
        self.assertIsNone(store.get_link(kept, "invite"))

    def test_new_password_links_replace_each_other_and_close_sessions(self):
        store = self.store()
        dara = store.create_user("dara", "Dara", "motdepasse-dara", must_change_password=True)
        session_token, _ = store.create_session(dara.id)
        first, _ = store.create_reset(dara.id, created_by="stefan")
        second, link = store.create_reset(dara.id, created_by="stefan")
        self.assertEqual(link.expires_at - link.created_at, 24 * 3600)
        self.assertIsNone(store.get_link(first, "reset"), "un nouveau lien remplace l'ancien")
        self.assertIsNone(store.get_link(second, "invite"))
        with self.assertRaises(AccountError):
            store.use_reset(second, "court")
        user, _ = store.use_reset(second, "nouveau-secret")
        self.assertEqual((user.login, user.must_change_password), ("dara", False))
        self.assertIsNotNone(store.authenticate("dara", "nouveau-secret"))
        self.assertIsNone(store.session(session_token), "les sessions du compte sont fermées")
        with self.assertRaises(AccountError):
            store.use_reset(second, "encore-un-autre")
        # Un mot de passe changé autrement, un compte désactivé ou supprimé : le lien ne vaut plus rien.
        third, _ = store.create_reset(dara.id)
        store.set_password(dara.id, "change-ailleurs")
        self.assertIsNone(store.get_link(third, "reset"))
        fourth, _ = store.create_reset(dara.id)
        store.create_user("admin", "Admin", "motdepasse-admin", role="admin")
        store.update_user(dara.id, active=False)
        self.assertIsNone(store.get_link(fourth, "reset"))
        with self.assertRaises(AccountError):
            store.create_reset(dara.id)
        store.update_user(dara.id, active=True)
        self.assertIsNotNone(store.get_link(fourth, "reset"))
        self.now += 24 * 3600 + 1
        self.assertIsNone(store.get_link(fourth, "reset"))
        with self.assertRaises(AccountError):
            store.create_reset(9999)

    def test_journal_keeps_filters_and_forgets_events(self):
        store = self.store()
        dara = store.create_user("dara", "Dara", "motdepasse-dara")
        with self.assertRaises(ValueError):
            store.record_event("n-importe-quoi", user=dara)
        store.record_event("login", user=dara, ip="192.168.1.20")
        store.record_event("login_failed", ip="192.168.1.99")
        store.record_event("role_changed", user=dara, actor="admin", detail="admin")
        events = store.list_events()
        self.assertEqual([(event.kind, event.login, event.actor, event.detail) for event in events],
                         [("role_changed", "dara", "admin", "admin"), ("login_failed", "", "", ""), ("login", "dara", "", "")])
        self.assertEqual([event.kind for event in store.list_events(kinds=accounts_module.EVENT_GROUPS["failures"])], ["login_failed"])
        self.assertEqual([event.kind for event in store.list_events(user_id=dara.id)], ["role_changed", "login"])
        self.assertEqual([event.kind for event in store.list_events(before=events[0].id, limit=1)], ["login_failed"])
        self.assertEqual(store.list_events(kinds=["inconnu"]), [])
        store.delete_user(dara.id)
        self.assertEqual(len(store.list_events(user_id=dara.id)), 2, "l'historique survit au compte")
        # Au-delà de la durée de conservation (180 jours par défaut), les anciens événements sont effacés.
        self.now += 200 * 86400
        for _ in range(60):
            store.record_event("logout")
        kept = store.list_events(limit=1000)
        self.assertEqual({event.kind for event in kept}, {"logout"})
        self.assertEqual(len(kept), 60)


# --- Serveur ----------------------------------------------------------------------------------------

class Browser:
    """Client HTTP minimal qui garde ses cookies, comme un navigateur."""

    def __init__(self, port: int):
        self.port = port
        self.cookies: dict[str, str] = {}
        self.origin = f"http://127.0.0.1:{port}"

    def request(self, method: str, path: str, *, form: dict | None = None, data=None, headers: dict | None = None):
        sent = {"Host": f"127.0.0.1:{self.port}"}
        if self.cookies:
            sent["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        body = None
        if form is not None:
            body = urllib.parse.urlencode(form).encode("utf-8")
            sent.update({"Content-Type": "application/x-www-form-urlencoded", "Origin": self.origin})
        elif data is not None:
            body = json.dumps(data).encode("utf-8")
            sent.update({"Content-Type": "application/json", "Origin": self.origin})
        sent.update(headers or {})
        sent = {name: value for name, value in sent.items() if value is not None}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            conn.request(method, path, body=body, headers=sent)
            response = conn.getresponse()
            payload = response.read()
            self.last_cookies = response.msg.get_all("Set-Cookie") or []
            for cookie in self.last_cookies:
                name, _, value = cookie.split(";", 1)[0].partition("=")
                if "Max-Age=0" in cookie or not value:
                    self.cookies.pop(name, None)
                else:
                    self.cookies[name] = value
            if response.getheader("Content-Encoding") == "gzip":
                payload = gzip.decompress(payload)
            return response.status, {name.lower(): value for name, value in response.getheaders()}, payload.decode("utf-8", "replace")
        finally:
            conn.close()

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def token(self, path: str) -> str:
        """Jeton anti-CSRF du premier formulaire de la page."""
        _, _, body = self.get(path)
        found = re.search(r'name="csrf" value="([^"]+)"', body)
        return found.group(1) if found else ""

    def post(self, path: str, form: dict, *, page: str | None = None, **kwargs):
        return self.request("POST", path, form={"csrf": self.token(page or path), **form}, **kwargs)

    def login(self, login: str, password: str, **extra):
        return self.post("/connexion", {"identifiant": login, "motdepasse": password, **extra})


class ServerCase(AccountsCase):
    with_users = True

    def setUp(self):
        super().setUp()
        for name in ("templates", "css", "js"):
            shutil.copytree(ROOT / name, self.root / name)
        files = {"index.html": PAGE.format(root=".", body="accueil"),
                 "lessons/lesson-001.html": PAGE.format(root="..", body="leçon une"),
                 "data/lessons.json": "[]", ".env": "GOOGLE_TTS_API_KEY=" + SECRET, "manage.py": "print('code')",
                 "manifest.webmanifest": "{}"}
        for name, body in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        (self.root / "audio" / "fr-FR").mkdir(parents=True, exist_ok=True)
        self.wav = make_wav(24000, 0.2)
        (self.root / "audio" / "fr-FR" / "bonjour_000000000000.wav").write_bytes(self.wav)
        self.app = webapp.WebApp(self.config, clock=self.clock)
        self.app.log.disabled = True
        self.addCleanup(setattr, self.app.log, "disabled", False)
        self.accounts = self.app.accounts
        if self.with_users:
            self.admin = self.accounts.create_user("admin", "Administratrice", "motdepasse-admin", role="admin")
            self.dara = self.accounts.create_user("dara", "Dara <Sok>", "motdepasse-dara", profile="km")
        self.server = webapp.make_server(self.config, "127.0.0.1", 0, self.app)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.app.close)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]

    def browser(self, login: str | None = None, password: str | None = None) -> Browser:
        browser = Browser(self.port)
        if login:
            status, headers, _ = browser.login(login, password or f"motdepasse-{login}")
            self.assertEqual((status, headers["location"]), (303, "./"), f"connexion de {login}")
        return browser


class AccessTest(ServerCase):
    def test_site_requires_an_account_but_the_login_page_works(self):
        visitor = self.browser()
        for path, target in (("/", "./connexion"), ("/index.html", "./connexion?suite=/index.html"),
                             ("/lessons/lesson-001.html", "../connexion?suite=/lessons/lesson-001.html"),
                             ("/compte", "./connexion?suite=/compte"), ("/utilisateurs", "./connexion?suite=/utilisateurs")):
            status, headers, body = visitor.get(path)
            self.assertEqual((status, headers.get("location")), (302, target), path)
            self.assertNotIn("accueil", body)
        for path in ("/audio/fr-FR/bonjour_000000000000.wav", "/data/lessons.json", "/api/progress", "/api/me"):
            self.assertEqual(visitor.get(path)[0], 401, path)
        for path in ("/css/style.css", "/css/account.css", "/js/account.js", "/js/app.js", "/manifest.webmanifest"):
            self.assertEqual(visitor.get(path)[0], 200, f"{path} sert à la page de connexion")
        status, headers, body = visitor.get("/connexion")
        self.assertEqual(status, 200)
        self.assertIn('name="motdepasse"', body)
        self.assertIn('"user":null', body)
        self.assertEqual(headers["cache-control"], "no-store")
        self.assertEqual((headers["x-frame-options"], headers["x-content-type-options"]), ("DENY", "nosniff"))
        self.assertEqual(visitor.get("/inscription")[0], 404, "inscription fermée par défaut")
        self.assertEqual(visitor.get("/installation")[0], 404, "des comptes existent déjà")

    def test_login_opens_the_site_and_logout_closes_it(self):
        user = self.browser()
        status, _, body = user.login("dara", "mauvais-motdepasse")
        self.assertEqual(status, 401)
        self.assertIn("Identifiant ou mot de passe incorrect", body)
        self.assertNotIn("frkh_session", user.cookies)
        status, headers, _ = user.login("Dara", "motdepasse-dara", suite="/lessons/lesson-001.html")
        self.assertEqual((status, headers["location"]), (303, "./lessons/lesson-001.html"))
        cookie = next(c for c in user.last_cookies if c.startswith("frkh_session="))
        for flag in ("HttpOnly", "SameSite=Lax", "Path=/", "Max-Age=2592000"):
            self.assertIn(flag, cookie)
        self.assertNotIn("Secure", cookie, "en HTTP local, le cookie doit rester utilisable")

        status, headers, body = user.get("/")
        self.assertEqual(status, 200)
        self.assertIn("accueil", body)
        self.assertIn('window.FRKH_ACCOUNT={"user":{"id":%d,"login":"dara"' % self.dara.id, body)
        self.assertIn("Dara \\u003cSok\\u003e", body, "le nom est échappé dans le script")
        self.assertNotIn("<Sok>", body)
        self.assertIn('href="./css/account.css', body)
        self.assertIn('src="./js/account.js', body)
        self.assertEqual(headers["cache-control"], "private, no-cache")
        status, _, body = user.get("/lessons/lesson-001.html")
        self.assertIn("leçon une", body)
        self.assertIn('src="../js/account.js', body, "les chemins suivent la profondeur de la page")
        status, headers, raw = user.get("/audio/fr-FR/bonjour_000000000000.wav", headers={"Range": "bytes=0-9"})
        self.assertEqual((status, headers["content-range"]), (206, f"bytes 0-9/{len(self.wav)}"))
        self.assertEqual(json.loads(user.get("/api/me")[2])["user"]["login"], "dara")
        self.assertEqual(user.get("/connexion")[1]["location"], "./", "déjà connecté : pas de formulaire")

        token = user.cookies["frkh_session"]
        status, headers, _ = user.post("/deconnexion", {}, page="/compte")
        self.assertEqual((status, headers["location"]), (303, "./connexion?sortie=1"))
        self.assertNotIn("frkh_session", user.cookies)
        user.cookies["frkh_session"] = token
        self.assertEqual(user.get("/")[0], 302, "l'ancien jeton ne vaut plus rien")

    def test_private_files_stay_private_even_when_signed_in(self):
        user = self.browser("dara")
        paths = ["/.env", "/manage.py", "/config/config.json", "/database/learning.db", "/database/", "/templates/base.html",
                 "/lessons/../.env", "/lessons/%2e%2e/.env", "/css/..%2f.env", "/audio/%2e%2e/database/learning.db",
                 "/lessons/..%5c.env", "/%2e%2e/%2e%2e/etc/passwd", "/lessons//..//.env", "/lessons/", "/audio/fr-FR/"]
        for browser, refusals in ((user, (404,)), (self.browser(), (401, 404))):
            for path in paths:
                status, _, body = browser.get(path)
                self.assertIn(status, refusals, f"{path} ne doit pas être accessible")
                self.assertNotIn(SECRET, body, path)
        if hasattr(os, "symlink"):
            try:
                os.symlink(self.root / ".env", self.root / "lessons" / "lien.html")
            except OSError:
                return
            status, _, body = user.get("/lessons/lien.html")
            self.assertEqual(status, 404, "un lien symbolique ne doit pas faire sortir du site")
            self.assertNotIn(SECRET, body)

    def test_malformed_requests_get_a_clean_refusal(self):
        user = self.browser("dara")
        self.assertEqual(user.get("http://[adresse")[0], 400, "adresse impossible à analyser")
        self.assertEqual(user.get("//[adresse")[0], 404)
        self.assertEqual(user.get("/?" + "&".join(f"a{i}=1" for i in range(50)))[0], 200, "trop de paramètres : ignorés")
        self.assertEqual(user.get("/api/inconnu")[0], 404)
        self.assertEqual(user.get("/connexion/")[0], 404)
        self.assertEqual(user.get("/")[0], 200, "le serveur répond toujours")

    def test_return_address_never_leaves_the_site(self):
        for wanted in ("//evil.example/", "https://evil.example/", "/\\evil.example", "evil.example", "/connexion",
                       "/api/me", "/a\r\nSet-Cookie: x=1"):
            user = self.browser()
            status, headers, _ = user.login("dara", "motdepasse-dara", suite=wanted)
            self.assertEqual((status, headers["location"]), (303, "./"), wanted)
        self.assertEqual(webapp.safe_next("/lexique.html?q=1#x"), "lexique.html?q=1#x")

    def test_pages_are_revalidated_and_compressed(self):
        user = self.browser("dara")
        status, headers, body = user.get("/", headers={"Accept-Encoding": "gzip"})
        self.assertEqual((status, headers["content-encoding"]), (200, "gzip"))
        self.assertIn("accueil", body)
        etag = headers["etag"]
        self.assertEqual(user.get("/", headers={"Accept-Encoding": "gzip", "If-None-Match": etag})[0], 304)
        other = self.browser("admin")
        self.assertEqual(other.get("/", headers={"Accept-Encoding": "gzip", "If-None-Match": etag})[0], 200,
                         "la page d'un autre compte n'est pas la même")
        (self.root / "index.html").write_text(PAGE.format(root=".", body="accueil modifié"), encoding="utf-8")
        status, _, body = user.get("/", headers={"Accept-Encoding": "gzip", "If-None-Match": etag})
        self.assertEqual(status, 200)
        self.assertIn("accueil modifié", body)

    def test_forms_refuse_forged_requests(self):
        user = self.browser("dara")
        status, _, _ = user.request("POST", "/compte", form={"action": "profil", "nom": "Pirate", "csrf": "faux"})
        self.assertEqual(status, 303)
        self.assertEqual(self.accounts.get_user(self.dara.id).name, "Dara <Sok>", "sans jeton valable, rien ne change")
        self.assertIn("Le formulaire a expiré", user.get("/compte")[2])
        token = user.token("/compte")
        user.request("POST", "/compte", form={"action": "profil", "nom": "Pirate", "csrf": token},
                     headers={"Origin": "http://evil.example"})
        self.assertEqual(self.accounts.get_user(self.dara.id).name, "Dara <Sok>", "une autre origine est refusée")
        status, _, _ = user.request("POST", "/api/progress", data={"data": {}}, headers={"Origin": "http://evil.example"})
        self.assertEqual(status, 403)
        status, _, _ = user.request("POST", "/api/progress", data={"data": {}}, headers={"Origin": None, "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        status, _, _ = user.request("POST", "/api/profile", data={"profile": "en"})
        self.assertEqual(status, 403, "/api/profile exige le jeton du compte")
        self.assertEqual(self.accounts.get_user(self.dara.id).profile, "km")
        # Formulaire de connexion : le jeton du cookie et celui du champ doivent correspondre.
        visitor = self.browser()
        visitor.get("/connexion")
        status, _, _ = visitor.request("POST", "/connexion", form={"identifiant": "dara", "motdepasse": "motdepasse-dara", "csrf": "faux"})
        self.assertEqual(status, 403)
        self.assertNotIn("frkh_session", visitor.cookies)
        self.assertEqual(user.request("POST", "/index.html", form={})[0], 405)
        self.assertEqual(user.request("POST", "/compte", data={"action": "profil"})[0], 400, "formulaire attendu, pas du JSON")

    def test_repeated_failures_are_slowed_down(self):
        visitor = self.browser()
        for _ in range(5):
            self.assertEqual(visitor.login("dara", "faux-motdepasse")[0], 401)
        status, _, body = visitor.login("dara", "motdepasse-dara")
        self.assertEqual(status, 429, "même le bon mot de passe attend la fin du blocage")
        self.assertIn("Trop de tentatives", body)
        self.assertEqual(self.browser().login("admin", "motdepasse-admin")[0], 303, "les autres comptes ne sont pas bloqués")
        self.now += 16 * 60
        self.assertEqual(visitor.login("dara", "motdepasse-dara")[0], 303)


class AccountPagesTest(ServerCase):
    def test_progress_is_kept_per_account(self):
        dara, admin = self.browser("dara"), self.browser("admin")
        sent = {"frkh-done2-km": json.dumps({"1": {"d": 1, "t": 5}}), "frkh-profile": "km"}
        status, _, body = dara.request("POST", "/api/progress", data={"data": sent})
        self.assertEqual((status, set(json.loads(body)["data"])), (200, {"frkh-done2-km"}))
        self.assertEqual(json.loads(admin.get("/api/progress")[2]), {"data": {}})
        phone = self.browser("dara")
        self.assertEqual(json.loads(json.loads(phone.get("/api/progress")[2])["data"]["frkh-done2-km"]), {"1": {"d": 1, "t": 5.0}})
        for bad, expected in ((b"{", 400), (b"[]", 400), (b'{"data": 3}', 400)):
            conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
            conn.request("POST", "/api/progress", body=bad, headers={
                "Content-Type": "application/json", "Origin": dara.origin, "Cookie": f"frkh_session={dara.cookies['frkh_session']}"})
            self.assertEqual(conn.getresponse().status, expected, bad)
            conn.close()
        self.assertFalse((self.root / "database" / "progress-sync.json").exists(), "plus de progression partagée")

    def test_account_page_updates_profile_password_and_sessions(self):
        user = self.browser("dara")
        status, _, body = user.get("/compte")
        self.assertEqual(status, 200)
        self.assertIn("Dara &lt;Sok&gt;", body)
        self.assertNotIn("Dara <Sok>", body)
        user.post("/compte", {"action": "profil", "nom": "Dara S.", "profil": "en"})
        self.assertIn("Profil enregistré", user.get("/compte")[2])
        self.assertEqual((self.accounts.get_user(self.dara.id).name, self.accounts.get_user(self.dara.id).profile), ("Dara S.", "en"))
        token = re.search(r'"csrf":"([^"]+)"', user.get("/")[2]).group(1)
        status, _, _ = user.request("POST", "/api/profile", data={"profile": "km"}, headers={"X-CSRF-Token": token})
        self.assertEqual((status, self.accounts.get_user(self.dara.id).profile), (200, "km"))
        self.assertEqual(user.request("POST", "/api/profile", data={"profile": "de"}, headers={"X-CSRF-Token": token})[0], 400)

        phone = self.browser("dara")
        for form, message in (({"actuel": "faux", "motdepasse": "nouveau-secret", "motdepasse2": "nouveau-secret"}, "actuel est incorrect"),
                              ({"actuel": "motdepasse-dara", "motdepasse": "nouveau-secret", "motdepasse2": "autre-secret"}, "pas identiques"),
                              ({"actuel": "motdepasse-dara", "motdepasse": "court", "motdepasse2": "court"}, "au moins 8"),
                              ({"actuel": "motdepasse-dara", "motdepasse": "motdepasse-dara", "motdepasse2": "motdepasse-dara"}, "différent")):
            user.post("/compte", {"action": "motdepasse", **form})
            self.assertIn(message, user.get("/compte")[2], str(form))
        user.post("/compte", {"action": "motdepasse", "actuel": "motdepasse-dara", "motdepasse": "nouveau-secret", "motdepasse2": "nouveau-secret"})
        self.assertIn("Mot de passe changé", user.get("/compte")[2])
        self.assertEqual(phone.get("/")[0], 302, "les autres appareils sont déconnectés")
        self.assertEqual(self.browser().login("dara", "motdepasse-dara")[0], 401)
        phone = self.browser("dara", "nouveau-secret")
        user.post("/compte", {"action": "sessions"})
        self.assertEqual((phone.get("/")[0], user.get("/")[0]), (302, 200))

        user.request("POST", "/api/progress", data={"data": {"frkh-done2-km": json.dumps({"1": {"d": 1, "t": 5}})}})
        user.post("/compte", {"action": "progression"})
        self.assertEqual(self.accounts.progress_summary(self.dara.id)["lessons"], 1, "sans la case cochée, rien n'est effacé")
        user.post("/compte", {"action": "progression", "confirmer": "1"})
        self.assertEqual(self.accounts.progress_summary(self.dara.id)["lessons"], 0)

    def test_administrator_manages_accounts(self):
        admin, dara = self.browser("admin"), self.browser("dara")
        status, _, body = dara.get("/utilisateurs")
        self.assertEqual(status, 403)
        self.assertNotIn("motdepasse", body)
        dara.post("/utilisateurs", {"action": "creer", "identifiant": "pirate", "motdepasse": "motdepasse-pirate"}, page="/compte")
        self.assertIsNone(self.accounts.get_by_login("pirate"), "un apprenant ne crée pas de compte")

        status, _, body = admin.get("/utilisateurs")
        self.assertEqual(status, 200)
        self.assertIn("Dara &lt;Sok&gt;", body)
        status, _, body = admin.post("/utilisateurs", {"action": "creer", "identifiant": "dara", "motdepasse": "motdepasse-autre"})
        self.assertEqual(status, 422)
        self.assertIn("déjà utilisé", body)
        status, headers, _ = admin.post("/utilisateurs", {"action": "creer", "identifiant": "Alex", "nom": "Alex", "profil": "en"})
        self.assertEqual((status, headers["location"]), (303, "./utilisateurs"))
        body = admin.get("/utilisateurs")[2]
        temporary = re.search(r"« alex » : ([a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}) —", body).group(1)
        self.assertNotIn(temporary, admin.get("/utilisateurs")[2], "le mot de passe provisoire n'est montré qu'une fois")
        alex = self.accounts.get_by_login("alex")
        self.assertEqual((alex.role, alex.profile, alex.must_change_password), ("user", "en", True))

        newcomer = self.browser()
        status, headers, _ = newcomer.login("alex", temporary)
        self.assertEqual((status, headers["location"]), (303, "./compte"))
        self.assertEqual(newcomer.get("/")[1]["location"], "./compte", "mot de passe provisoire : à changer d'abord")
        self.assertIn("provisoire", newcomer.get("/compte")[2])
        newcomer.post("/compte", {"action": "motdepasse", "actuel": temporary, "motdepasse": "motdepasse-alex", "motdepasse2": "motdepasse-alex"})
        self.assertEqual(newcomer.get("/")[0], 200)

        edit = f"/utilisateurs?u={alex.id}"
        self.assertIn("Modifier le compte", admin.get(edit)[2])
        admin.post("/utilisateurs", {"action": "modifier", "id": alex.id, "nom": "Alexandre", "role": "admin", "profil": "fr", "actif": "1"}, page=edit)
        alex = self.accounts.get_user(alex.id)
        self.assertEqual((alex.name, alex.role, alex.profile, alex.active), ("Alexandre", "admin", "fr", True))
        self.assertEqual(newcomer.get("/utilisateurs")[0], 200, "devenu administrateur")
        admin.post("/utilisateurs", {"action": "modifier", "id": alex.id, "nom": "Alexandre", "role": "user", "profil": "fr"}, page=edit)
        self.assertFalse(self.accounts.get_user(alex.id).active, "case décochée : compte désactivé")
        self.assertEqual(newcomer.get("/")[0], 302)
        self.assertEqual(self.browser().login("alex", "motdepasse-alex")[0], 401)

        admin.post("/utilisateurs", {"action": "motdepasse", "id": self.dara.id, "motdepasse": "redonne-par-admin", "changer": "1"}, page=edit)
        self.assertEqual(dara.get("/")[0], 302, "ses sessions sont fermées")
        self.assertEqual(self.browser().login("dara", "redonne-par-admin")[1]["location"], "./compte")

        own = f"/utilisateurs?u={self.admin.id}"
        self.assertNotIn('value="supprimer"', admin.get(own)[2], "pas de bouton pour supprimer son propre compte")
        for form in ({"action": "supprimer", "id": self.admin.id, "confirmer": "1"},
                     {"action": "modifier", "id": self.admin.id, "nom": "Administratrice", "role": "user", "actif": "1"}):
            admin.post("/utilisateurs", form, page=own)
        me = self.accounts.get_user(self.admin.id)
        self.assertEqual((me.role, me.active), ("admin", True), "le dernier administrateur reste en place")
        admin.post("/utilisateurs", {"action": "supprimer", "id": alex.id}, page=edit)
        self.assertIsNotNone(self.accounts.get_user(alex.id), "sans confirmation, pas de suppression")
        admin.post("/utilisateurs", {"action": "supprimer", "id": alex.id, "confirmer": "1"}, page=edit)
        self.assertIsNone(self.accounts.get_user(alex.id))
        self.assertIn("supprimé", admin.get("/utilisateurs")[2])
        admin.post("/utilisateurs", {"action": "supprimer", "id": 9999, "confirmer": "1"})
        self.assertIn("n&#x27;existe pas", admin.get("/utilisateurs")[2])


class TrackingTest(ServerCase):
    def add_lessons(self, *rows) -> None:
        """Leçons minimales dans la base : (numéro, date, titre)."""
        conn = db.connect(self.config.paths.database)
        try:
            for number, date, title in rows:
                conn.execute(
                    "INSERT INTO lessons(lesson_number, lesson_date, theme, title_fr, title_en, title_km, level, html_path, "
                    "content_json, status, created_at, updated_at) VALUES (?, ?, 'theme', ?, ?, ?, 'debutant', ?, '{}', 'complete', ?, ?)",
                    (number, date, title, f"{title} (en)", "មេរៀន", f"lessons/lesson-{number:03d}.html", db.utcnow(), db.utcnow()))
        finally:
            conn.close()

    def test_tracking_page_shows_a_learners_progress(self):
        today, now = self.accounts.today(), int(self.now * 1000)

        def ago(days: int) -> str:
            return (today - dt.timedelta(days=days)).isoformat()

        self.add_lessons((1, ago(5), "Les salutations"), (2, ago(1), "Les <nombres>"), (3, ago(-20), "Plus tard"))
        dara = self.browser("dara")
        dara.request("POST", "/api/progress", data={"data": {
            "frkh-done2-km": json.dumps({"1": {"d": 1, "t": now - 3600000}}),
            "frkh-days-km": json.dumps([ago(0), ago(1), ago(4)]),
            "frkh-boxes-km-fr": json.dumps({"bonjour": {"b": 3, "t": now}, "merci": {"b": 1, "t": now - 3 * 86400000}})}})
        status, _, body = dara.get("/suivi")
        self.assertEqual(status, 200)
        self.assertIn("Terminées : 1 sur 2", body)
        self.assertRegex(body, r'class="lchip is-done" href="lessons/lesson-001\.html"')
        self.assertRegex(body, r'class="lchip" href="lessons/lesson-002\.html" title="2\. Les &lt;nombres&gt;')
        self.assertNotIn("lesson-003.html", body, "une leçon à venir n'est pas comptée")
        self.assertIn("Connues : 1 sur 2 révisées", body)
        self.assertIn("à revoir : 1", body)
        self.assertIn("Jours actifs : 3 sur", body)
        self.assertEqual(body.count('class="cal-day is-on" title='), 3)
        self.assertNotIn("track-users", body, "un apprenant ne voit que sa propre progression")
        self.assertIn('href="suivi"', dara.get("/compte")[2])
        self.assertEqual(dara.get(f"/suivi?u={self.dara.id}")[0], 200)
        self.assertEqual(dara.get(f"/suivi?u={self.admin.id}")[0], 403)
        self.assertEqual(dara.request("POST", "/suivi", form={})[0], 405)

        admin = self.browser("admin")
        status, _, body = admin.get(f"/suivi?u={self.dara.id}")
        self.assertEqual(status, 200)
        self.assertIn("Dara &lt;Sok&gt;", body)
        self.assertNotIn("Dara <Sok>", body)
        self.assertIn("track-users", body)
        self.assertIn("lesson-001.html", body)
        self.assertEqual(admin.get("/suivi?u=9999")[0], 404)
        own = admin.get("/suivi")[2]
        self.assertIn("Aucune carte révisée", own)
        self.assertIn("Terminées : 0 sur 2", own)
        self.assertIn(f'href="suivi?u={self.dara.id}"', admin.get("/utilisateurs")[2])

        visitor = self.browser()
        self.assertEqual(visitor.get(f"/suivi?u={self.dara.id}")[1]["location"], f"./connexion?suite=/suivi%3Fu%3D{self.dara.id}")
        status, headers, _ = visitor.login("admin", "motdepasse-admin", suite=f"/suivi?u={self.dara.id}")
        self.assertEqual((status, headers["location"]), (303, f"./suivi?u={self.dara.id}"), "retour à la page demandée")

    def test_tracking_page_works_before_any_lesson_exists(self):
        status, _, body = self.browser("dara").get("/suivi")
        self.assertEqual(status, 200)
        self.assertIn("Aucune leçon publiée", body)
        self.assertIn("Aucune activité enregistrée", body)

    def test_devices_are_listed_and_signed_out_one_by_one(self):
        laptop, phone, admin = self.browser(), self.browser(), self.browser("admin")
        for device, agent in ((laptop, FIREFOX_LINUX), (phone, CHROME_ANDROID)):
            status, _, _ = device.post("/connexion", {"identifiant": "dara", "motdepasse": "motdepasse-dara"}, headers={"User-Agent": agent})
            self.assertEqual(status, 303)
        body = laptop.get("/compte")[2]
        self.assertIn("Firefox · Linux", body)
        self.assertIn("Chrome · Android", body)
        self.assertEqual(body.count(">cet appareil<"), 1)
        buttons = re.findall(r'name="session" value="([0-9a-f]{16})"', body)
        own = self.accounts.session(laptop.cookies["frkh_session"]).public_id
        theirs = self.accounts.session(admin.cookies["frkh_session"]).public_id
        self.assertEqual(len(buttons), 1, "un bouton par autre appareil, aucun pour celui-ci")
        self.assertNotEqual(buttons[0], own)
        # Ni sa propre session, ni celle d'un autre compte, ni un identifiant fantaisiste.
        for wanted in (own, theirs, "zz", ""):
            laptop.post("/compte", {"action": "appareil", "session": wanted})
        self.assertEqual((laptop.get("/")[0], phone.get("/")[0], admin.get("/")[0]), (200, 200, 200))
        self.assertIn("Firefox · Linux", admin.get(f"/utilisateurs?u={self.dara.id}")[2], "l'administrateur voit les sessions du compte")
        laptop.post("/compte", {"action": "appareil", "session": buttons[0]})
        body = laptop.get("/compte")[2]
        self.assertIn("Appareil déconnecté", body)
        self.assertNotIn("Chrome · Android", body)
        self.assertNotIn('value="sessions"', body, "plus d'autre appareil : plus de bouton pour les déconnecter")
        self.assertEqual((laptop.get("/")[0], phone.get("/")[0]), (200, 302))


class JournalTest(ServerCase):
    def kinds(self, **filters) -> list:
        return [event.kind for event in self.accounts.list_events(limit=1000, **filters)]

    def test_journal_shows_sign_ins_failures_and_operations(self):
        admin = self.browser("admin")
        typed = "motdepasse-tape-au-mauvais-endroit"
        self.assertEqual(self.browser().login("dara", "mauvais")[0], 401)
        self.assertEqual(self.browser().login(typed, "x")[0], 401)
        admin.post("/utilisateurs", {"action": "creer", "identifiant": "alex", "motdepasse": "motdepasse-alex"})
        alex = self.accounts.get_by_login("alex")
        edit = f"/utilisateurs?u={alex.id}"
        admin.post("/utilisateurs", {"action": "modifier", "id": alex.id, "nom": "alex", "role": "admin", "actif": "1"}, page=edit)
        admin.post("/utilisateurs", {"action": "modifier", "id": alex.id, "nom": "alex", "role": "admin"}, page=edit)
        admin.post("/utilisateurs", {"action": "motdepasse", "id": alex.id, "motdepasse": "redonne-par-admin"}, page=edit)
        admin.post("/utilisateurs", {"action": "supprimer", "id": alex.id, "confirmer": "1"}, page=edit)
        self.assertEqual(self.kinds()[::-1], ["login", "login_failed", "login_failed", "user_created", "role_changed",
                                              "user_disabled", "password_reset", "user_deleted"])
        events = self.accounts.list_events(limit=1000)
        self.assertEqual([event.login for event in events if event.kind == "login_failed"], ["", "dara"])
        self.assertEqual({event.actor for event in events if event.login == "alex"}, {"admin"})
        stored = "\n".join(str(tuple(row)) for row in self.accounts._conn.execute("SELECT * FROM account_events"))
        self.assertNotIn(typed, stored, "un identifiant inconnu n'est pas conservé : ce peut être un mot de passe")

        status, _, body = admin.get("/journal")
        self.assertEqual(status, 200)
        for text in ("Échec de connexion", "identifiant inconnu", "Compte créé", "Rôle changé", "Compte désactivé",
                     "Mot de passe redéfini", "Compte supprimé"):
            self.assertIn(text, body)
        self.assertNotIn(typed, body)
        self.assertIn('<span class="acct-login">alex</span>', body, "le compte supprimé reste nommé")
        self.assertIn(f'href="utilisateurs?u={self.dara.id}#modifier">dara</a>', body)
        failures = admin.get("/journal?type=failures")[2]
        self.assertIn("Échec de connexion", failures)
        self.assertNotIn("Compte créé", failures)
        one = admin.get(f"/journal?u={self.dara.id}")[2]
        self.assertIn("Échec de connexion", one)
        self.assertNotIn("Compte supprimé", one)
        self.assertIn("compte supprimé", admin.get(f"/journal?u={alex.id}")[2])
        self.assertEqual(admin.get("/journal?type=inconnu&u=abc&avant=xyz")[0], 200, "filtres invalides : ignorés")
        self.assertEqual(admin.get("/journal?u=%C2%B2&avant=%C2%B2")[0], 200, "« ² » n'est pas un nombre")
        self.assertEqual(admin.get("/suivi?u=%C2%B2")[0], 404)
        self.assertEqual(admin.request("POST", "/journal", form={})[0], 405)

        dara = self.browser("dara")
        self.assertEqual(dara.get("/journal")[0], 403)
        self.assertIn("Échec de connexion", dara.get("/compte")[2], "chacun voit les tentatives sur son propre compte")
        self.assertEqual(self.browser().get("/journal")[1]["location"], "./connexion?suite=/journal")

    def test_a_blocked_sign_in_is_noted_once(self):
        for _ in range(9):
            self.browser().login("dara", "mauvais")
        self.assertEqual((self.kinds().count("login_failed"), self.kinds().count("login_blocked")), (5, 1))
        self.now += 901
        self.browser("dara")
        self.assertEqual(self.kinds()[0], "login")

    def test_journal_is_paged(self):
        for _ in range(webapp.JOURNAL_PAGE + 20):
            self.accounts.record_event("logout", user=self.dara)
        admin = self.browser("admin")
        body = admin.get("/journal")[2]
        self.assertEqual(body.count("<tr>"), 1 + webapp.JOURNAL_PAGE)
        self.assertNotIn("Revenir aux plus récents", body)
        older = re.search(r'href="(journal\?avant=\d+)"', body).group(1)
        body = admin.get("/" + older)[2]
        self.assertEqual(body.count("<tr>"), 1 + 21, "les vingt restants et la connexion de l'administrateur")
        self.assertIn("Revenir aux plus récents", body)
        self.assertNotIn("Plus anciens", body)


class LinksTest(ServerCase):
    def link(self, body: str) -> str:
        """Le chemin du lien montré à l'administrateur (« invitation?c=… »), une seule fois."""
        return re.search(r'data-rel="((?:invitation|reinitialisation)\?c=[A-Za-z0-9_-]{40,})"', body).group(1)

    def test_administrator_invites_someone_who_creates_their_own_account(self):
        admin, dara = self.browser("admin"), self.browser("dara")
        dara.post("/utilisateurs", {"action": "inviter", "pour": "Pirate"}, page="/compte")
        self.assertEqual(self.accounts.list_links("invite"), [], "un apprenant n'invite personne")
        status, headers, _ = admin.post("/utilisateurs", {"action": "inviter", "pour": "Tante <Sophea>", "role": "user", "profil": "km"})
        self.assertEqual((status, headers["location"]), (303, "./utilisateurs"))
        body = admin.get("/utilisateurs")[2]
        path = self.link(body)
        self.assertIn(f'value="http://127.0.0.1:{self.port}/{path}"', body, "adresse complète, prête à copier")
        self.assertIn("Tante &lt;Sophea&gt;", body)
        self.assertNotIn("Tante <Sophea>", body)
        again = admin.get("/utilisateurs")[2]
        self.assertNotIn(path, again, "le lien n'est montré qu'une fois")
        self.assertIn("Invitations en attente", again)

        guest = self.browser()
        status, _, body = guest.get("/" + path)
        self.assertEqual(status, 200)
        self.assertIn("Vous êtes invité", body)
        self.assertRegex(body, r'name="profil" value="km" checked')
        self.assertIn('"suggest":"km"', body, "la page s'ouvre dans la langue prévue pour la personne invitée")
        self.assertNotIn('"suggest"', admin.get("/utilisateurs")[2])
        self.assertEqual(guest.get("/" + path)[0], 200, "ouvrir le lien ne le consomme pas")
        self.assertEqual(dara.get("/" + path)[0], 409, "déjà connecté : se déconnecter d'abord")
        form = {"c": path.split("=", 1)[1], "identifiant": "sophea", "nom": "Sophea", "profil": "km",
                "motdepasse": "motdepasse-sophea", "motdepasse2": "motdepasse-sophea"}
        for change, message in (({"identifiant": "dara"}, "déjà utilisé"), ({"motdepasse2": "autre-chose"}, "pas identiques"),
                                ({"motdepasse": "court", "motdepasse2": "court"}, "au moins 8")):
            status, _, body = guest.post("/invitation", {**form, **change}, page="/" + path)
            self.assertEqual(status, 422, str(change))
            self.assertIn(message, body)
        self.assertEqual(guest.request("POST", "/invitation", form={**form, "csrf": "faux"})[0], 403)
        status, headers, _ = guest.post("/invitation", form, page="/" + path)
        self.assertEqual((status, headers["location"]), (303, "./"))
        self.assertEqual(guest.get("/")[0], 200, "connecté dès la création du compte")
        sophea = self.accounts.get_by_login("sophea")
        self.assertEqual((sophea.role, sophea.profile, sophea.must_change_password), ("user", "km", False))
        status, _, body = self.browser().get("/" + path)
        self.assertEqual(status, 410)
        self.assertIn("déjà servi", body)
        self.assertEqual(self.accounts.list_links("invite"), [])
        events = self.accounts.list_events(limit=10, kinds=("invite_created", "register"))
        self.assertEqual([(event.kind, event.login, event.actor, event.detail) for event in events],
                         [("register", "sophea", "", "invitation"), ("invite_created", "", "admin", "Tante <Sophea>")])
        journal = admin.get("/journal")[2]
        self.assertIn("Invitation créée", journal)
        self.assertIn("par invitation", journal)
        self.assertNotIn("identifiant inconnu", journal, "une invitation ne concerne encore aucun compte")

    def test_invitations_can_be_cancelled_and_bad_links_are_refused(self):
        admin = self.browser("admin")
        admin.post("/utilisateurs", {"action": "inviter", "pour": "Alex", "role": "admin", "profil": "fr"})
        body = admin.get("/utilisateurs")[2]
        path = self.link(body)
        public = re.search(r'name="lien" value="([0-9a-f]{16})"', body).group(1)
        admin.post("/utilisateurs", {"action": "annuler-lien", "lien": "0" * 16})
        self.assertEqual(len(self.accounts.list_links("invite")), 1)
        admin.post("/utilisateurs", {"action": "annuler-lien", "lien": public})
        self.assertIn("Invitation annulée", admin.get("/utilisateurs")[2])
        guest = self.browser()
        for wrong in ("/" + path, "/invitation", "/invitation?c=", "/invitation?c=" + "x" * 43, "/reinitialisation?c=" + path.split("=", 1)[1]):
            self.assertEqual(guest.get(wrong)[0], 410, wrong)
        admin.post("/utilisateurs", {"action": "inviter", "pour": "x" * 61})
        self.assertIn("1 à 60 caractères", admin.get("/utilisateurs")[2])
        admin.post("/utilisateurs", {"action": "inviter", "profil": "de"})
        self.assertIn("Langue inconnue", admin.get("/utilisateurs")[2])
        self.assertEqual(self.accounts.list_links("invite"), [])

    def test_guessing_links_is_slowed_down(self):
        guest = self.browser()
        codes = [guest.get(f"/invitation?c=essai-{n}")[0] for n in range(32)]
        self.assertEqual((codes[:30], codes[30:]), ([410] * 30, [429, 429]))

    def test_new_password_link_lets_the_person_choose_their_password(self):
        admin, laptop = self.browser("admin"), self.browser("dara")
        edit = f"/utilisateurs?u={self.dara.id}"
        self.assertIn('value="lien-motdepasse"', admin.get(edit)[2])
        status, headers, _ = admin.post("/utilisateurs", {"action": "lien-motdepasse", "id": self.dara.id}, page=edit)
        self.assertEqual((status, headers["location"]), (303, f"./{edit[1:]}"))
        body = admin.get(edit)[2]
        path = self.link(body)
        self.assertTrue(path.startswith("reinitialisation?c="))
        self.assertIn("durée de validité, en heures : 24", body)
        self.assertEqual(laptop.get("/")[0], 200, "tant que le lien n'a pas servi, rien ne change")

        phone = self.browser()
        status, _, body = phone.get("/" + path)
        self.assertEqual(status, 200)
        self.assertIn("pour le compte « dara »", body)
        form = {"c": path.split("=", 1)[1], "motdepasse": "choisi-par-dara", "motdepasse2": "choisi-par-dara"}
        status, _, body = phone.post("/reinitialisation", {**form, "motdepasse2": "autre"}, page="/" + path)
        self.assertEqual(status, 422)
        status, headers, _ = phone.post("/reinitialisation", form, page="/" + path)
        self.assertEqual((status, headers["location"]), (303, "./"))
        self.assertEqual((phone.get("/")[0], laptop.get("/")[0]), (200, 302), "connecté ici, déconnecté ailleurs")
        self.assertEqual(self.browser().login("dara", "motdepasse-dara")[0], 401)
        self.assertEqual(self.browser().login("dara", "choisi-par-dara")[0], 303)
        self.assertEqual(self.browser().get("/" + path)[0], 410)
        kinds = [(event.kind, event.detail, event.actor) for event in self.accounts.list_events(limit=3, user_id=self.dara.id,
                                                                                              kinds=("password_changed", "reset_link_created"))]
        self.assertEqual(kinds, [("password_changed", "link", ""), ("reset_link_created", "", "admin")])
        self.assertIn("par lien", phone.get("/compte")[2])
        # Pas de lien pour un compte désactivé.
        self.accounts.update_user(self.dara.id, active=False)
        self.assertNotIn('value="lien-motdepasse"', admin.get(edit)[2])
        admin.post("/utilisateurs", {"action": "lien-motdepasse", "id": self.dara.id}, page=edit)
        self.assertIn("Ce compte est désactivé", admin.get(edit)[2])


class FirstRunTest(ServerCase):
    with_users = False

    def test_first_account_needs_the_code_shown_by_the_server(self):
        visitor = self.browser()
        self.assertEqual(visitor.get("/")[1]["location"], "./connexion")
        self.assertEqual(visitor.get("/connexion")[1]["location"], "./installation")
        self.assertEqual(visitor.get("/installation")[0], 200)
        code = self.app.setup_code
        self.assertRegex(code, r"^[a-z0-9]{4}-[a-z0-9]{4}$")
        form = {"identifiant": "stefan", "nom": "Stefan", "profil": "fr", "motdepasse": "motdepasse-stefan",
                "motdepasse2": "motdepasse-stefan"}
        status, _, body = visitor.post("/installation", {**form, "code": "aaaa-bbbb"})
        self.assertEqual(status, 422)
        self.assertIn("Code d&#x27;installation incorrect", body)
        status, _, body = visitor.post("/installation", {**form, "code": code, "motdepasse2": "autre"})
        self.assertIn("pas identiques", body)
        self.assertEqual(self.accounts.count_users(), 0)
        status, headers, _ = visitor.post("/installation", {**form, "code": code.upper()})
        self.assertEqual((status, headers["location"]), (303, "./"))
        user = self.accounts.get_by_login("stefan")
        self.assertEqual((user.role, user.name), ("admin", "Stefan"))
        self.assertEqual(visitor.get("/utilisateurs")[0], 200)
        self.assertEqual(self.browser().get("/installation")[0], 404, "le premier démarrage ne sert qu'une fois")


class RegistrationTest(ServerCase):
    server_config = {"registration": "open", "registration_code": "bienvenue", "password_min_length": 10}

    def test_open_registration_with_an_invitation_code(self):
        visitor = self.browser()
        status, _, body = visitor.get("/inscription")
        self.assertEqual(status, 200)
        self.assertIn('name="code"', body)
        self.assertIn("inscription", visitor.get("/connexion")[2])
        form = {"identifiant": "sophea", "nom": "Sophea", "profil": "km", "motdepasse": "motdepasse-sophea",
                "motdepasse2": "motdepasse-sophea"}
        for extra, message in (({"code": "faux"}, "Code d&#x27;invitation incorrect"),
                               ({"code": "bienvenue", "motdepasse": "neuf-car.", "motdepasse2": "neuf-car."}, "au moins 10"),
                               ({"code": "bienvenue", "identifiant": "dara"}, "déjà utilisé")):
            status, _, body = visitor.post("/inscription", {**form, **extra})
            self.assertEqual(status, 422)
            self.assertIn(message, body)
        status, headers, _ = visitor.post("/inscription", {**form, "code": "bienvenue", "role": "admin"})
        self.assertEqual((status, headers["location"]), (303, "./"))
        user = self.accounts.get_by_login("sophea")
        self.assertEqual((user.role, user.profile), ("user", "km"), "une inscription ne crée jamais d'administrateur")
        self.assertEqual(visitor.get("/")[0], 200)


class PublicSiteTest(ServerCase):
    server_config = {"require_login": False}

    def test_site_can_stay_readable_without_an_account(self):
        visitor = self.browser()
        status, _, body = visitor.get("/")
        self.assertEqual(status, 200)
        self.assertIn("accueil", body)
        self.assertIn('"user":null', body)
        self.assertEqual(visitor.get("/audio/fr-FR/bonjour_000000000000.wav")[0], 200)
        self.assertEqual(visitor.get("/api/progress")[0], 401, "la progression en ligne demande un compte")
        self.assertEqual(visitor.get("/.env")[0], 404)
        self.assertEqual(visitor.get("/compte")[1]["location"], "./connexion?suite=/compte")
        self.assertIn('"login":"dara"', self.browser("dara").get("/")[2])


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="frkh-cli-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)

    def run_cli(self, *args: str, stdin: str = "", expect: int = 0) -> str:
        proc = subprocess.run([sys.executable, str(ROOT / "manage.py"), "--root", str(self.root), *args], input=stdin,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=clean_env(), timeout=120)
        self.assertEqual(proc.returncode, expect, f"manage.py {' '.join(args)}\n{proc.stdout}\n{proc.stderr}")
        return proc.stdout + proc.stderr

    def test_accounts_can_be_managed_from_the_command_line(self):
        self.assertIn("Aucun compte", self.run_cli("users", "list"))
        self.assertIn("Compte créé : stefan (admin)", self.run_cli(
            "users", "add", "stefan", "--role", "admin", "--name", "Stefan", "--password-stdin", stdin="motdepasse-stefan\n"))
        out = self.run_cli("users", "add", "dara", "--profile", "km", "--generate")
        temporary = re.search(r"Mot de passe provisoire : (\S+)", out).group(1)
        self.assertIn("déjà utilisé", self.run_cli("users", "add", "dara", "--generate", expect=1))
        self.assertIn("au moins 8", self.run_cli("users", "add", "alex", "--password-stdin", stdin="court\n", expect=1))
        listing = self.run_cli("users", "list")
        self.assertRegex(listing, r"dara\s+user\s+actif\s+km")
        self.assertRegex(listing, r"stefan\s+admin\s+actif")
        config = load_config(self.root)
        store = Accounts(config)
        try:
            self.assertTrue(store.get_by_login("dara").must_change_password)
            self.assertIsNotNone(store.authenticate("dara", temporary))
            self.assertIsNotNone(store.authenticate("stefan", "motdepasse-stefan"))
        finally:
            store.close()
        shown = self.run_cli("users", "show", "dara")
        self.assertRegex(shown, r"Identifiant\s+: dara")
        self.assertIn("mot de passe provisoire", shown)
        self.assertIn("0 leçon(s) terminée(s)", shown)
        self.assertRegex(shown, r"Sessions ouvertes\s+: 0")
        self.assertIn("Compte créé", shown)
        self.run_cli("users", "role", "dara", "admin")
        self.run_cli("users", "disable", "stefan")
        self.assertIn("au moins un administrateur", self.run_cli("users", "disable", "dara", expect=1))
        self.assertIn("--yes", self.run_cli("users", "delete", "stefan", expect=1))
        self.assertIn("Compte supprimé", self.run_cli("users", "delete", "stefan", "--yes"))
        self.assertIn("Compte inconnu", self.run_cli("users", "password", "stefan", "--generate", expect=1))
        self.assertNotIn("stefan", self.run_cli("users", "list"))
        invite = self.run_cli("users", "invite", "--for", "Sophea", "--profile", "km", "--days", "3", "--url", "https://apprendre.exemple.org/")
        self.assertRegex(invite, r"^https://apprendre\.exemple\.org/invitation\?c=[A-Za-z0-9_-]{43}\n")
        self.assertIn("valable 3 jour(s)", invite)
        reset = self.run_cli("users", "reset-link", "dara")
        self.assertRegex(reset, r"^/reinitialisation\?c=[A-Za-z0-9_-]{43}\n")
        self.assertIn("24 heure(s), pour le compte dara", reset)
        store = Accounts(load_config(self.root))
        try:
            self.assertEqual([(item.note, item.profile, item.created_by) for item in store.list_links("invite")],
                             [("Sophea", "km", "@cli")])
            self.assertIsNotNone(store.get_link(reset.split("c=", 1)[1].split()[0], "reset"))
        finally:
            store.close()
        self.assertIn("Compte inconnu", self.run_cli("users", "reset-link", "stefan", expect=1))
        journal = self.run_cli("users", "journal")
        self.assertIn("Invitation créée (Sophea)", journal)
        self.assertIn("Lien de réinitialisation créé", journal)
        for text in ("Compte créé", "Rôle changé (admin)", "Compte désactivé", "Compte supprimé", "par la ligne de commande"):
            self.assertIn(text, journal)
        self.assertEqual(len(self.run_cli("users", "journal", "--limit", "2").strip().splitlines()), 2)
        self.assertRegex(self.run_cli("users", "journal", "dara"), r"Rôle changé \(admin\)\s+dara")
        self.assertIn("Journal vide", self.run_cli("users", "journal", "--type", "failures"))
        self.assertIn("Compte inconnu", self.run_cli("users", "journal", "stefan", expect=1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
