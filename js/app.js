/* FR-KH Learning — comportement du site (JavaScript natif, sans dépendance, utilisable hors ligne). */
(function () {
  "use strict";

  var root = document.documentElement;
  var ICON_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.2v13.6L19.5 12z"/></svg>';
  var ICON_PAUSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h3.6v14H7zM13.4 5H17v14h-3.6z"/></svg>';
  var SLOW_RATE = 0.75;

  var store = {
    get: function (key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } },
    set: function (key, value) {
      try { window.localStorage.setItem(key, value); } catch (e) { /* stockage indisponible */ }
      if (SYNC_KEY.test(key)) { scheduleSync(); }
    }
  };

  /* ------------------------------------------------- Synchronisation des appareils */
  /* Avec le serveur local (« manage.py serve »), la progression est partagée entre l'ordinateur
     et le téléphone : le serveur fusionne les états entrée par entrée (la plus récente gagne).
     Fichiers ouverts depuis le disque : chaque appareil garde sa propre progression. */
  var SYNC_KEY = /^frkh-(done2-[AB]|days-[AB]|boxes-[AB]-(fr|en|km))$/;
  var syncTimer = 0, syncBusy = false, syncAgain = false;

  function syncURL() { return (root.getAttribute("data-root") || ".") + "/api/progress"; }
  function syncable() {
    var data = {};
    try {
      for (var i = 0; i < window.localStorage.length; i++) {
        var key = window.localStorage.key(i);
        if (SYNC_KEY.test(key)) { data[key] = window.localStorage.getItem(key); }
      }
    } catch (e) { /* stockage indisponible */ }
    return data;
  }
  function scheduleSync() {
    if (!/^https?:$/.test(location.protocol) || !window.fetch) { return; }
    window.clearTimeout(syncTimer);
    syncTimer = window.setTimeout(syncNow, 700);
  }
  function syncNow() {
    if (!/^https?:$/.test(location.protocol) || !window.fetch) { return; }
    if (syncBusy) { syncAgain = true; return; }
    syncBusy = true;
    window.fetch(syncURL(), {
      method: "POST", headers: { "Content-Type": "application/json" }, cache: "no-store",
      body: JSON.stringify({ data: syncable() })
    }).then(function (response) {
      if (!response.ok) { throw new Error("HTTP " + response.status); }
      return response.json();
    }).then(function (payload) {
      var data = payload && payload.data, changed = false;
      if (data && typeof data === "object") {
        Object.keys(data).forEach(function (key) {
          if (!SYNC_KEY.test(key) || typeof data[key] !== "string") { return; }
          var before = null;
          try { before = window.localStorage.getItem(key); window.localStorage.setItem(key, data[key]); } catch (e) { return; }
          if (before !== data[key]) { changed = true; }
        });
      }
      root.classList.add("is-synced");
      if (changed) {
        refreshDone();
        document.dispatchEvent(new CustomEvent("frkh:synced"));
      }
    }).catch(function () {
      root.classList.remove("is-synced");   /* pas de serveur local : rien à faire */
    }).then(function () {
      syncBusy = false;
      if (syncAgain) { syncAgain = false; syncNow(); }
    });
  }
  window.frkhSync = { schedule: scheduleSync, now: syncNow };

  function all(selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  }

  /* ---------------------------------------------------------------- Profil */
  function profile() {
    return root.getAttribute("data-profile") === "A" ? "A" : "B";
  }

  function applyProfile(value, persist) {
    root.setAttribute("data-profile", value);
    root.setAttribute("lang", value === "A" ? "km" : "fr");
    if (persist) { store.set("frkh-profile", value); }
    all("[data-profile-choice]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-profile-choice") === value));
    });
    /* Le profil suit l'utilisateur d'une page à l'autre, même si le navigateur
       isole le stockage local des fichiers ouverts directement depuis le disque. */
    all("a[data-nav]").forEach(function (link) {
      var parts = link.getAttribute("href").split("#");
      var params = (parts[1] || "").split("&").filter(function (p) { return p && p.indexOf("profil=") !== 0; });
      params.push("profil=" + value);
      link.setAttribute("href", parts[0] + "#" + params.join("&"));
    });
    all("input[data-placeholder-fr]").forEach(function (input) {
      input.placeholder = input.getAttribute(value === "A" ? "data-placeholder-km" : "data-placeholder-fr");
    });
    refreshDone();
    if (root.dispatchEvent && typeof CustomEvent === "function") { root.dispatchEvent(new CustomEvent("frkh:profile")); }
    if (typeof updateCount === "function") { updateCount(); }
    if (typeof lexiconCount === "function") { lexiconCount(); }
  }

  /* ------------------------------------------------------- Date du jour */
  /* Les leçons peuvent être générées à l'avance : seules celles dont la date est passée
     sont « disponibles ». La date se calcule dans le fuseau du programme (Cambodge). */
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function todayISO() {
    var forced = /(?:^|[#&])jour=(\d{4}-\d{2}-\d{2})/.exec(location.hash);
    if (forced) { return forced[1]; }
    var tz = root.getAttribute("data-tz");
    try {
      if (tz) {
        return new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
      }
    } catch (e) { /* fuseau inconnu du navigateur */ }
    var d = new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }
  var TODAY = todayISO();
  var showFuture = false;

  function kmDigits(n) { return String(n).replace(/\d/g, function (d) { return "០១២៣៤៥៦៧៨៩".charAt(Number(d)); }); }

  /* ----------------------------------------------------------------- Audio */
  var playing = null;      // { audio, button }
  var sequence = null;     // lecture enchaînée du dialogue

  function slow() { return store.get("frkh-slow") === "1"; }

  function setState(button, isPlaying) {
    button.classList.toggle("is-playing", isPlaying);
    button.innerHTML = isPlaying ? ICON_PAUSE : ICON_PLAY;
  }

  function stopPlaying() {
    if (!playing) { return; }
    playing.audio.pause();
    setState(playing.button, false);
    playing = null;
  }

  function start(audio, button) {
    stopPlaying();
    try { audio.currentTime = 0; } catch (e) { /* pas encore chargé */ }
    audio.playbackRate = slow() ? SLOW_RATE : 1;
    playing = { audio: audio, button: button };
    setState(button, true);
    var attempt = audio.play();
    if (attempt && typeof attempt.catch === "function") {
      attempt.catch(function () { if (playing && playing.audio === audio) { setState(button, false); playing = null; } });
    }
  }

  function enhanceAudio(wrapper) {
    var audio = wrapper.querySelector("audio");
    if (!audio) { return; }
    var button = document.createElement("button");
    button.type = "button";
    button.className = "play";
    button.setAttribute("aria-label", audio.getAttribute("aria-label") || "Écouter");
    button.innerHTML = ICON_PLAY;
    wrapper.insertBefore(button, audio);
    wrapper.classList.add("is-enhanced");
    audio.removeAttribute("controls");

    button.addEventListener("click", function () {
      if (sequence) { stopSequence(); }
      if (playing && playing.audio === audio) { stopPlaying(); } else { start(audio, button); }
    });
    audio.addEventListener("ended", function () {
      if (playing && playing.audio === audio) { setState(button, false); playing = null; }
      audio.dispatchEvent(new CustomEvent("frkh:done"));
    });
    function failed() {
      wrapper.classList.add("has-error");
      button.title = profile() === "A" ? "មិនអាចបើកសំឡេងបានទេ" : "Fichier audio illisible";
      if (playing && playing.audio === audio) { setState(button, false); playing = null; }
      audio.dispatchEvent(new CustomEvent("frkh:done"));
    }
    audio.addEventListener("error", failed);
    all("source", audio).forEach(function (source) { source.addEventListener("error", failed); });
    wrapper._frkh = { audio: audio, button: button };
  }

  /* Boutons audio légers, sans élément <audio> dans la page (listes longues : Lexique). */
  var lightAudio = null;
  function initLightAudio() {
    document.addEventListener("click", function (event) {
      var button = event.target.closest ? event.target.closest("button[data-src]") : null;
      if (!button) { return; }
      if (lightAudio && lightAudio.button === button && !lightAudio.audio.paused) {
        lightAudio.audio.pause(); setState(button, false); lightAudio = null; return;
      }
      stopPlaying();
      if (lightAudio) { lightAudio.audio.pause(); setState(lightAudio.button, false); }
      var audio = new Audio(button.getAttribute("data-src"));
      audio.playbackRate = slow() ? SLOW_RATE : 1;
      lightAudio = { audio: audio, button: button };
      setState(button, true);
      audio.addEventListener("ended", function () { setState(button, false); });
      audio.addEventListener("error", function () { setState(button, false); button.classList.add("has-error"); });
      var attempt = audio.play();
      if (attempt && attempt.catch) { attempt.catch(function () { setState(button, false); }); }
    });
  }

  /* Lecture de tout le dialogue dans une langue, réplique après réplique. */
  function stopSequence() {
    if (!sequence) { return; }
    window.clearTimeout(sequence.timer);
    sequence.trigger.classList.remove("is-playing");
    all(".line.is-speaking").forEach(function (line) { line.classList.remove("is-speaking"); });
    sequence = null;
    stopPlaying();
  }

  function playSequence(trigger, lang) {
    stopRoleplay();
    if (sequence && sequence.trigger === trigger) { stopSequence(); return; }
    stopSequence();
    var items = all(".dialogue .line").map(function (line) {
      var wrapper = line.querySelector(".lang-" + lang + " .audio.is-enhanced");
      return wrapper && wrapper._frkh ? { line: line, audio: wrapper._frkh.audio, button: wrapper._frkh.button } : null;
    }).filter(Boolean);
    if (!items.length) { return; }
    sequence = { trigger: trigger, timer: 0 };
    trigger.classList.add("is-playing");
    var index = 0;
    function next() {
      if (!sequence || sequence.trigger !== trigger) { return; }
      all(".line.is-speaking").forEach(function (line) { line.classList.remove("is-speaking"); });
      if (index >= items.length) { stopSequence(); return; }
      var item = items[index++];
      item.line.classList.add("is-speaking");
      if (item.line.scrollIntoView) { item.line.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
      item.audio.addEventListener("frkh:done", function () {
        if (sequence && sequence.trigger === trigger) { sequence.timer = window.setTimeout(next, 450); }
      }, { once: true });
      start(item.audio, item.button);
    }
    next();
  }

  /* Jeu de rôle : le site lit les répliques de l'autre personnage et s'arrête à chacune des vôtres,
     dont le texte (dans la langue étudiée) est masqué. On la dit à voix haute, puis « Continuer » fait
     entendre la bonne version. */
  var roleplay = null;

  function rpLang() {
    var active = document.querySelector("[data-rp-lang].is-active");
    if (active && getComputedStyle(active).display !== "none") { return active.getAttribute("data-rp-lang"); }
    return profile() === "A" ? "fr" : "km";
  }
  function rpText(key) {
    var A = profile() === "A";
    var names = { fr: A ? "ភាសាបារាំង" : "en français", en: A ? "ភាសាអង់គ្លេស" : "en anglais", km: A ? "ភាសាខ្មែរ" : "en khmer" };
    if (key === "turn") { return A ? "ដល់វេនអ្នកហើយ៖ និយាយឃ្លានេះ" + names[roleplay.lang] + " រួចចុច « បន្ត »។" : "À vous ! Dites la réplique " + names[roleplay.lang] + ", puis appuyez sur « Continuer »."; }
    if (key === "listen") { return A ? "ស្តាប់…" : "Écoutez…"; }
    return A ? "ល្អណាស់! ការសន្ទនាចប់ហើយ។" : "Bravo, dialogue terminé !";
  }
  function stopRoleplay() {
    if (!roleplay) { return; }
    window.clearTimeout(roleplay.timer);
    all(".line").forEach(function (line) { line.classList.remove("is-speaking", "is-yourturn"); line.removeAttribute("data-mask"); });
    all("[data-role]").forEach(function (b) { b.classList.remove("is-playing"); });
    document.getElementById("roleplay-bar").hidden = true;
    roleplay = null;
    stopPlaying();
  }
  function rpAudio(line, lang) {
    var wrapper = line.querySelector(".lang-" + lang + " .audio.is-enhanced");
    return wrapper && wrapper._frkh ? wrapper._frkh : null;
  }
  function rpStep() {
    if (!roleplay) { return; }
    var bar = document.getElementById("roleplay-bar"), msg = document.getElementById("rp-msg");
    var cont = document.getElementById("rp-continue");
    all(".line.is-speaking").forEach(function (line) { line.classList.remove("is-speaking", "is-yourturn"); });
    if (roleplay.index >= roleplay.lines.length) {
      msg.textContent = rpText("end");
      cont.hidden = true;
      all("[data-role]").forEach(function (b) { b.classList.remove("is-playing"); });
      return;
    }
    var line = roleplay.lines[roleplay.index], player = rpAudio(line, roleplay.lang);
    line.classList.add("is-speaking");
    if (line.scrollIntoView) { line.scrollIntoView({ block: "center", behavior: "smooth" }); }
    function advance(delay) {
      roleplay.index++;
      roleplay.timer = window.setTimeout(rpStep, delay);
    }
    if (line.classList.contains("speaker-" + roleplay.role) && !roleplay.answered) {
      line.classList.add("is-yourturn");
      line.setAttribute("data-mask", roleplay.lang);
      msg.textContent = rpText("turn");
      cont.hidden = false;
      roleplay.waiting = true;
      return;
    }
    roleplay.answered = false;
    roleplay.waiting = false;
    cont.hidden = true;
    msg.textContent = rpText("listen");
    if (!player) { advance(1800); return; }
    player.audio.addEventListener("frkh:done", function () {
      if (roleplay && roleplay.lines[roleplay.index] === line) { advance(500); }
    }, { once: true });
    start(player.audio, player.button);
    bar.hidden = false;
  }
  function rpContinue() {
    if (!roleplay || !roleplay.waiting) { return; }
    var line = roleplay.lines[roleplay.index];
    line.removeAttribute("data-mask");
    roleplay.answered = true;
    rpStep();
  }
  function initRoleplay() {
    var box = document.querySelector("[data-roleplay]");
    if (!box) { return; }
    var langs = all("[data-rp-lang]", box);
    function markLang(lang) { langs.forEach(function (b) { b.classList.toggle("is-active", b.getAttribute("data-rp-lang") === lang); }); }
    markLang(profile() === "A" ? "fr" : "km");
    langs.forEach(function (b) {
      b.addEventListener("click", function () { markLang(b.getAttribute("data-rp-lang")); stopRoleplay(); });
    });
    all("[data-role]", box).forEach(function (button) {
      button.addEventListener("click", function () {
        var same = roleplay && roleplay.button === button;
        stopRoleplay();
        stopSequence();
        if (same) { return; }
        roleplay = { role: button.getAttribute("data-role"), lang: rpLang(), index: 0, timer: 0, button: button,
                     lines: all(".dialogue .line"), waiting: false, answered: false };
        button.classList.add("is-playing");
        document.getElementById("roleplay-bar").hidden = false;
        rpStep();
      });
    });
    document.getElementById("rp-continue").addEventListener("click", rpContinue);
    document.getElementById("rp-stop").addEventListener("click", stopRoleplay);
    document.addEventListener("keydown", function (event) {
      if (roleplay && roleplay.waiting && (event.key === " " || event.key === "Enter") &&
          !/^(input|textarea|button)$/i.test(event.target.tagName || "")) {
        event.preventDefault();
        rpContinue();
      }
    });
    root.addEventListener("frkh:profile", function () { markLang(profile() === "A" ? "fr" : "km"); });
  }

  /* Mode test : le texte des langues étudiées est flouté ; toucher une ligne la révèle. */
  function initQuiz() {
    var toggle = document.getElementById("quiz-toggle");
    if (!toggle) { return; }
    var hint = document.getElementById("quiz-hint");
    function key() { return "frkh-quiz-" + profile(); }
    function apply(on) {
      root.classList.toggle("quiz-mode", on);
      toggle.setAttribute("aria-pressed", String(on));
      if (hint) { hint.hidden = !on; }
      if (!on) { all(".lang-row.is-shown").forEach(function (row) { row.classList.remove("is-shown"); }); }
    }
    apply(store.get(key()) === "1");
    toggle.addEventListener("click", function () {
      var on = !root.classList.contains("quiz-mode");
      store.set(key(), on ? "1" : "0");
      apply(on);
    });
    document.addEventListener("click", function (event) {
      if (!root.classList.contains("quiz-mode")) { return; }
      if (event.target.closest && event.target.closest(".play, .audio-download, a, button")) { return; }
      var row = event.target.closest ? event.target.closest(".entry .lang-row") : null;
      if (row) { row.classList.toggle("is-shown"); }
    });
    root.addEventListener("frkh:profile", function () { apply(store.get(key()) === "1"); });
  }

  function initSlowToggle() {
    var toggle = document.getElementById("slow-toggle");
    if (!toggle) { return; }
    toggle.setAttribute("aria-pressed", String(slow()));
    toggle.addEventListener("click", function () {
      var value = !slow();
      store.set("frkh-slow", value ? "1" : "0");
      toggle.setAttribute("aria-pressed", String(value));
      if (playing) { playing.audio.playbackRate = value ? SLOW_RATE : 1; }
    });
  }

  /* --------------------------------------------------- Leçons terminées */
  function doneMap() {
    var key = "frkh-done2-" + profile(), map = null;
    try { map = JSON.parse(store.get(key) || "null"); } catch (e) { map = null; }
    if (!map || typeof map !== "object") {
      map = {};
      var old = [];
      try { old = JSON.parse(store.get("frkh-done-" + profile()) || "[]") || []; } catch (e) { old = []; }
      if (old.length) {
        old.forEach(function (n) { map[n] = { d: 1, t: 1 }; });
        store.set(key, JSON.stringify(map));
      }
    }
    return map;
  }

  function doneList() {
    var map = doneMap();
    return Object.keys(map).filter(function (n) { return map[n] && map[n].d === 1; }).map(Number);
  }

  function setDone(number, value) {
    var map = doneMap();
    map[number] = { d: value ? 1 : 0, t: Date.now() };
    store.set("frkh-done2-" + profile(), JSON.stringify(map));
    if (value) { addActiveDay(); }
  }

  /* Jours d'activité (leçon terminée ou série de révision) : pour la série de jours d'affilée. */
  function activeDays() {
    try { return JSON.parse(store.get("frkh-days-" + profile()) || "[]") || []; } catch (e) { return []; }
  }
  function addActiveDay() {
    var days = activeDays();
    if (days.indexOf(TODAY) === -1) {
      days.push(TODAY);
      days.sort();
      store.set("frkh-days-" + profile(), JSON.stringify(days.slice(-400)));
    }
  }
  window.frkhActiveDay = addActiveDay;

  function shiftDay(iso, delta) {
    var d = new Date(iso + "T12:00:00Z");
    d.setUTCDate(d.getUTCDate() + delta);
    return d.toISOString().slice(0, 10);
  }
  function streak() {
    var days = activeDays(), count = 0;
    var day = days.indexOf(TODAY) !== -1 ? TODAY : shiftDay(TODAY, -1);
    while (days.indexOf(day) !== -1) { count++; day = shiftDay(day, -1); }
    return count;
  }

  function refreshDone() {
    var done = doneList();
    all(".lesson-card").forEach(function (card) {
      card.classList.toggle("is-done", done.indexOf(Number(card.getAttribute("data-number"))) !== -1);
    });
    refreshToday();
    var button = document.getElementById("finish-lesson");
    var lesson = document.querySelector("[data-lesson]");
    if (button && lesson) {
      button.setAttribute("aria-pressed", String(done.indexOf(Number(lesson.getAttribute("data-lesson"))) !== -1));
    }
  }

  function initFinish() {
    var button = document.getElementById("finish-lesson");
    var lesson = document.querySelector("[data-lesson]");
    if (!button || !lesson) { return; }
    button.addEventListener("click", function () {
      var number = Number(lesson.getAttribute("data-lesson"));
      setDone(number, doneList().indexOf(number) === -1);
      refreshDone();
    });
  }

  /* ---------------------------------------------------- Leçon du jour (index) */
  function lessonCards() { return all(".lesson-card"); }
  function cardDate(card) { return card.getAttribute("data-date") || ""; }

  function markCards() {
    var future = 0;
    lessonCards().forEach(function (card) {
      var date = cardDate(card);
      var isFuture = date > TODAY, isToday = date === TODAY;
      card.classList.toggle("is-future", isFuture);
      card.classList.toggle("is-today", isToday);
      var meta = card.querySelector(".lesson-meta");
      var old = card.querySelector(".badge-today, .badge-future");
      if (old) { old.parentNode.removeChild(old); }
      var tpl = document.getElementById(isToday ? "badge-today" : isFuture ? "badge-future" : "");
      if (meta && tpl && tpl.content) { meta.insertBefore(tpl.content.cloneNode(true), meta.firstChild); }
      if (isFuture) { future++; }
    });
    return future;
  }

  function refreshToday() {
    var panel = document.getElementById("today-panel");
    if (!panel) { return; }
    var cards = lessonCards().filter(function (card) { return cardDate(card) <= TODAY; });
    if (!cards.length) { panel.hidden = true; return; }
    /* Les cartes sont triées de la plus récente à la plus ancienne. */
    var main = cards.filter(function (card) { return cardDate(card) === TODAY; })[0] || cards[0];
    var isToday = cardDate(main) === TODAY;
    panel.querySelector(".today-label-today").hidden = !isToday;
    panel.querySelector(".today-label-latest").hidden = isToday;
    var link = main.querySelector(".lesson-link");
    var target = document.getElementById("today-link");
    target.setAttribute("href", link.getAttribute("href"));
    var number = Number(main.getAttribute("data-number"));
    document.getElementById("today-num").textContent = profile() === "A" ? kmDigits(number) : String(number);
    document.getElementById("today-title").innerHTML = main.querySelector(".lesson-title").innerHTML;
    var done = doneList();
    target.classList.toggle("is-done", done.indexOf(number) !== -1);

    var finished = cards.filter(function (card) { return done.indexOf(Number(card.getAttribute("data-number"))) !== -1; }).length;
    var text = document.getElementById("progress-text");
    text.textContent = profile() === "A"
      ? "រៀនចប់ " + kmDigits(finished) + " / " + kmDigits(cards.length) + " មេរៀន"
      : finished + " leçon" + (finished > 1 ? "s" : "") + " terminée" + (finished > 1 ? "s" : "") + " sur " + cards.length;
    document.getElementById("progress-fill").style.width = Math.round(100 * finished / cards.length) + "%";

    var streakBox = document.getElementById("streak");
    if (streakBox) {
      var days = streak();
      streakBox.hidden = days < 1;
      streakBox.querySelector(".streak-count").textContent = profile() === "A"
        ? kmDigits(days) + " ថ្ងៃជាប់គ្នា"
        : days + (days > 1 ? " jours d'affilée" : " jour d'affilée");
    }

    var activity = document.getElementById("activity");
    if (activity) {
      var active = activeDays(), cells = [];
      for (var back = 27; back >= 0; back--) {
        var day = shiftDay(TODAY, -back);
        cells.push('<span class="day' + (active.indexOf(day) !== -1 ? " is-active" : "") + (back === 0 ? " is-today" : "") +
                   '" title="' + day + '"></span>');
      }
      activity.innerHTML = cells.join("");
    }

    refreshDue();

    /* « Reprendre » : la plus ancienne leçon disponible pas encore terminée, si ce n'est pas celle du jour. */
    var resume = document.getElementById("resume-link");
    var todo = cards.slice().reverse().filter(function (card) {
      return done.indexOf(Number(card.getAttribute("data-number"))) === -1 && card !== main;
    })[0];
    if (todo) {
      var n = Number(todo.getAttribute("data-number"));
      resume.setAttribute("href", todo.querySelector(".lesson-link").getAttribute("href"));
      resume.textContent = profile() === "A" ? "បន្តមេរៀនទី " + kmDigits(n) + " ›" : "Reprendre la leçon " + n + " ›";
      resume.hidden = false;
    } else {
      resume.hidden = true;
    }
    panel.hidden = false;
  }

  /* Mots à réviser aujourd'hui (même règle que la page « Réviser » : boîte b → retour après 1, 2, 4, 8, 16 jours),
     pour la langue principale étudiée : khmer pour le profil B, français pour le profil A. */
  var INTERVALS = [0, 1, 2, 4, 8, 16];
  function refreshDue() {
    var link = document.getElementById("due-link"), data = document.getElementById("cards-data");
    if (!link || !data) { return; }
    var cards = [];
    try { cards = JSON.parse(data.textContent) || []; } catch (e) { cards = []; }
    var lang = profile() === "A" ? "fr" : "km", known = {};
    try { known = JSON.parse(store.get("frkh-boxes-" + profile() + "-" + lang) || "{}") || {}; } catch (e) { known = {}; }
    var now = Date.now(), count = 0;
    cards.forEach(function (card) {
      if (card[1] > TODAY) { return; }
      var entry = known[card[0]];
      if (!entry) { count++; return; }
      var when = typeof entry.t === "number" ? entry.t : (Date.parse(entry.t) || 0);
      if (now >= when + (INTERVALS[entry.b] || 1) * 86400000 - 6 * 3600000) { count++; }
    });
    link.hidden = count === 0;
    document.getElementById("due-count").textContent = profile() === "A" ? kmDigits(count) : String(count);
  }

  /* Taille du texte : normale, grande, très grande (mémorisée sur l'appareil). */
  function initSize() {
    var button = document.getElementById("size-toggle");
    if (!button) { return; }
    var sizes = ["", "l", "xl"];
    button.addEventListener("click", function () {
      var current = root.getAttribute("data-size") || "";
      var next = sizes[(sizes.indexOf(current) + 1) % sizes.length];
      if (next) { root.setAttribute("data-size", next); } else { root.removeAttribute("data-size"); }
      try { window.localStorage.setItem("frkh-size", next); } catch (e) { /* stockage indisponible */ }
      button.setAttribute("data-level", next || "m");
    });
    button.setAttribute("data-level", root.getAttribute("data-size") || "m");
  }

  function initFuture() {
    var future = markCards();
    var toggle = document.getElementById("future-toggle");
    if (!toggle) { return; }
    function label() {
      if (profile() === "A") {
        toggle.textContent = showFuture ? "លាក់មេរៀនខាងមុខ" : "បង្ហាញមេរៀនខាងមុខ (" + kmDigits(future) + ")";
      } else {
        toggle.textContent = showFuture ? "Masquer les leçons à venir"
          : "Afficher les " + future + " leçon" + (future > 1 ? "s" : "") + " à venir";
      }
      toggle.setAttribute("aria-pressed", String(showFuture));
    }
    toggle.hidden = !future;
    label();
    toggle.addEventListener("click", function () {
      showFuture = !showFuture;
      label();
      if (typeof updateCount === "function") { updateCount(); }
    });
    toggle._label = label;
  }

  function initFutureNotice() {
    var lesson = document.querySelector("[data-lesson][data-date]");
    var notice = document.getElementById("future-notice");
    if (lesson && notice) { notice.hidden = !(lesson.getAttribute("data-date") > TODAY); }
  }

  /* ------------------------------------------------------------ Recherche */
  var updateCount = null;

  function fold(text) {
    var value = String(text).toLowerCase();
    if (value.normalize) { value = value.normalize("NFD").replace(/[̀-ͯ]/g, "").normalize("NFC"); }
    return value.replace(/œ/g, "oe").replace(/æ/g, "ae").replace(/[​﻿]/g, "").replace(/\s+/g, " ").trim();
  }

  function initSearch() {
    var input = document.getElementById("search");
    var list = document.getElementById("lesson-list");
    if (!input || !list) { return; }
    var cards = all(".lesson-card", list);
    var empty = document.getElementById("no-result");
    var count = document.getElementById("result-count");
    var level = "";

    function digitsKm(number) {
      return String(number).replace(/\d/g, function (d) { return "០១២៣៤៥៦៧៨៩".charAt(Number(d)); });
    }

    function digitsLatin(text) {
      return text.replace(/[០-៩]/g, function (d) { return String("០១២៣៤៥៦៧៨៩".indexOf(d)); });
    }

    function filter() {
      var terms = fold(input.value).split(" ").filter(Boolean);
      var shown = 0;
      cards.forEach(function (card) {
        var haystack = card.getAttribute("data-search") || "";
        var number = Number(card.getAttribute("data-number"));
        /* Un numéro de leçon tapé explicitement affiche aussi une leçon à venir. */
        var byNumber = terms.some(function (term) { return /^\d{1,3}$/.test(digitsLatin(term)); });
        var ok = (showFuture || byNumber || !card.classList.contains("is-future")) &&
          (!level || card.getAttribute("data-level") === level) &&
          terms.every(function (term) {
            /* Un nombre seul (« 12 » ou « ១២ ») désigne le numéro de la leçon ;
               les dates se cherchent sous la forme 2026-11-15, 15/11/2026 ou « 15 novembre ». */
            var digits = digitsLatin(term);
            if (/^\d{1,3}$/.test(digits)) { return Number(digits) === number; }
            return haystack.indexOf(term) !== -1;
          });
        card.hidden = !ok;
        if (ok) { shown++; }
      });
      var listed = cards.filter(function (card) { return showFuture || !card.classList.contains("is-future"); }).length;
      if (empty) { empty.hidden = shown !== 0 || listed === 0; }
      if (count) {
        if (!listed) { count.textContent = ""; }
        else if (profile() === "A") { count.textContent = "មេរៀន " + digitsKm(shown) + " / " + digitsKm(listed); }
        else { count.textContent = shown + (shown > 1 ? " leçons affichées sur " : " leçon affichée sur ") + listed; }
      }
      var toggle = document.getElementById("future-toggle");
      if (toggle && toggle._label) { toggle._label(); }
    }

    updateCount = filter;
    input.addEventListener("input", filter);
    all("[data-level]", document.querySelector(".filters") || document.createElement("div")).forEach(function (chip) {
      chip.addEventListener("click", function () {
        level = chip.getAttribute("data-level");
        all(".filters .chip").forEach(function (other) { other.classList.toggle("is-active", other === chip); });
        filter();
      });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "/" && document.activeElement !== input && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        input.focus();
      }
    });
    filter();
  }

  /* --------------------------------------------------------------- Lexique */
  function initLexicon() {
    var list = document.getElementById("lexicon");
    var input = document.getElementById("lex-search");
    if (!list || !input) { return; }
    var items = all(".lex-item", list).filter(function (item) {
      var future = (item.getAttribute("data-date") || "") > TODAY;
      if (future) { item.parentNode.removeChild(item); }   /* mots des leçons à venir */
      return !future;
    });
    var none = document.getElementById("lex-none");
    var count = document.getElementById("lex-count");
    var kind = "";
    function filter() {
      var terms = fold(input.value).split(" ").filter(Boolean), shown = 0;
      items.forEach(function (item) {
        var hay = item.getAttribute("data-search") || "";
        var ok = (!kind || item.getAttribute("data-kind") === kind) &&
          terms.every(function (term) { return hay.indexOf(term) !== -1; });
        item.hidden = !ok;
        if (ok) { shown++; }
      });
      none.hidden = shown !== 0;
      count.textContent = profile() === "A"
        ? kmDigits(shown) + " / " + kmDigits(items.length)
        : shown + " sur " + items.length + (items.length > 1 ? " mots et expressions" : " mot");
    }
    input.addEventListener("input", filter);
    all("#lex-filters [data-kind]").forEach(function (chip) {
      chip.addEventListener("click", function () {
        kind = chip.getAttribute("data-kind");
        all("#lex-filters .chip").forEach(function (other) { other.classList.toggle("is-active", other === chip); });
        filter();
      });
    });
    lexiconCount = filter;
    filter();
  }
  var lexiconCount = null;

  /* -------------------------------------------------------- Initialisation */
  function init() {
    all("[data-audio]").forEach(enhanceAudio);
    all("[data-play-all]").forEach(function (trigger) {
      trigger.addEventListener("click", function () { playSequence(trigger, trigger.getAttribute("data-play-all")); });
    });
    all("[data-profile-choice]").forEach(function (button) {
      button.addEventListener("click", function () { applyProfile(button.getAttribute("data-profile-choice"), true); });
    });
    initSlowToggle();
    initSize();
    initLightAudio();
    initRoleplay();
    initQuiz();
    initFinish();
    initFuture();
    initFutureNotice();
    initSearch();
    initLexicon();
    applyProfile(profile(), false);
    syncNow();
    var anchor = location.hash.slice(1).split("&")[0];
    if (anchor && anchor.indexOf("=") === -1) {
      var target = document.getElementById(decodeURIComponent(anchor));
      if (target && target.scrollIntoView) { target.scrollIntoView(); target.classList.add("is-target"); }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
