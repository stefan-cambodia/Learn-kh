/* FR-KH Learning — page « Traduire » : traduction écrite et vocale entre les sept langues du site.
 *
 * Contrairement au reste du site, cette page a besoin d'Internet :
 *  - traduction : service gratuit de Google Traduction (sans clé), MyMemory en secours ;
 *  - dictée : reconnaissance vocale du navigateur (Chrome, Edge, Safari récent) ;
 *  - lecture : voix de Google Traduction, ou à défaut une voix installée dans l'appareil.
 * Aucun historique n'est conservé ; seules les deux langues choisies sont mémorisées.
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var app = document.getElementById("tr-app");
  var dataEl = document.getElementById("tr-data");
  if (!app || !dataEl) { return; }

  var META = {};
  try { META = JSON.parse(dataEl.textContent) || {}; } catch (e) { META = {}; }
  var LANGS = Object.keys(META);

  /* Codes de langue des services (le chinois est le mandarin simplifié). */
  var API = { zh: "zh-CN" };
  function api(lang) { return API[lang] || lang; }
  /* Langues dont on affiche la translittération latine. */
  var TRANSLIT = { km: true, ru: true, zh: true };
  var SLOW_RATE = 0.75, MAX_TTS = 180, DEBOUNCE = 700;
  var KEY_LANGS = "frkh-translate-langs";

  /* Libellés : [français, anglais, khmer] — la langue du profil actif est utilisée. */
  var T = {
    listening: ["Je vous écoute… parlez en {lang}.", "Listening… speak in {lang}.", "កំពុងស្តាប់… សូមនិយាយជា{lang}។"],
    translating: ["Traduction…", "Translating…", "កំពុងបកប្រែ…"],
    no_mic: ["La dictée n'est pas disponible dans ce navigateur. Essayez Chrome ou Edge.",
             "Dictation is not available in this browser. Try Chrome or Edge.",
             "កម្មវិធីរុករកនេះមិនអាចស្តាប់សំឡេងបានទេ។ សូមសាកល្បង Chrome ឬ Edge។"],
    insecure: ["La dictée a besoin d'une page en https (le site en ligne).",
               "Dictation needs an https page (the online site).",
               "ការស្តាប់សំឡេងត្រូវការទំព័រ https (គេហទំព័រលើអ៊ីនធឺណិត)។"],
    denied: ["Le micro est bloqué. Autorisez-le dans les réglages du navigateur.",
             "The microphone is blocked. Allow it in the browser settings.",
             "មីក្រូហ្វូនត្រូវបានបិទ។ សូមអនុញ្ញាតក្នុងការកំណត់កម្មវិធីរុករក។"],
    no_speech: ["Je n'ai rien entendu. Touchez « Parler » et réessayez.",
                "I didn't hear anything. Tap “Speak” and try again.",
                "មិនបានឮអ្វីទេ។ សូមចុច «និយាយ» ហើយសាកម្តងទៀត។"],
    lang_unsupported: ["La dictée en {lang} n'est pas prise en charge par ce navigateur.",
                       "Dictation in {lang} is not supported by this browser.",
                       "កម្មវិធីរុករកនេះមិនអាចស្តាប់{lang}បានទេ។"],
    mic_error: ["La dictée s'est arrêtée (connexion ?). Réessayez.",
                "Dictation stopped (connection?). Try again.",
                "ការស្តាប់បានឈប់ (អ៊ីនធឺណិត?)។ សូមសាកម្តងទៀត។"],
    offline: ["Pas de connexion Internet : la traduction est impossible pour l'instant.",
              "No Internet connection: translation is not possible right now.",
              "គ្មានអ៊ីនធឺណិត៖ មិនអាចបកប្រែបានទេពេលនេះ។"],
    failed: ["La traduction a échoué. Vérifiez la connexion et réessayez.",
             "Translation failed. Check the connection and try again.",
             "ការបកប្រែបរាជ័យ។ សូមពិនិត្យអ៊ីនធឺណិត ហើយសាកម្តងទៀត។"],
    no_voice: ["Aucune voix disponible pour le {lang} sur cet appareil.",
               "No voice available for {lang} on this device.",
               "គ្មានសំឡេងសម្រាប់{lang}នៅលើឧបករណ៍នេះទេ។"],
    copied: ["Traduction copiée.", "Translation copied.", "បានចម្លងការបកប្រែ។"],
    fallback: ["Traduit avec MyMemory (Google Traduction ne répond pas).",
               "Translated with MyMemory (Google Translate is not responding).",
               "បកប្រែដោយ MyMemory (Google Translate មិនឆ្លើយតប)។"]
  };
  var IDX = { fr: 0, en: 1, km: 2 };
  function profile() { var p = root.getAttribute("data-profile"); return IDX.hasOwnProperty(p) ? p : "fr"; }
  function t(key, lang) {
    var text = T[key][IDX[profile()]] || T[key][0];
    if (lang) {
      var names = (META[lang] && META[lang].names) || {};
      text = text.replace("{lang}", names[profile()] || names.fr || lang);
    }
    return text;
  }

  var store = {
    get: function (key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } },
    set: function (key, value) { try { window.localStorage.setItem(key, value); } catch (e) { /* stockage indisponible */ } }
  };
  function slow() { return store.get("frkh-slow") === "1"; }

  var $ = function (id) { return document.getElementById(id); };
  var fromSel = $("tr-from"), toSel = $("tr-to"), swapBtn = $("tr-swap");
  var input = $("tr-text"), srcTranslit = $("tr-src-translit");
  var micBtn = $("tr-mic"), clearBtn = $("tr-clear"), goBtn = $("tr-go");
  var inPane = $("tr-in"), outPane = $("tr-out");
  var result = $("tr-result"), resultTranslit = $("tr-result-translit");
  var speakBtn = $("tr-speak"), copyBtn = $("tr-copy"), statusEl = $("tr-status");

  /* ------------------------------------------------------------ État et messages */
  var current = { text: "", lang: "" };   // dernière traduction affichée
  var lastQuery = "";                     // « texte|de|vers » déjà traduit
  var seq = 0, timer = null;

  function status(message, kind) {
    if (!message) { statusEl.hidden = true; statusEl.textContent = ""; statusEl.className = "tr-status"; return; }
    statusEl.hidden = false;
    statusEl.textContent = message;
    statusEl.className = "tr-status" + (kind ? " is-" + kind : "");
  }

  /* ------------------------------------------------------------ Choix des langues */
  function defaults() {
    var saved = null;
    try { saved = JSON.parse(store.get(KEY_LANGS) || "null"); } catch (e) { saved = null; }
    if (saved && META[saved.from] && META[saved.to] && saved.from !== saved.to) { return saved; }
    var p = profile(), learns = (window.FRKH_PROFILES && window.FRKH_PROFILES[p]) || [];
    var to = learns.filter(function (l) { return META[l] && l !== p; })[0] || LANGS.filter(function (l) { return l !== p; })[0];
    return { from: META[p] ? p : LANGS[0], to: to };
  }

  function applyLangs() {
    var from = fromSel.value, to = toSel.value;
    inPane.setAttribute("data-lang", from);
    outPane.setAttribute("data-lang", to);
    input.setAttribute("lang", from);
    result.setAttribute("lang", to);
    micBtn.setAttribute("data-lang", from);
    store.set(KEY_LANGS, JSON.stringify({ from: from, to: to }));
  }

  function onLangChange(changed) {
    /* Même langue des deux côtés : on échange plutôt que de traduire vers soi-même. */
    if (fromSel.value === toSel.value) {
      /* L'autre menu reprend l'ancienne langue de celui qu'on vient de changer (échange). */
      var other = changed === fromSel ? toSel : fromSel, prev = changed.getAttribute("data-prev");
      other.value = prev && prev !== changed.value ? prev : LANGS.filter(function (l) { return l !== changed.value; })[0];
    }
    fromSel.setAttribute("data-prev", fromSel.value);
    toSel.setAttribute("data-prev", toSel.value);
    stopListening();
    stopSpeaking();
    applyLangs();
    clearResult();
    translateNow();
  }

  function swap() {
    var from = fromSel.value;
    fromSel.value = toSel.value;
    toSel.value = from;
    fromSel.setAttribute("data-prev", fromSel.value);
    toSel.setAttribute("data-prev", toSel.value);
    /* La traduction devient le texte à traduire. */
    if (current.text) { input.value = current.text; }
    stopListening();
    stopSpeaking();
    applyLangs();
    clearResult();
    translateNow();
  }

  /* ------------------------------------------------------------ Traduction */
  function showResult(text, translit, sourceTranslit, lang) {
    current = { text: text, lang: lang };
    result.textContent = text;
    var showT = TRANSLIT[lang] && translit && translit !== text;
    resultTranslit.textContent = showT ? translit : "";
    resultTranslit.hidden = !showT;
    var from = fromSel.value, showS = TRANSLIT[from] && sourceTranslit && sourceTranslit !== input.value.trim();
    srcTranslit.textContent = showS ? sourceTranslit : "";
    srcTranslit.hidden = !showS;
    speakBtn.disabled = copyBtn.disabled = !text;
    outPane.classList.toggle("has-result", !!text);
  }

  function clearResult() {
    showResult("", "", "", toSel.value);
    lastQuery = "";
  }

  function viaGoogle(text, from, to, signal) {
    var url = "https://translate.googleapis.com/translate_a/single?client=gtx&dt=t&dt=rm" +
      "&sl=" + encodeURIComponent(api(from)) + "&tl=" + encodeURIComponent(api(to)) + "&q=" + encodeURIComponent(text);
    return fetch(url, { signal: signal, referrerPolicy: "no-referrer" }).then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    }).then(function (data) {
      var parts = (data && data[0]) || [], out = "", translit = "", source = "";
      parts.forEach(function (seg) {
        if (!seg) { return; }
        if (typeof seg[0] === "string") { out += seg[0]; }
        else {   // segment de translittération : [null, null, cible, source]
          if (typeof seg[2] === "string") { translit += seg[2]; }
          if (typeof seg[3] === "string") { source += seg[3]; }
        }
      });
      if (!out) { throw new Error("réponse vide"); }
      return { text: out, translit: translit.trim(), source: source.trim() };
    });
  }

  function viaMyMemory(text, from, to, signal) {
    var url = "https://api.mymemory.translated.net/get?q=" + encodeURIComponent(text.slice(0, 500)) +
      "&langpair=" + encodeURIComponent(api(from) + "|" + api(to));
    return fetch(url, { signal: signal, referrerPolicy: "no-referrer" }).then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    }).then(function (data) {
      var out = data && data.responseData && data.responseData.translatedText;
      if (!out || Number(data.responseStatus) !== 200) { throw new Error("MyMemory : " + (data && data.responseDetails)); }
      return { text: out, translit: "", source: "", fallback: true };
    });
  }

  var controller = null;
  function translateNow(thenSpeak) {
    clearTimeout(timer);
    var text = input.value.trim(), from = fromSel.value, to = toSel.value;
    if (!text) { clearResult(); status(""); return; }
    var query = text + "|" + from + "|" + to;
    if (query === lastQuery) { if (thenSpeak) { speak(); } return; }
    if (navigator.onLine === false) { status(t("offline"), "error"); return; }
    if (controller) { controller.abort(); }
    controller = typeof AbortController === "function" ? new AbortController() : null;
    var signal = controller ? controller.signal : undefined, mine = ++seq;
    status(t("translating"), "busy");
    outPane.classList.add("is-busy");
    viaGoogle(text, from, to, signal).catch(function (err) {
      if (err && err.name === "AbortError") { throw err; }
      return viaMyMemory(text, from, to, signal);
    }).then(function (res) {
      if (mine !== seq) { return; }
      lastQuery = query;
      showResult(res.text, res.translit, res.source, to);
      status(res.fallback ? t("fallback") : "", res.fallback ? "info" : "");
      if (thenSpeak) { speak(); }
    }).catch(function (err) {
      if (mine !== seq || (err && err.name === "AbortError")) { return; }
      status(t("failed"), "error");
    }).then(function () {
      if (mine === seq) { outPane.classList.remove("is-busy"); }
    });
  }

  function translateSoon() {
    clearTimeout(timer);
    timer = setTimeout(function () { translateNow(false); }, DEBOUNCE);
  }

  /* ------------------------------------------------------------ Lecture à voix haute */
  var speaking = null;   // { audio } ou { synth: true }

  function setSpeaking(on) {
    speakBtn.classList.toggle("is-playing", on);
    speakBtn.setAttribute("aria-pressed", String(on));
  }

  function stopSpeaking() {
    if (speaking && speaking.audio) { speaking.audio.pause(); speaking.audio.removeAttribute("src"); }
    if (window.speechSynthesis) { try { window.speechSynthesis.cancel(); } catch (e) { /* rien */ } }
    speaking = null;
    setSpeaking(false);
  }

  /* Découpe aux ponctuations : la voix de Google Traduction accepte environ 200 caractères. */
  function chunks(text) {
    var pieces = text.replace(/\s+/g, " ").replace(/([.!?។៕,;:。！？，；：])\s*/g, "$1\u0000").split("\u0000"),
      out = [], cur = "";
    pieces.forEach(function (piece) {
      while (piece.length > MAX_TTS) {
        var cut = piece.lastIndexOf(" ", MAX_TTS);
        if (cut <= 0) { cut = MAX_TTS; }
        out.push(piece.slice(0, cut).trim());
        piece = piece.slice(cut).trim();
      }
      if (cur && cur.length + 1 + piece.length > MAX_TTS) { out.push(cur); cur = piece; }
      else { cur = (cur + " " + piece).trim(); }
    });
    if (cur) { out.push(cur); }
    return out.filter(Boolean);
  }

  function findVoice(lang) {
    if (!window.speechSynthesis) { return null; }
    var locale = (META[lang] && META[lang].locale) || lang, voices = window.speechSynthesis.getVoices() || [];
    var norm = function (v) { return String(v.lang || "").replace("_", "-").toLowerCase(); };
    return voices.filter(function (v) { return norm(v) === locale.toLowerCase(); })[0] ||
      voices.filter(function (v) { return norm(v).indexOf(lang) === 0; })[0] || null;
  }

  function speakWithDevice(text, lang) {
    var voice = findVoice(lang);
    if (!voice) { stopSpeaking(); status(t("no_voice", lang), "error"); return; }
    var u = new SpeechSynthesisUtterance(text);
    u.voice = voice;
    u.lang = voice.lang;
    u.rate = slow() ? SLOW_RATE : 1;
    u.onend = u.onerror = function () { if (speaking && speaking.synth) { speaking = null; setSpeaking(false); } };
    speaking = { synth: true };
    setSpeaking(true);
    window.speechSynthesis.speak(u);
  }

  function speak() {
    var text = current.text, lang = current.lang;
    if (!text) { return; }
    stopSpeaking();
    var parts = chunks(text), i = 0, audio = new Audio(), started = false;
    try { audio.referrerPolicy = "no-referrer"; } catch (e) { /* ancien navigateur */ }
    speaking = { audio: audio };
    setSpeaking(true);
    function next() {
      if (!speaking || speaking.audio !== audio) { return; }
      if (i >= parts.length) { speaking = null; setSpeaking(false); return; }
      audio.src = "https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=" + encodeURIComponent(api(lang)) +
        "&total=" + parts.length + "&idx=" + i + "&textlen=" + parts[i].length + "&q=" + encodeURIComponent(parts[i]);
      i += 1;
      audio.playbackRate = slow() ? SLOW_RATE : 1;
      var attempt = audio.play();
      if (attempt && typeof attempt.catch === "function") {
        attempt.then(function () { started = true; }).catch(function (err) {
          if (err && err.name === "AbortError") { return; }
          fail();
        });
      }
    }
    /* La voix en ligne ne répond pas : on se rabat sur une voix de l'appareil. */
    function fail() {
      if (!speaking || speaking.audio !== audio) { return; }
      speaking = null;
      if (started) { setSpeaking(false); return; }
      speakWithDevice(text, lang);
    }
    audio.addEventListener("ended", next);
    audio.addEventListener("error", fail);
    next();
  }

  /* ------------------------------------------------------------ Dictée */
  var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  var rec = null, listening = false, heard = "", prefix = "";

  function setListening(on) {
    listening = on;
    micBtn.classList.toggle("is-listening", on);
    micBtn.setAttribute("aria-pressed", String(on));
  }

  function stopListening() {
    if (rec && listening) { try { rec.stop(); } catch (e) { /* déjà arrêtée */ } }
  }

  function startListening() {
    if (!Recognition) { status(t("no_mic"), "error"); return; }
    if (window.isSecureContext === false) { status(t("insecure"), "error"); return; }
    stopSpeaking();
    var lang = fromSel.value, error = null;
    rec = new Recognition();
    rec.lang = (META[lang] && META[lang].locale) || lang;
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    heard = "";
    prefix = input.value.trim() ? input.value.trim() + " " : "";
    rec.onstart = function () { setListening(true); status(t("listening", lang), "busy"); };
    rec.onresult = function (event) {
      var finalText = "", interim = "";
      for (var i = 0; i < event.results.length; i++) {
        var r = event.results[i];
        if (r.isFinal) { finalText += r[0].transcript; } else { interim += r[0].transcript; }
      }
      heard = (finalText || interim).trim();
      input.value = prefix + heard;
    };
    rec.onerror = function (event) { error = event.error || "error"; };
    rec.onend = function () {
      setListening(false);
      rec = null;
      if (error === "not-allowed" || error === "service-not-allowed") { status(t("denied"), "error"); }
      else if (error === "no-speech" || (!error && !heard)) { status(t("no_speech"), "info"); }
      else if (error === "language-not-supported") { status(t("lang_unsupported", lang), "error"); }
      else if (error && error !== "aborted") { status(t("mic_error"), "error"); }
      else { status(""); }
      /* Phrase dictée : on traduit, puis on lit la traduction à voix haute. */
      if (heard) { translateNow(true); }
    };
    try { rec.start(); } catch (e) { setListening(false); status(t("mic_error"), "error"); }
  }

  /* ------------------------------------------------------------ Branchements */
  function placeholder() {
    input.placeholder = input.getAttribute("data-placeholder-" + profile()) || input.getAttribute("data-placeholder-fr");
  }

  var start = defaults();
  fromSel.value = start.from;
  toSel.value = start.to;
  fromSel.setAttribute("data-prev", fromSel.value);
  toSel.setAttribute("data-prev", toSel.value);
  applyLangs();
  placeholder();
  if (!Recognition) { micBtn.classList.add("is-unavailable"); micBtn.title = t("no_mic"); }

  fromSel.addEventListener("change", function () { onLangChange(fromSel); });
  toSel.addEventListener("change", function () { onLangChange(toSel); });
  swapBtn.addEventListener("click", swap);
  input.addEventListener("input", function () {
    if (!input.value.trim()) { clearTimeout(timer); clearResult(); status(""); return; }
    translateSoon();
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); translateNow(false); }
  });
  goBtn.addEventListener("click", function () { translateNow(false); });
  clearBtn.addEventListener("click", function () {
    stopListening();
    stopSpeaking();
    input.value = "";
    clearResult();
    status("");
    input.focus();
  });
  micBtn.addEventListener("click", function () { if (listening) { stopListening(); } else { startListening(); } });
  speakBtn.addEventListener("click", function () { if (speaking) { stopSpeaking(); } else { speak(); } });
  copyBtn.addEventListener("click", function () {
    if (!current.text) { return; }
    var done = function () { status(t("copied"), "info"); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(current.text).then(done, function () { status(""); });
    }
  });
  root.addEventListener("frkh:profile", function () { placeholder(); });
  /* Les voix de l'appareil se chargent après la page dans Chrome. */
  if (window.speechSynthesis && "onvoiceschanged" in window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = function () { window.speechSynthesis.getVoices(); };
  }
  clearResult();
})();
