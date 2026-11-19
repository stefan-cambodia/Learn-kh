/* FR-KH Learning — cartes mémoire de la page « Réviser » (JavaScript natif, hors ligne). */
(function () {
  "use strict";

  var root = document.documentElement;
  var app = document.getElementById("review-app");
  var dataEl = document.getElementById("review-data");
  if (!app || !dataEl) { return; }

  var ALL = [];
  try { ALL = JSON.parse(dataEl.textContent) || []; } catch (e) { ALL = []; }

  var SESSION = 20, MAX_BOX = 5, KNOWN_BOX = 3, RECENT_LESSONS = 5;
  /* Répétition espacée : une carte de la boîte b revient après INTERVALS[b] jours. */
  var INTERVALS = [0, 1, 2, 4, 8, 16], DAY = 86400000;
  /* « revision.html#lecon=12 » (lien en fin de leçon) : réviser uniquement les mots de cette leçon. */
  var LESSON = (function () { var m = /(?:^|[#&])lecon=(\d+)/.exec(location.hash); return m ? Number(m[1]) : 0; })();
  var ICON_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.2v13.6L19.5 12z"/></svg>';
  var TAGS = { fr: "FR", en: "EN", km: "KH", es: "ES", it: "IT", ru: "RU", zh: "ZH" };
  var CONTENT_LANGS = (window.FRKH_LANGS && window.FRKH_LANGS.all) || ["fr", "en", "km"];
  /* Langues qu'on ne tape pas au clavier dans l'exercice « Écrire » (écriture non latine sans clavier dédié). */
  var NO_WRITE = ["km", "zh"];

  /* Libellés : [français, anglais, khmer] — la langue du profil actif est utilisée. */
  var T = {
    lang_fr: ["Français", "French", "ភាសាបារាំង"],
    lang_en: ["Anglais", "English", "ភាសាអង់គ្លេស"],
    lang_km: ["Khmer", "Khmer", "ភាសាខ្មែរ"],
    lang_es: ["Espagnol", "Spanish", "ភាសាអេស្ប៉ាញ"],
    lang_it: ["Italien", "Italian", "ភាសាអ៊ីតាលី"],
    lang_ru: ["Russe", "Russian", "ភាសារុស្ស៊ី"],
    lang_zh: ["Chinois", "Chinese", "ភាសាចិន"],
    studied: ["Langue révisée", "Language", "ភាសាដែលរំលឹក"],
    mode: ["Exercice", "Exercise", "លំហាត់"],
    recognize: ["Reconnaître le mot", "Recognise the word", "ស្គាល់ពាក្យ"],
    recall: ["Retrouver le mot", "Recall the word", "នឹកឃើញពាក្យ"],
    listen: ["Écouter et choisir", "Listen and choose", "ស្តាប់ ហើយជ្រើសរើស"],
    prompt_listen: ["Écoutez, puis choisissez la bonne traduction.", "Listen, then choose the right translation.",
                    "ស្តាប់ ហើយជ្រើសរើសការបកប្រែត្រឹមត្រូវ។"],
    next: ["Suivant", "Next", "បន្ទាប់"],
    right: ["Bonne réponse !", "Correct!", "ត្រឹមត្រូវ!"],
    wrong: ["Ce n'était pas ça. La bonne réponse :", "Not quite. The right answer:", "មិនត្រឹមត្រូវទេ។ ចម្លើយត្រឹមត្រូវ៖"],
    scope: ["Mots", "Words", "ពាក្យ"],
    recent: ["5 dernières leçons", "Last 5 lessons", "មេរៀន៥ចុងក្រោយ"],
    due: ["À réviser ({n})", "Due ({n})", "ត្រូវរំលឹក ({n})"],
    nothing_due: ["Rien à réviser aujourd'hui : bravo ! Revenez demain, ou choisissez « Toutes les leçons ».",
                  "Nothing to review today: well done! Come back tomorrow, or choose “All lessons”.",
                  "ថ្ងៃនេះគ្មានពាក្យត្រូវរំលឹកទេ។ ល្អណាស់! ត្រលប់មកវិញថ្ងៃស្អែក ឬជ្រើសរើស « មេរៀនទាំងអស់ »។"],
    write: ["Écrire le mot", "Write the word", "សរសេរពាក្យ"],
    prompt_write: ["Écrivez-le en {lang} :", "Write it in {lang}:", "សរសេរជា{lang}៖"],
    check: ["Vérifier", "Check", "ពិនិត្យ"],
    almost: ["Presque ! Attention à l'orthographe :", "Almost! Watch the spelling:", "ជិតត្រូវហើយ! សូមប្រយ័ត្នអក្ខរាវិរុទ្ធ៖"],
    your_answer: ["Votre réponse", "Your answer", "ចម្លើយរបស់អ្នក"],
    placeholder: ["Tapez votre réponse…", "Type your answer…", "វាយចម្លើយ…"],
    all: ["Toutes les leçons", "All lessons", "មេរៀនទាំងអស់"],
    reveal: ["Voir la réponse", "Show the answer", "មើលចម្លើយ"],
    again: ["À revoir", "Again", "ត្រូវរំលឹកទៀត"],
    good: ["Je savais", "I knew it", "ខ្ញុំចាំ"],
    card: ["Carte", "Card", "កាត"],
    of: ["sur", "of", "ក្នុងចំណោម"],
    known: ["mots bien connus", "words known well", "ពាក្យដែលចាំច្បាស់"],
    lesson: ["Leçon", "Lesson", "មេរៀនទី"],
    this_lesson: ["Leçon {n}", "Lesson {n}", "មេរៀនទី {n}"],
    done_title: ["Série terminée !", "Set complete!", "ចប់ហើយ!"],
    done_text: ["Vous saviez {ok} cartes sur {total}.", "You knew {ok} cards out of {total}.", "អ្នកចាំបាន {ok} កាត ក្នុងចំណោម {total}។"],
    again_btn: ["Nouvelle série", "New set", "ចាប់ផ្តើមម្តងទៀត"],
    empty: ["Aucun mot à réviser pour l'instant : terminez d'abord une leçon.",
            "No words to review yet: finish a lesson first.", "មិនទាន់មានពាក្យត្រូវរំលឹកទេ។"],
    keys: ["Clavier : Espace pour retourner la carte ou passer à la suivante, 1 « à revoir », 2 « je savais » (1 à 4 pour choisir à l'écoute), L pour écouter.",
           "Keyboard: Space to flip the card or go to the next one, 1 “again”, 2 “I knew it” (1 to 4 to choose when listening), L to listen.",
           "ក្តារចុច៖ Space បើកចម្លើយ ឬទៅកាតបន្ទាប់, 1 ត្រូវរំលឹកទៀត, 2 ខ្ញុំចាំ (1 ដល់ 4 ពេលស្តាប់), L ស្តាប់។"],
    key_space: ["Espace", "Space", "Space"],
    key_enter: ["Entrée", "Enter", "Enter"],
    play: ["Écouter", "Listen", "ស្តាប់"],
    prompt_recognize: ["Que veut dire ce mot ?", "What does this word mean?", "តើពាក្យនេះមានន័យថាអ្វី?"],
    prompt_recall: ["Comment le dit-on en {lang} ?", "How do you say it in {lang}?", "តើនិយាយជា{lang}ដូចម្តេច?"]
  };

  var store = {
    get: function (key) { try { return window.localStorage.getItem(key); } catch (e) { return null; } },
    set: function (key, value) {
      try { window.localStorage.setItem(key, value); } catch (e) { /* stockage indisponible */ }
      if (/^frkh-boxes-/.test(key) && window.frkhSync) { window.frkhSync.schedule(); }
    }
  };

  var PROFILES = window.FRKH_PROFILES || { fr: ["km", "en"], en: ["km", "fr"], km: ["fr", "en"] };
  var UI_LANGS = ["fr", "en", "km"];
  function profile() {
    var value = root.getAttribute("data-profile");
    return PROFILES[value] ? value : Object.keys(PROFILES)[0];
  }
  function t(key) { return T[key][Math.max(0, UI_LANGS.indexOf(profile()))]; }
  /* Nom d'une langue au milieu d'une phrase : « en khmer », « in Khmer ». */
  function langName(lang) { var name = t("lang_" + lang); return profile() === "fr" ? name.toLowerCase() : name; }
  function kmDigits(n) { return String(n).replace(/\d/g, function (d) { return "០១២៣៤៥៦៧៨៩".charAt(Number(d)); }); }
  function num(n) { return profile() === "km" ? kmDigits(n) : String(n); }
  function esc(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function shuffle(list) {
    for (var i = list.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1)), tmp = list[i];
      list[i] = list[j]; list[j] = tmp;
    }
    return list;
  }

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
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  /* ------------------------------------------------------------- Réglages */
  function shown(lang) { return window.frkhLangShown ? window.frkhLangShown(lang) : true; }
  /* Langues révisables : celles du profil, puis les langues supplémentaires affichées. */
  function targets() {
    var langs = PROFILES[profile()].slice();
    CONTENT_LANGS.forEach(function (l) {
      if (l !== profile() && langs.indexOf(l) === -1 && ALL.some(function (c) { return c[l]; })) { langs.push(l); }
    });
    var visible = langs.filter(shown);
    return visible.length ? visible : langs;
  }
  /* Ordre des langues au dos de la carte : la langue révisée, puis les autres langues affichées. */
  function backOrder() {
    return [settings.lang].concat(CONTENT_LANGS.filter(function (l) { return l !== settings.lang && shown(l); }));
  }
  function native() { return profile(); }

  function prefs() {
    var saved = {};
    try { saved = JSON.parse(store.get("frkh-review-" + profile()) || "{}") || {}; } catch (e) { saved = {}; }
    var langs = targets();
    return {
      lang: langs.indexOf(saved.lang) !== -1 ? saved.lang : langs[0],
      dir: ["recall", "listen", "write"].indexOf(saved.dir) !== -1 ? saved.dir : "recognize",
      scope: LESSON ? "lesson" : ["all", "recent"].indexOf(saved.scope) !== -1 ? saved.scope : "due"
    };
  }
  function fixPrefs() { if (settings.dir === "write" && NO_WRITE.indexOf(settings.lang) !== -1) { settings.dir = "recognize"; } }
  function savePrefs() {
    var saved = { lang: settings.lang, dir: settings.dir, scope: settings.scope === "lesson" ? "due" : settings.scope };
    store.set("frkh-review-" + profile(), JSON.stringify(saved));
  }

  function boxesKey() { return "frkh-boxes-" + profile() + "-" + settings.lang; }
  function boxes() {
    try { return JSON.parse(store.get(boxesKey()) || "{}") || {}; } catch (e) { return {}; }
  }
  function saveBoxes(value) { store.set(boxesKey(), JSON.stringify(value)); }

  function stamp(t) { return typeof t === "number" ? t : (Date.parse(t) || 0); }
  function isDue(entry, now) {
    if (!entry) { return false; }
    return now >= stamp(entry.t) + (INTERVALS[entry.b] || 1) * DAY - 6 * 3600000;
  }
  /* Cartes à réviser aujourd'hui : échues d'abord (les moins bien connues en tête), puis les nouvelles. */
  function dueCards() {
    var known = boxes(), now = Date.now(), due = [], fresh = [];
    available().forEach(function (card) {
      var entry = known[card.id];
      if (!entry) { fresh.push(card); } else if (isDue(entry, now)) { due.push(card); }
    });
    due.sort(function (a, b) { return known[a.id].b - known[b.id].b; });
    fresh.sort(function (a, b) { return a.n - b.n; });
    return shuffle(due).sort(function (a, b) { return known[a.id].b - known[b.id].b; }).concat(fresh);
  }

  /* --------------------------------------------------------------- Audio */
  var current = null;
  function play(src, button) {
    if (!src) { return; }
    if (current) { current.audio.pause(); current.button && current.button.classList.remove("is-playing"); }
    var audio = new Audio(src);
    audio.playbackRate = store.get("frkh-slow") === "1" ? 0.75 : 1;
    current = { audio: audio, button: button };
    if (button) { button.classList.add("is-playing"); }
    audio.addEventListener("ended", function () { if (button) { button.classList.remove("is-playing"); } });
    var attempt = audio.play();
    if (attempt && attempt.catch) { attempt.catch(function () { if (button) { button.classList.remove("is-playing"); } }); }
  }

  /* -------------------------------------------------------------- Séance */
  var settings, queue, position, revealed, score;

  function available() {
    var today = todayISO();
    return ALL.filter(function (card) { return card.d <= today && card[settings.lang]; });
  }

  function pool() {
    if (settings.scope === "lesson") { return ALL.filter(function (card) { return card.n === LESSON && card[settings.lang]; }); }
    if (settings.scope === "due") { return dueCards(); }
    var cards = available();
    if (settings.scope === "recent") {
      var numbers = [];
      cards.forEach(function (card) { if (numbers.indexOf(card.n) === -1) { numbers.push(card.n); } });
      numbers.sort(function (a, b) { return b - a; });
      var keep = numbers.slice(0, RECENT_LESSONS);
      cards = cards.filter(function (card) { return keep.indexOf(card.n) !== -1; });
    }
    return cards;
  }

  function startSession() {
    fixPrefs();
    var known = boxes();
    var cards = pool().slice();
    if (settings.scope !== "due") {
      /* Les cartes ratées passent d'abord, puis les nouvelles, puis les mieux connues. */
      cards = shuffle(cards);
      cards.sort(function (a, b) { return rank(known[a.id]) - rank(known[b.id]); });
    }
    if (settings.dir === "listen") {
      cards = cards.filter(function (card) { return card.a[settings.lang]; });
    }
    queue = cards.slice(0, SESSION);
    if (settings.dir === "listen") { queue.forEach(function (card) { card._choices = choicesFor(card); card._chosen = -1; }); }
    queue.forEach(function (card) { card._typed = null; card._verdict = null; });
    position = 0;
    revealed = false;
    score = { ok: 0, total: 0 };
    draw();
  }
  function rank(entry) { return entry ? entry.b : 1.5; }

  function choicesFor(card) {
    var nat = native(), seen = {};
    seen[card[nat]] = true;
    var others = shuffle((available().length > 8 ? available() : ALL).filter(function (other) {
      if (seen[other[nat]] || other.k !== card.k) { return false; }
      seen[other[nat]] = true;
      return true;
    })).slice(0, 3);
    return shuffle(others.concat([card]));
  }

  function record(card, ok) {
    var known = boxes();
    var box = known[card.id] ? known[card.id].b : 0;
    known[card.id] = { b: ok ? Math.min(MAX_BOX, Math.max(1, box) + 1) : 1, t: Date.now() };
    saveBoxes(known);
    score.total++;
    if (ok) { score.ok++; }
  }

  function next() {
    position++;
    revealed = false;
    if (position >= queue.length && score.total >= 5 && window.frkhActiveDay) { window.frkhActiveDay(); }
    draw();
    if (settings.dir === "listen") { autoPlay(); }
  }

  function answer(ok) {
    var card = queue[position];
    if (!card || !revealed || settings.dir === "listen") { return; }
    record(card, ok);
    next();
  }

  function choose(index) {
    var card = queue[position];
    if (!card || settings.dir !== "listen" || card._chosen !== -1 || !card._choices[index]) { return; }
    card._chosen = index;
    record(card, card._choices[index] === card);
    revealed = true;
    draw();
  }

  function plain(text) {
    var value = String(text || "").toLowerCase().replace(/[’`]/g, "'");
    if (value.normalize) { value = value.normalize("NFD").replace(/[\u0300-\u036f]/g, ""); }
    return value.replace(/œ/g, "oe").replace(/æ/g, "ae").replace(/[.,!?;:…«»"()¿¡]/g, " ").replace(/\s+/g, " ").trim();
  }
  function exact(text) {
    return String(text || "").toLowerCase().replace(/[’`]/g, "'").replace(/[.,!?;:…«»"()¿¡]/g, " ").replace(/\s+/g, " ").trim();
  }
  function bare(text) { return text.replace(/^(le |la |les |l'|un |une |des |the |a |an |to )/, ""); }
  function distance(a, b) {
    var row = [], i, j;
    for (j = 0; j <= b.length; j++) { row[j] = j; }
    for (i = 1; i <= a.length; i++) {
      var prev = row[0];
      row[0] = i;
      for (j = 1; j <= b.length; j++) {
        var tmp = row[j];
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
        prev = tmp;
      }
    }
    return row[b.length];
  }
  /* « right » : identique ; « almost » : accents, article ou une faute de frappe ; « wrong » sinon.
     Les formes séparées par une virgule (« je, moi ») sont toutes acceptées. */
  function grade(typed, expected) {
    var forms = String(expected).split(/\s*,\s*/).concat([expected]);
    var best = "wrong";
    forms.forEach(function (form) {
      if (exact(typed) === exact(form)) { best = "right"; return; }
      var a = bare(plain(typed)), b = bare(plain(form));
      if (best !== "right" && a && (a === b || (b.length >= 5 && distance(a, b) <= 1))) { best = "almost"; }
    });
    return best;
  }
  function submitWrite() {
    var card = currentCard(), input = document.getElementById("fc-input");
    if (!card || settings.dir !== "write" || card._verdict || !input) { return; }
    var typed = input.value.trim();
    if (!typed) { input.focus(); return; }
    card._typed = typed;
    card._verdict = grade(typed, card[settings.lang]);
    record(card, card._verdict !== "wrong");
    revealed = true;
    draw();
    play(card.a[settings.lang], app.querySelector('.fc-back [data-play="' + settings.lang + '"]'));
  }

  function autoPlay() {
    var card = currentCard();
    if (card && settings.dir === "listen" && !revealed) {
      play(card.a[settings.lang], app.querySelector('.fc-front [data-play="' + settings.lang + '"]'));
    }
  }

  /* --------------------------------------------------------------- Rendu */
  function chips(group, options, value) {
    return '<div class="review-group"><span class="review-group-label">' + esc(t(group)) + '</span><div class="review-chips" role="group">' +
      options.map(function (opt) {
        return '<button type="button" class="chip' + (opt.value === value ? " is-active" : "") + '" data-set="' + group +
          '" data-value="' + opt.value + '" aria-pressed="' + (opt.value === value) + '">' + esc(opt.label) + "</button>";
      }).join("") + "</div></div>";
  }

  function row(card, lang, withAudio) {
    if (!card[lang]) { return ""; }
    var reading = lang === "km" ? card.tr : card[lang + "_tr"];
    var translit = reading ? '<p class="translit">' + esc(reading) + "</p>" : "";
    var audio = withAudio && card.a[lang]
      ? '<span class="audio is-enhanced"><button type="button" class="play" data-play="' + lang + '" aria-label="' + esc(t("play")) + '">' + ICON_PLAY + "</button></span>"
      : "";
    return '<div class="lang-row lang-' + lang + '"><span class="lang-tag" aria-hidden="true">' + TAGS[lang] + "</span>" +
      '<div class="lang-text"><p class="lang-main" lang="' + lang + '">' + esc(card[lang]) + "</p>" + translit + "</div>" + audio + "</div>";
  }

  function mastery() {
    var known = boxes(), cards = available(), count = 0;
    cards.forEach(function (card) { if (known[card.id] && known[card.id].b >= KNOWN_BOX) { count++; } });
    return { known: count, total: cards.length };
  }

  function draw() {
    var langs = targets();
    var controls =
      chips("studied", langs.map(function (l) { return { value: l, label: t("lang_" + l) }; }), settings.lang) +
      chips("mode", [{ value: "recognize", label: t("recognize") }, { value: "recall", label: t("recall") },
                     { value: "listen", label: t("listen") }].concat(NO_WRITE.indexOf(settings.lang) === -1 ? [{ value: "write", label: t("write") }] : []),
            settings.dir) +
      chips("scope", (LESSON ? [{ value: "lesson", label: t("this_lesson").replace("{n}", num(LESSON)) }] : [])
        .concat([{ value: "due", label: t("due").replace("{n}", num(dueCards().length)) },
                 { value: "recent", label: t("recent") }, { value: "all", label: t("all") }]), settings.scope);
    var m = mastery();
    var percent = m.total ? Math.round(100 * m.known / m.total) : 0;
    var summary = '<div class="review-mastery"><p>' + num(m.known) + " / " + num(m.total) + " " + esc(t("known")) + "</p>" +
      '<div class="progress-bar" aria-hidden="true"><span style="width:' + percent + '%"></span></div></div>';

    var body;
    if (!queue.length) {
      body = '<p class="empty">' + esc(settings.scope === "due" && available().length ? t("nothing_due") : t("empty")) + "</p>";
    } else if (position >= queue.length) {
      body = '<div class="flashcard flashcard-done"><p class="fc-done-title">' + esc(t("done_title")) + "</p><p>" +
        esc(t("done_text").replace("{ok}", num(score.ok)).replace("{total}", num(score.total))) + "</p>" +
        '<button type="button" class="finish-button fc-restart" data-action="restart">' + esc(t("again_btn")) + "</button></div>";
    } else if (settings.dir === "listen") {
      body = drawListen(queue[position]);
    } else if (settings.dir === "write") {
      body = drawWrite(queue[position]);
    } else {
      var card = queue[position];
      var front = settings.dir === "recognize" ? settings.lang : native();
      var question = settings.dir === "recognize" ? t("prompt_recognize")
        : t("prompt_recall").replace("{lang}", langName(settings.lang));
      var progress = '<p class="fc-progress">' + esc(t("card")) + " " + num(position + 1) + " " + esc(t("of")) + " " + num(queue.length) + "</p>";
      var face = '<p class="fc-question">' + esc(question) + "</p>" +
        '<div class="fc-front lang-' + front + '"><p class="fc-prompt" lang="' + front + '">' + esc(card[front]) + "</p>" +
        (front === "km" && card.tr && profile() !== "km" ? '<p class="translit">' + esc(card.tr) + "</p>" : "") +
        (front !== "km" && card[front + "_tr"] ? '<p class="translit">' + esc(card[front + "_tr"]) + "</p>" : "") +
        (card.a[front] && settings.dir === "recognize"
          ? '<span class="audio is-enhanced"><button type="button" class="play" data-play="' + front + '" aria-label="' + esc(t("play")) + '">' + ICON_PLAY + "</button></span>" : "") +
        "</div>";
      var back = "";
      if (revealed) {
        var order = backOrder();
        back = '<div class="fc-back tri">' + order.map(function (l) { return row(card, l, true); }).join("") + "</div>" +
          '<p class="fc-source"><a data-nav href="' + esc(card.href) + '">' + esc(t("lesson")) + " " + num(card.n) + "</a></p>" +
          '<div class="fc-answers"><button type="button" class="fc-btn fc-again" data-answer="0">' + esc(t("again")) +
          ' <kbd>1</kbd></button><button type="button" class="fc-btn fc-good" data-answer="1">' + esc(t("good")) + " <kbd>2</kbd></button></div>";
      } else {
        back = '<button type="button" class="fc-btn fc-reveal" data-action="reveal">' + esc(t("reveal")) + " <kbd>" + esc(t("key_space")) + "</kbd></button>";
      }
      body = progress + '<div class="flashcard' + (revealed ? " is-revealed" : "") + '">' + face + back + "</div>";
    }
    app.innerHTML = '<div class="review-controls">' + controls + "</div>" + summary + body +
      '<p class="review-keys">' + esc(t("keys")) + "</p>";
    var input = document.getElementById("fc-input");
    if (input && !input.disabled) { try { input.focus({ preventScroll: true }); } catch (e) { input.focus(); } }
  }

  function drawWrite(card) {
    var nat = native();
    var progress = '<p class="fc-progress">' + esc(t("card")) + " " + num(position + 1) + " " + esc(t("of")) + " " + num(queue.length) + "</p>";
    var face = '<p class="fc-question">' + esc(t("prompt_write").replace("{lang}", langName(settings.lang))) + "</p>" +
      '<div class="fc-front lang-' + nat + '"><p class="fc-prompt" lang="' + nat + '">' + esc(card[nat]) + "</p></div>";
    var form = '<form class="fc-write" data-write autocomplete="off"><input id="fc-input" class="fc-input" type="text" lang="' + settings.lang +
      '" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="' + esc(t("placeholder")) + '"' +
      (card._verdict ? ' value="' + esc(card._typed) + '" disabled' : "") + '>' +
      (card._verdict ? "" : '<button type="submit" class="fc-btn">' + esc(t("check")) + "</button>") + "</form>";
    var after = "";
    if (card._verdict) {
      var label = card._verdict === "right" ? t("right") : card._verdict === "almost" ? t("almost") : t("wrong");
      var order = backOrder();
      after = '<p class="fc-verdict ' + (card._verdict === "wrong" ? "is-wrong" : "is-right") + '">' + esc(label) + "</p>" +
        '<div class="fc-back tri">' + order.map(function (l) { return row(card, l, true); }).join("") + "</div>" +
        '<button type="button" class="fc-btn fc-reveal" data-action="next">' + esc(t("next")) + " <kbd>" + esc(t("key_enter")) + "</kbd></button>";
    }
    return progress + '<div class="flashcard fc-writing' + (card._verdict ? " is-revealed is-" + card._verdict : "") + '">' +
      face + form + after + "</div>";
  }

  function drawListen(card) {
    var nat = native();
    var progress = '<p class="fc-progress">' + esc(t("card")) + " " + num(position + 1) + " " + esc(t("of")) + " " + num(queue.length) + "</p>";
    var face = '<p class="fc-question">' + esc(t("prompt_listen")) + "</p>" +
      '<div class="fc-front fc-listen lang-' + settings.lang + '">' +
      '<span class="audio is-enhanced"><button type="button" class="play play-big" data-play="' + settings.lang + '" aria-label="' + esc(t("play")) + '">' + ICON_PLAY + "</button></span></div>";
    var choices = '<div class="fc-choices">' + card._choices.map(function (choice, i) {
      var cls = "fc-choice";
      if (card._chosen !== -1) {
        if (choice === card) { cls += " is-right"; }
        else if (i === card._chosen) { cls += " is-wrong"; }
      }
      return '<button type="button" class="' + cls + '" data-choice="' + i + '"' + (card._chosen !== -1 ? " disabled" : "") +
        '><kbd>' + (i + 1) + '</kbd><span lang="' + nat + '">' + esc(choice[nat]) + "</span></button>";
    }).join("") + "</div>";
    var after = "";
    if (card._chosen !== -1) {
      var ok = card._choices[card._chosen] === card;
      var order = backOrder();
      after = '<p class="fc-verdict ' + (ok ? "is-right" : "is-wrong") + '">' + esc(ok ? t("right") : t("wrong")) + "</p>" +
        '<div class="fc-back tri">' + order.map(function (l) { return row(card, l, true); }).join("") + "</div>" +
        '<button type="button" class="fc-btn fc-reveal" data-action="next">' + esc(t("next")) + " <kbd>" + esc(t("key_space")) + "</kbd></button>";
    }
    return progress + '<div class="flashcard' + (revealed ? " is-revealed" : "") + '">' + face + choices + after + "</div>";
  }

  function currentCard() { return queue && position < queue.length ? queue[position] : null; }

  app.addEventListener("submit", function (event) {
    if (event.target.hasAttribute("data-write")) { event.preventDefault(); submitWrite(); }
  });

  app.addEventListener("click", function (event) {
    var target = event.target.closest("button");
    if (!target) { return; }
    if (target.hasAttribute("data-set")) {
      var group = target.getAttribute("data-set"), value = target.getAttribute("data-value");
      if (group === "studied") { settings.lang = value; }
      if (group === "mode") { settings.dir = value; }
      if (group === "scope") { settings.scope = value; }
      savePrefs();
      startSession();
      autoPlay();
      return;
    }
    if (target.hasAttribute("data-play")) {
      var card = currentCard();
      if (card) { play(card.a[target.getAttribute("data-play")], target); }
      return;
    }
    if (target.hasAttribute("data-answer")) { answer(target.getAttribute("data-answer") === "1"); return; }
    if (target.hasAttribute("data-choice")) { choose(Number(target.getAttribute("data-choice"))); return; }
    var action = target.getAttribute("data-action");
    if (action === "reveal") { reveal(); }
    if (action === "restart") { startSession(); autoPlay(); }
    if (action === "next") { next(); }
  });

  function reveal() {
    var card = currentCard();
    if (!card || revealed) { return; }
    revealed = true;
    draw();
    play(card.a[settings.lang], app.querySelector('.fc-back [data-play="' + settings.lang + '"]'));
  }

  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey || event.metaKey || event.altKey) { return; }
    var tag = (event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") { return; }
    var card = currentCard();
    if (!card) { return; }
    if (settings.dir === "write") {
      if ((event.key === " " || event.key === "Enter") && revealed) { event.preventDefault(); next(); }
      return;
    }
    if (settings.dir === "listen") {
      if (/^[1-4]$/.test(event.key) && !revealed) { event.preventDefault(); choose(Number(event.key) - 1); }
      else if ((event.key === " " || event.key === "Enter") && revealed) { event.preventDefault(); next(); }
      else if (event.key === "l" || event.key === "L") { play(card.a[settings.lang], app.querySelector('[data-play="' + settings.lang + '"]')); }
      return;
    }
    if ((event.key === " " || event.key === "Enter") && !revealed) { event.preventDefault(); reveal(); }
    else if (revealed && (event.key === "1" || event.key === "ArrowLeft")) { event.preventDefault(); answer(false); }
    else if (revealed && (event.key === "2" || event.key === "ArrowRight")) { event.preventDefault(); answer(true); }
    else if (event.key === "l" || event.key === "L") {
      var lang = revealed || settings.dir === "recognize" ? settings.lang : null;
      if (lang) { play(card.a[lang], app.querySelector('[data-play="' + lang + '"]')); }
    }
  });

  function init() {
    settings = prefs();
    startSession();
  }

  /* Changer de profil (bouton en haut de page) recharge les réglages et la progression de l'autre apprenant. */
  if (window.MutationObserver) {
    new MutationObserver(function (changes) {
      changes.forEach(function (change) { if (change.attributeName === "data-profile") { init(); } });
    }).observe(root, { attributes: true });
  }
  /* Langue masquée ou réaffichée dans le sélecteur « Langues » : les langues révisables changent. */
  root.addEventListener("frkh:langs", function () { init(); });
  document.addEventListener("frkh:synced", function () {
    if (!position && !revealed) { init(); } else { /* séance en cours : on garde les cartes */ }
  });
  init();
})();
