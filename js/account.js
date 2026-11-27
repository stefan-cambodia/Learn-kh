/* FR-KH Learning — menu du compte (serveur avec comptes).
   Ce fichier n'est chargé que par « manage.py serve », qui l'ajoute aux pages en les servant :
   la version autonome du site (fichiers ouverts depuis le disque) ne le connaît pas. */
(function () {
  "use strict";

  var account = window.FRKH_ACCOUNT;
  if (!account) { return; }
  var root = document.documentElement, user = account.user;
  var base = (root.getAttribute("data-root") || ".") + "/";
  var LOCAL = /^frkh-(done2?|days|boxes|review|quiz)-/;
  var SYNC = /^frkh-(done2-(fr|en|km)|days-(fr|en|km)|boxes-(fr|en|km)-(fr|en|km|es|it|ru|zh))$/;

  var ICON_USER = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8.5" r="3.8" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4.5 20c.9-3.6 3.8-5.5 7.5-5.5s6.6 1.9 7.5 5.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  var ICON_USERS = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="9" cy="8.5" r="3.3" fill="none" stroke="currentColor" stroke-width="2"/><path d="M2.8 19.5c.7-3.1 3.1-4.8 6.2-4.8s5.5 1.7 6.2 4.8M15.5 5.6a3.3 3.3 0 0 1 0 5.8M17.8 14.9c1.8.6 3 2.1 3.5 4.6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
  var ICON_CHART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19.5v-7M12 19.5v-15M19 19.5v-10" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>';
  var ICON_LOG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6.5h11M9 12h11M9 17.5h11M4.5 6.5h.01M4.5 12h.01M4.5 17.5h.01" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>';
  var ICON_OUT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 4.5H6.5A1.5 1.5 0 0 0 5 6v12a1.5 1.5 0 0 0 1.5 1.5H14M10.5 12H20m0 0-3.5-3.5M20 12l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  var ICON_IN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 4.5h7.5A1.5 1.5 0 0 1 19 6v12a1.5 1.5 0 0 1-1.5 1.5H10M4 12h9.5m0 0L10 8.5M13.5 12 10 15.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  /* Libellé dans les trois langues de l'interface : la feuille de style n'affiche que celle du profil. */
  function tri(fr, en, km) {
    return '<span class="ui-fr" lang="fr">' + fr + '</span><span class="ui-en" lang="en">' + en +
      '</span><span class="ui-km" lang="km">' + km + '</span>';
  }
  function make(tag, className, html) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (html) { node.innerHTML = html; }
    return node;
  }

  /* ------------------------------------------------------- Progression locale */
  function localKeys(pattern) {
    var keys = [];
    try {
      for (var i = 0; i < window.localStorage.length; i++) {
        var key = window.localStorage.key(i);
        if (pattern.test(key || "")) { keys.push(key); }
      }
    } catch (e) { /* stockage indisponible */ }
    return keys;
  }
  function clearLocalProgress(forgetUser) {
    try {
      localKeys(LOCAL).forEach(function (key) { window.localStorage.removeItem(key); });
      if (forgetUser) { window.localStorage.removeItem("frkh-user"); }
    } catch (e) { /* stockage indisponible */ }
  }
  /* Dernier envoi de la progression avant de quitter le compte : rien ne doit rester seulement ici. */
  function pushProgress(done) {
    var finished = false;
    function finish() { if (!finished) { finished = true; done(); } }
    if (!window.fetch) { return finish(); }
    var data = {};
    localKeys(SYNC).forEach(function (key) { data[key] = window.localStorage.getItem(key); });
    window.setTimeout(finish, 2500);
    window.fetch(base + "api/progress", {
      method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
      credentials: "same-origin", body: JSON.stringify({ data: data })
    }).catch(function () { /* hors ligne : tant pis */ }).then(finish);
  }

  /* ------------------------------------------------------------ Menu du compte */
  function closeOthers(opened) {
    ["settings", "account"].forEach(function (id) {
      var panel = document.getElementById(id);
      if (panel && panel !== opened && panel.open) { panel.open = false; }
    });
  }
  function rootPath() {
    var here = location.pathname, home = here;
    try { home = new URL(base, location.href).pathname; } catch (e) { return ""; }
    return here.indexOf(home) === 0 ? "/" + here.slice(home.length) : "";
  }

  function buildMenu() {
    var tools = document.querySelector(".topbar .tools");
    if (!tools || document.getElementById("account")) { return; }
    if (!user) {
      if (document.body.classList.contains("page-auth")) { return; }
      var link = make("a", "tool tool-account tool-login", ICON_IN + '<span class="account-name">' + tri("Connexion", "Sign in", "ចូល") + "</span>");
      var back = rootPath();
      link.href = base + "connexion" + (back && back !== "/" ? "?suite=" + encodeURIComponent(back + location.search) : "");
      link.id = "account";
      tools.appendChild(link);
      return;
    }
    var menu = make("details", "settings account");
    menu.id = "account";
    var summary = make("summary", "tool tool-account", ICON_USER + '<span class="account-name"></span>');
    summary.querySelector(".account-name").textContent = user.name.split(" ")[0];
    summary.title = user.name;
    summary.setAttribute("aria-label", user.name);
    menu.appendChild(summary);

    var panel = make("div", "settings-panel account-panel");
    var who = make("div", "settings-group account-who");
    var name = make("p", "account-full");
    name.textContent = user.name;
    var login = make("p", "account-login");
    login.textContent = user.login;
    if (user.role === "admin") {
      login.appendChild(make("span", "badge badge-role-admin", tri("Administrateur", "Administrator", "អ្នកគ្រប់គ្រង")));
    }
    who.appendChild(name);
    who.appendChild(login);
    panel.appendChild(who);

    var links = make("div", "settings-group account-links");
    function addLink(path, icon, label) {
      var link = make("a", "account-link", icon + label);
      link.href = base + path;
      links.appendChild(link);
    }
    addLink("compte", ICON_USER, tri("Mon compte", "My account", "គណនីរបស់ខ្ញុំ"));
    addLink("suivi", ICON_CHART, tri("Ma progression", "My progress", "វឌ្ឍនភាពរបស់ខ្ញុំ"));
    if (user.role === "admin") {
      addLink("utilisateurs", ICON_USERS, tri("Utilisateurs", "Users", "អ្នកប្រើប្រាស់"));
      addLink("journal", ICON_LOG, tri("Journal", "Activity log", "កំណត់ហេតុ"));
    }
    panel.appendChild(links);

    var out = make("form", "settings-group account-out js-logout");
    out.method = "post";
    out.action = base + "deconnexion";
    var token = make("input");
    token.type = "hidden";
    token.name = "csrf";
    token.value = account.csrf;
    out.appendChild(token);
    var leave = make("button", "account-link account-logout", ICON_OUT + tri("Se déconnecter", "Sign out", "ចាកចេញ"));
    leave.type = "submit";
    out.appendChild(leave);
    panel.appendChild(out);
    menu.appendChild(panel);
    tools.appendChild(menu);

    menu.addEventListener("toggle", function () { if (menu.open) { closeOthers(menu); } });
    var settings = document.getElementById("settings");
    if (settings) { settings.addEventListener("toggle", function () { if (settings.open) { closeOthers(settings); } }); }
    document.addEventListener("click", function (event) {
      if (menu.open && !menu.contains(event.target)) { menu.open = false; }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && menu.open) { menu.open = false; summary.focus(); }
    });
  }

  /* -------------------------------------------------------------- Déconnexion */
  function wireLogout() {
    Array.prototype.forEach.call(document.querySelectorAll("form.js-logout"), function (form) {
      var sent = false;
      form.addEventListener("submit", function (event) {
        if (sent) { return; }
        event.preventDefault();
        sent = true;
        pushProgress(function () {
          clearLocalProgress(true);
          form.submit();
        });
      });
    });
  }

  /* ---------------------------------------------- Langue de l'apprenant → compte */
  function watchProfile() {
    if (!user || !window.fetch) { return; }
    document.addEventListener("click", function (event) {
      var button = event.target && event.target.closest ? event.target.closest("[data-profile-choice]") : null;
      var value = button ? button.getAttribute("data-profile-choice") : "";
      if (!value || value === user.profile) { return; }
      user.profile = value;
      window.fetch(base + "api/profile", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": account.csrf },
        body: JSON.stringify({ profile: value })
      }).catch(function () { /* sera renvoyé au prochain changement */ });
    });
  }

  /* ------------------------------------------------- Session fermée ailleurs */
  function watchSession() {
    if (!user || !window.fetch) { return; }
    var last = Date.now();
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "visible" || Date.now() - last < 60000) { return; }
      last = Date.now();
      window.fetch(base + "api/me", { credentials: "same-origin", cache: "no-store" }).then(function (response) {
        if (response.status === 401) { location.reload(); }
      }).catch(function () { /* hors ligne */ });
    });
  }

  function init() {
    buildMenu();
    wireLogout();
    watchProfile();
    watchSession();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
