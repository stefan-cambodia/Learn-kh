#!/usr/bin/env node
/* Contrôle du site dans un vrai navigateur (Firefox sans affichage, protocole WebDriver BiDi).
 *
 * Vérifie, sur un site déjà généré : l'absence d'erreur JavaScript et de requête réseau,
 * l'affichage du khmer avec la police embarquée, la recherche, le changement de profil,
 * la navigation entre leçons et la lecture réelle des fichiers audio (MP3 ou WAV).
 *
 * Usage : node tests/browser_check.mjs <dossier_du_site> [dossier_des_captures]
 * Nécessite Node.js 22+ et Firefox. Aucun module à installer.
 */
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const site = resolve(process.argv[2] || ".");
const shots = process.argv[3] ? resolve(process.argv[3]) : null;
if (!existsSync(join(site, "index.html"))) {
  console.error(`index.html introuvable dans ${site}`);
  process.exit(2);
}
if (shots) mkdirSync(shots, { recursive: true });

const profileDir = mkdtempSync(join(tmpdir(), "frkh-firefox-"));
writeFileSync(join(profileDir, "user.js"), [
  'user_pref("media.autoplay.default", 0);',
  'user_pref("media.autoplay.blocking_policy", 0);',
  'user_pref("media.autoplay.block-webaudio", false);',
  'user_pref("browser.shell.checkDefaultBrowser", false);',
  'user_pref("datareporting.policy.dataSubmissionEnabled", false);',
  'user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);',
  'user_pref("browser.aboutwelcome.enabled", false);',
  'user_pref("network.proxy.type", 1);',                 // aucun accès réseau possible :
  'user_pref("network.proxy.http", "127.0.0.1");',        // toute requête externe échouerait,
  'user_pref("network.proxy.http_port", 9);',             // ce qui prouve le fonctionnement hors ligne
  'user_pref("network.proxy.ssl", "127.0.0.1");',
  'user_pref("network.proxy.ssl_port", 9);',
  'user_pref("network.proxy.no_proxies_on", "");',
  'user_pref("network.proxy.allow_hijacking_localhost", false);',
  // FRKH_DARK=1 : contrôle et captures avec le thème sombre
  `user_pref("layout.css.prefers-color-scheme.content-override", ${process.env.FRKH_DARK ? 0 : 1});`,
].join("\n"));

const firefox = spawn(process.env.FIREFOX || "firefox",
  ["--headless", "--no-remote", "--profile", profileDir, "--remote-debugging-port=0", "about:blank"],
  { stdio: ["ignore", "ignore", "pipe"] });

let finished = false;
function cleanup(code) {
  if (finished) return;
  finished = true;
  try { firefox.kill("SIGKILL"); } catch { /* déjà arrêté */ }
  setTimeout(() => {
    try { rmSync(profileDir, { recursive: true, force: true }); } catch { /* sans importance */ }
    process.exit(code);
  }, 300);
}
process.on("SIGINT", () => cleanup(130));
setTimeout(() => { console.error("Délai dépassé."); cleanup(3); }, 180000).unref();

const endpoint = await new Promise((ok, ko) => {
  let buffer = "";
  firefox.stderr.on("data", (chunk) => {
    buffer += chunk;
    const match = /WebDriver BiDi listening on (ws:\/\/\S+)/.exec(buffer);
    if (match) ok(match[1]);
  });
  firefox.on("error", (error) => ko(new Error(`Firefox introuvable : ${error.message}`)));
  firefox.on("exit", (code) => ko(new Error(`Firefox s'est arrêté (code ${code})`)));
}).catch((error) => { console.error(String(error.message || error)); cleanup(2); });

const socket = new WebSocket(`${endpoint}/session`);
await new Promise((ok, ko) => { socket.onopen = ok; socket.onerror = () => ko(new Error("connexion BiDi impossible")); });
let nextId = 0;
const pending = new Map();
const pageErrors = [];
const requests = [];
socket.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const { ok, ko } = pending.get(message.id);
    pending.delete(message.id);
    if (message.type === "error") ko(new Error(`${message.error}: ${message.message}`)); else ok(message.result);
  } else if (message.method === "log.entryAdded" && message.params.level === "error") {
    pageErrors.push(message.params.text);
  } else if (message.method === "network.beforeRequestSent") {
    requests.push(message.params.request.url);
  }
};
function send(method, params = {}) {
  const id = ++nextId;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((ok, ko) => pending.set(id, { ok, ko }));
}

await send("session.new", { capabilities: {} });
await send("session.subscribe", { events: ["log.entryAdded", "network.beforeRequestSent"] });
const tree = await send("browsingContext.getTree", {});
const context = tree.contexts[0].context;

async function open(path, width = 1280, height = 900) {
  await send("browsingContext.setViewport", { context, viewport: { width, height } });
  await send("browsingContext.navigate", { context, url: "about:blank", wait: "complete" });
  const [file, hash] = path.split("#");
  await send("browsingContext.navigate",
    { context, url: pathToFileURL(join(site, file)).href + (hash ? `#${hash}` : ""), wait: "complete" });
  await evaluate("new Promise(r => setTimeout(r, 250))");
}
async function evaluate(expression) {
  const result = await send("script.evaluate", {
    expression: `(async () => JSON.stringify(await (${expression})))()`,
    target: { context }, awaitPromise: true, resultOwnership: "none",
  });
  if (result.type !== "success") throw new Error(`script : ${JSON.stringify(result.exceptionDetails?.text || result)}`);
  return result.result.value === undefined ? undefined : JSON.parse(result.result.value);
}
async function capture(name, full = true) {
  if (!shots) return;
  const shot = await send("browsingContext.captureScreenshot", { context, origin: full ? "document" : "viewport" });
  writeFileSync(join(shots, `${name}.png`), Buffer.from(shot.data, "base64"));
}

const results = [];
function check(label, condition, detail = "") {
  results.push({ label, ok: Boolean(condition), detail });
  console.log(`${condition ? "  OK    " : "  ÉCHEC "} ${label}${detail ? ` — ${detail}` : ""}`);
}

try {
  /* ------------------------------------------------------------------ Index */
  await open("index.html#profil=fr");
  const index = await evaluate(`({
    title: document.title,
    cards: [...document.querySelectorAll(".lesson-card")].map(c => Number(c.dataset.number)),
    stats: [...document.querySelectorAll(".stat")].map(s => s.innerText.replace(/\\s+/g, " ").trim()),
    links: [...document.querySelectorAll(".lesson-link")].map(a => a.getAttribute("href")),
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
  })`);
  check("index : titre du site", /Learning/.test(index.title), index.title);
  check("index : au moins trois leçons listées", index.cards.length >= 3, `${index.cards.length} leçon(s)`);
  check("index : leçons de la plus récente à la plus ancienne",
    index.cards.every((n, i) => i === 0 || index.cards[i - 1] > n), index.cards.join(", "));
  check("index : trois indicateurs (leçons, mots, niveau)", index.stats.length === 3, index.stats.join(" | "));
  await capture("index-profil-fr-ordinateur");

  const total = index.cards.length;
  async function search(term) {
    return evaluate(`(() => { const i = document.getElementById("search"); i.value = ${JSON.stringify(term)};
      i.dispatchEvent(new Event("input", { bubbles: true }));
      return [...document.querySelectorAll(".lesson-card")].filter(c => !c.hidden).map(c => Number(c.dataset.number)); })()`);
  }
  const last = Math.max(...index.cards);
  const terms = await evaluate(`(() => { const card = document.querySelector('.lesson-card[data-number="1"]');
    const w = card.querySelector(".lesson-words li"); const s = w.querySelectorAll("span");
    return { fr: s[0].textContent, en: s[1].textContent, km: s[2].textContent,
             date: card.querySelector("time").getAttribute("datetime") }; })()`);
  for (const [label, term, expected] of [
    ["numéro", String(last), last], ["date", terms.date, 1], ["mot français", terms.fr, 1],
    ["mot anglais", terms.en, 1], ["mot khmer", terms.km, 1]]) {
    const found = await search(term);
    check(`recherche par ${label} « ${term} »`, found.includes(expected) && found.length < total + (total === 1 ? 1 : 0),
      `leçon(s) trouvée(s) : ${found.join(", ") || "aucune"}`);
  }
  const exact = await search("2");
  const khmerDigit = await search("២");
  check("recherche par numéro : « 2 » et « ២ » ne donnent que la leçon 2",
    exact.join() === "2" && khmerDigit.join() === "2", `${exact.join(", ")} / ${khmerDigit.join(", ")}`);
  const slashed = await search(terms.date.split("-").reverse().join("/"));
  check("recherche par date au format jour/mois/année", slashed.join() === "1", slashed.join(", "));
  check("recherche par thème « salutations »", (await search("salutations")).includes(1));
  check("recherche sans résultat : message affiché",
    (await search("zzzzqqq")).length === 0 && await evaluate(`!document.getElementById("no-result").hidden`));
  await search("");

  /* -------------------------------------------------- Profil et mise en page */
  await open("index.html#profil=km", 390, 844);
  const mobile = await evaluate(`({
    profile: document.documentElement.dataset.profile,
    kmVisible: getComputedStyle(document.querySelector(".tagline .ui-km")).display !== "none",
    frHidden: getComputedStyle(document.querySelector(".tagline .ui-fr")).display === "none",
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
  })`);
  check("profil KH : interface en khmer", mobile.profile === "km" && mobile.kmVisible && mobile.frHidden);
  check("index sur téléphone (390 px) : pas de défilement horizontal", !mobile.overflow);
  await capture("index-profil-km-telephone");

  await open("index.html#profil=en", 390, 844);
  const english = await evaluate(`({
    profile: document.documentElement.dataset.profile,
    lang: document.documentElement.lang,
    enVisible: getComputedStyle(document.querySelector(".tagline .ui-en")).display !== "none",
    others: [".tagline .ui-fr", ".tagline .ui-km"].every((sel) => getComputedStyle(document.querySelector(sel)).display === "none"),
    buttons: [...document.querySelectorAll("[data-profile-choice]")].map((b) => b.textContent.trim()).join(" "),
    pressed: document.querySelector('[data-profile-choice="en"]').getAttribute("aria-pressed"),
  })`);
  check("profil ENG : interface en anglais", english.profile === "en" && english.lang === "en" && english.enVisible && english.others);
  check("trois profils proposés : FR, ENG, KH", english.buttons === "FR ENG KH" && english.pressed === "true", english.buttons);

  /* ----------------------------------------------------------------- Leçon */
  await open("lessons/lesson-001.html#profil=fr");
  const lesson = await evaluate(`(async () => {
    await document.fonts.ready;
    const km = document.querySelector('.lang-km .lang-main');
    const audios = [...document.querySelectorAll("audio")];
    return {
      parts: [...document.querySelectorAll("section.part")].map(s => s.id),
      langs: ["fr", "en", "km"].map(l => document.querySelectorAll("#vocabulary .lang-" + l).length),
      khmerFont: getComputedStyle(km).fontFamily,
      khmerFontLoaded: document.fonts.check('16px "Noto Sans Khmer"', km.textContent),
      khmerText: km.textContent,
      audioCount: audios.length,
      preload: audios.every(a => a.getAttribute("preload") === "none"),
      loadedBeforeClick: audios.filter(a => a.networkState === 2 || a.readyState > 0).length,
      playButtons: document.querySelectorAll(".audio .play").length,
      downloads: document.querySelectorAll("a.audio-download[download]").length,
      nav: [...document.querySelectorAll(".lesson-nav:first-of-type .nav-link")].map(a => a.getAttribute("href")),
      answersClosed: [...document.querySelectorAll("details.answer")].every(d => !d.open),
      questions: document.querySelectorAll(".questions li").length,
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    };
  })()`);
  check("leçon : cinq parties (vocabulaire, expressions, phrases, dialogue, révision)",
    lesson.parts.join(",") === "vocabulary,expressions,sentences,dialogue,review", lesson.parts.join(", "));
  check("leçon : vocabulaire présenté dans les trois langues",
    lesson.langs[0] >= 5 && lesson.langs[0] === lesson.langs[1] && lesson.langs[1] === lesson.langs[2], lesson.langs.join("/"));
  check("khmer : police Noto Sans Khmer embarquée et chargée",
    /Noto Sans Khmer/.test(lesson.khmerFont) && lesson.khmerFontLoaded, lesson.khmerText);
  check("audio : lecteurs présents avec preload=\"none\"", lesson.audioCount > 30 && lesson.preload, `${lesson.audioCount} lecteurs`);
  check("audio : aucun fichier chargé avant un clic", lesson.loadedBeforeClick === 0);
  check("audio : un bouton d'écoute et un lien de téléchargement par fichier",
    lesson.playButtons === lesson.audioCount && lesson.downloads === lesson.audioCount);
  check("révision : trois questions, réponses masquées par défaut", lesson.questions === 3 && lesson.answersClosed);
  check("navigation : précédente, index, suivante", lesson.nav.length === 3 || lesson.nav.length === 2, JSON.stringify(lesson.nav));
  await capture("lecon-1-profil-fr-ordinateur");

  const playback = await evaluate(`(async () => {
    const out = [];
    for (const lang of ["fr", "en", "km"]) {
      const wrapper = document.querySelector("#vocabulary .lang-" + lang + " .audio.is-enhanced");
      const audio = wrapper.querySelector("audio");
      const done = new Promise(resolve => {
        audio.addEventListener("ended", () => resolve("ended"), { once: true });
        audio.addEventListener("error", () => resolve("error"), { once: true });
        wrapper.querySelector("source").addEventListener("error", () => resolve("source-error"), { once: true });
        setTimeout(() => resolve("timeout"), 8000);
      });
      wrapper.querySelector(".play").click();
      const state = await done;
      out.push({ lang, state, duration: audio.duration, src: audio.currentSrc.split("/").slice(-2).join("/") });
    }
    return out;
  })()`);
  for (const item of playback) {
    check(`lecture audio ${item.lang.toUpperCase()} jusqu'au bout`, item.state === "ended" && item.duration > 0.05,
      `${item.src} (${Number(item.duration).toFixed(2)} s, ${item.state})`);
  }

  const links = await evaluate(`(async () => {
    const urls = [...new Set([...document.querySelectorAll("audio source")].map(s => s.src))];
    let broken = [];
    for (const url of urls) {
      const ok = await new Promise(resolve => { const a = new Audio(); a.preload = "metadata";
        a.onloadedmetadata = () => resolve(a.duration > 0); a.onerror = () => resolve(false); a.src = url; });
      if (!ok) broken.push(url.split("/").pop());
    }
    return { total: urls.length, broken };
  })()`);
  check("liens audio : tous les fichiers de la leçon sont lisibles", links.total > 30 && links.broken.length === 0,
    `${links.total} fichiers, ${links.broken.length} illisible(s)`);

  await open("lessons/lesson-001.html#profil=km", 390, 844);
  const phone = await evaluate(`({
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    translitHidden: getComputedStyle(document.querySelector(".translit")).display === "none",
    noteKm: getComputedStyle(document.querySelector(".note.for-km")).display !== "none",
    noteFr: getComputedStyle(document.querySelector(".note.for-fr")).display === "none",
  })`);
  check("leçon sur téléphone : pas de défilement horizontal", !phone.overflow);
  check("profil KH : explications en khmer, translittération masquée", phone.noteKm && phone.noteFr && phone.translitHidden);
  await capture("lecon-1-profil-km-telephone");

  await open("lessons/lesson-001.html#profil=en", 390, 844);
  const enLesson = await evaluate(`({
    noteEn: getComputedStyle(document.querySelector(".note.for-en")).display !== "none",
    noteOthers: [".note.for-fr", ".note.for-km"].every((sel) => getComputedStyle(document.querySelector(sel)).display === "none"),
    translitShown: getComputedStyle(document.querySelector(".translit")).display !== "none",
    prompt: document.querySelector(".prompt.for-en")?.textContent || "",
  })`);
  check("profil ENG : explications en anglais, translittération affichée", enLesson.noteEn && enLesson.noteOthers && enLesson.translitShown);
  check("profil ENG : questions de révision en anglais", /in Khmer and French/.test(enLesson.prompt), enLesson.prompt);
  await capture("lecon-1-profil-en-telephone");

  await open("lessons/lesson-002.html#profil=fr", 390, 844);
  const second = await evaluate(`({
    profile: document.documentElement.dataset.profile,
    prev: document.querySelector(".nav-prev")?.getAttribute("href") || "",
    next: document.querySelector(".nav-next")?.getAttribute("href") || "",
    home: document.querySelector(".nav-home")?.getAttribute("href") || "",
    recall: document.querySelectorAll(".recall").length,
    translitShown: getComputedStyle(document.querySelector(".translit")).display !== "none",
  })`);
  check("leçon 2 : liens vers la leçon précédente, la suivante et l'index",
    /lesson-001\.html/.test(second.prev) && /lesson-003\.html/.test(second.next) && /index\.html/.test(second.home),
    `${second.prev} | ${second.home} | ${second.next}`);
  check("leçon 2 : révision espacée des mots de la veille", second.recall > 0, `${second.recall} mot(s) à revoir`);
  check("profil FR : translittération du khmer affichée", second.translitShown);
  await capture("lecon-2-profil-fr-telephone");

  /* ------------------------------------- Leçon du jour, leçons à venir, jeu de rôle, mode test */
  await open("index.html#profil=fr");
  const dates = await evaluate(`[...document.querySelectorAll(".lesson-card")].map(c => ({ n: Number(c.dataset.number), d: c.dataset.date }))
    .sort((a, b) => a.d < b.d ? -1 : 1)`);
  const pick = dates[Math.min(1, dates.length - 1)];
  await open(`index.html#profil=fr&jour=${pick.d}`);
  const home = await evaluate(`({
    panel: !document.getElementById("today-panel").hidden,
    num: document.getElementById("today-num").textContent,
    visible: [...document.querySelectorAll(".lesson-card")].filter(c => !c.hidden).length,
    toggle: !document.getElementById("future-toggle").hidden,
  })`);
  const past = dates.filter(x => x.d <= pick.d).length;
  check("accueil : leçon du jour mise en avant", home.panel && home.num === String(pick.n), `n° ${home.num}, jour ${pick.d}`);
  check("accueil : leçons à venir masquées", home.visible === past && (past === dates.length || home.toggle),
    `${home.visible} affichée(s) sur ${dates.length}`);

  const extras = await evaluate(`(() => {
    const due = document.getElementById("due-link");
    const size = (value) => document.querySelector('[data-size-choice="' + value + '"]').click();
    size("l");
    const bigger = document.documentElement.getAttribute("data-size") === "l";
    size("xl"); size("");
    return { due: due && !due.hidden ? Number(document.getElementById("due-count").textContent) : 0, bigger,
             reset: !document.documentElement.hasAttribute("data-size"),
             manifest: !!document.querySelector('link[rel="manifest"]') };
  })()`);
  check("accueil : mots à réviser aujourd'hui", extras.due > 0, `${extras.due} mot(s)`);
  check("taille du texte réglable", extras.bigger && extras.reset);
  check("application : manifeste déclaré", extras.manifest);

  await open(`lessons/lesson-${String(pick.n).padStart(3, "0")}.html#profil=fr`);
  const quiz = await evaluate(`(async () => {
    document.getElementById("quiz-toggle").click();
    const text = document.querySelector(".entry .lang-km .lang-text");
    const blurred = getComputedStyle(text).filter.includes("blur");
    text.click();
    const shown = !getComputedStyle(text).filter.includes("blur");
    document.getElementById("quiz-toggle").click();
    return { blurred, shown, off: !document.documentElement.classList.contains("quiz-mode") };
  })()`);
  check("leçon : mode test (khmer flouté, révélé d'un clic)", quiz.blurred && quiz.shown && quiz.off, JSON.stringify(quiz));
  const role = await evaluate(`(async () => {
    const lines = [...document.querySelectorAll(".dialogue .line")];
    const who = lines[0].classList.contains("speaker-a") ? "a" : "b";
    document.querySelector('[data-role="' + who + '"]').click();
    await new Promise(r => setTimeout(r, 300));
    const first = lines[0];
    const masked = first.getAttribute("data-mask") === "km" && first.classList.contains("is-yourturn");
    const hidden = getComputedStyle(first.querySelector(".lang-km .lang-text")).filter.includes("blur");
    document.getElementById("rp-continue").click();
    const unmasked = !first.hasAttribute("data-mask");
    document.getElementById("rp-stop").click();
    return { masked, hidden, unmasked, bar: document.getElementById("roleplay-bar").hidden };
  })()`);
  check("dialogue : jeu de rôle (réplique masquée, puis révélée)", role.masked && role.hidden && role.unmasked && role.bar,
    JSON.stringify(role));
  const reviewLink = await evaluate(`document.querySelector(".review-this-link")?.getAttribute("href") || ""`);
  check("leçon : lien « Réviser les mots de cette leçon »", new RegExp("revision\\.html#lecon=" + pick.n).test(reviewLink), reviewLink);

  /* ---------------------------------------------------------------- Réviser, Lexique, Alphabets */
  const lastDate = dates[dates.length - 1].d;
  await open(`revision.html#profil=fr&jour=${lastDate}`);
  const flash = await evaluate(`(async () => {
    const app = document.getElementById("review-app");
    const start = !!app.querySelector(".flashcard .fc-prompt");
    app.querySelector('[data-value="listen"]').click();
    await new Promise(r => setTimeout(r, 100));
    const choices = app.querySelectorAll(".fc-choice").length;
    app.querySelector(".fc-choice").click();
    const verdict = !!app.querySelector(".fc-verdict");
    app.querySelector('[data-value="recognize"]').click();
    return { start, choices, verdict };
  })()`);
  check("réviser : carte, puis écoute avec 4 choix et correction", flash.start && flash.choices === 4 && flash.verdict, JSON.stringify(flash));
  await open(`revision.html#lecon=${pick.n}&profil=fr`);
  const scoped = await evaluate(`document.querySelector('[data-set="scope"].is-active')?.dataset.value || ""`);
  check("réviser : lien depuis une leçon limité à cette leçon", scoped === "lesson", scoped);
  const writing = await evaluate(`(async () => {
    const app = document.getElementById("review-app");
    const cards = JSON.parse(document.getElementById("review-data").textContent);
    app.querySelector('[data-set="studied"][data-value="en"]').click();
    app.querySelector('[data-value="write"]').click();
    const submit = (text) => { const i = document.getElementById("fc-input"); i.value = text;
      app.querySelector("form[data-write]").dispatchEvent(new Event("submit", { cancelable: true, bubbles: true })); };
    submit("zzzz");
    const wrong = !!app.querySelector(".fc-writing.is-wrong");
    app.querySelector('[data-action="next"]').click();
    const prompt = app.querySelector(".fc-prompt").textContent;
    const card = cards.find(c => c.fr === prompt);
    submit(card ? card.en.toUpperCase() : "?");
    const right = !!app.querySelector(".fc-writing.is-right, .fc-writing.is-almost");
    app.querySelector('[data-set="studied"][data-value="km"]').click();
    return { wrong, right, noKhmerWriting: !app.querySelector('[data-value="write"]') };
  })()`);
  check("réviser : écrire le mot (erreur, puis bonne réponse ; pas pour le khmer)",
    writing.wrong && writing.right && writing.noKhmerWriting, JSON.stringify(writing));

  await open(`lexique.html#profil=fr&jour=${pick.d}`);
  const lexicon = await evaluate(`(() => {
    const all = document.querySelectorAll(".lex-item").length;
    const i = document.getElementById("lex-search"); i.value = ${JSON.stringify(terms.fr)};
    i.dispatchEvent(new Event("input", { bubbles: true }));
    const found = [...document.querySelectorAll(".lex-item")].filter(x => !x.hidden).length;
    return { all, found, overflow: document.documentElement.scrollWidth > window.innerWidth + 1 };
  })()`);
  check("lexique : mots des leçons passées seulement, recherche", lexicon.all > 0 && lexicon.found >= 1 && !lexicon.overflow,
    `${lexicon.all} entrée(s), « ${terms.fr} » → ${lexicon.found}`);

  // Sélecteur « Langues » : décocher le chinois le masque partout, et le choix est gardé d'une page à l'autre.
  await open("lessons/lesson-001.html#profil=fr");
  const langs = await evaluate(`(() => {
    const visible = l => [...document.querySelectorAll(".entry .lang-" + l)].filter(x => x.offsetParent !== null).length;
    const box = document.querySelector('[data-lang-toggle="zh"]');
    const before = { zh: visible("zh"), ru: visible("ru"), boxes: document.querySelectorAll("[data-lang-toggle]").length };
    box.click();
    return { before, after: { zh: visible("zh"), ru: visible("ru") }, cls: document.documentElement.classList.contains("hide-zh") };
  })()`);
  check("langues : sept langues proposées, le chinois se masque d'un clic",
    langs.before.boxes === 7 && langs.before.zh > 0 && langs.after.zh === 0 && langs.after.ru === langs.before.ru && langs.cls,
    JSON.stringify(langs));
  await open("lessons/lesson-002.html#profil=fr");
  const kept = await evaluate(`(() => {
    const zh = [...document.querySelectorAll(".entry .lang-zh")].filter(x => x.offsetParent !== null).length;
    const box = document.querySelector('[data-lang-toggle="zh"]');
    const unchecked = !box.checked;
    box.click();
    return { zh, unchecked, back: [...document.querySelectorAll(".entry .lang-zh")].filter(x => x.offsetParent !== null).length };
  })()`);
  check("langues : choix gardé sur la page suivante, puis rétabli", kept.zh === 0 && kept.unchecked && kept.back > 0,
    JSON.stringify(kept));
  if (existsSync(join(site, "alphabet.html"))) {     // page présente seulement avec content/alphabets.json
    await open("alphabet.html#profil=km", 390, 844);
    const alpha = await evaluate(`({ cards: document.querySelectorAll(".glyph-card").length,
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1 })`);
    check("alphabets : cartes affichées, pas de défilement horizontal sur téléphone", alpha.cards >= 100 && !alpha.overflow,
      `${alpha.cards} cartes`);
  }

  /* Traduire : rien n'est envoyé au chargement (le réseau ne sert qu'une fois du texte saisi). */
  await open("traduction.html#profil=km", 390, 844);
  const translate = await evaluate(`(() => {
    try { localStorage.removeItem("frkh-translate-langs"); } catch (e) {}
    return null;
  })()`);
  await open("traduction.html#profil=km", 390, 844);
  const tr = await evaluate(`(() => {
    const from = document.getElementById("tr-from"), to = document.getElementById("tr-to");
    const first = { from: from.value, to: to.value, options: from.options.length };
    document.getElementById("tr-swap").click();
    const swapped = { from: from.value, to: to.value };
    to.value = from.value; to.dispatchEvent(new Event("change"));
    const same = { from: from.value, to: to.value };
    return { first, swapped, same, tab: !!document.querySelector(".tab-translate"),
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1 };
  })()`);
  check("traduire : khmer → français par défaut, inversion, jamais deux fois la même langue",
    translate === null && tr.first.from === "km" && tr.first.to === "fr" && tr.first.options === 7 &&
    tr.swapped.from === "fr" && tr.swapped.to === "km" && tr.same.from !== tr.same.to && tr.tab && !tr.overflow,
    JSON.stringify(tr));

  const external = requests.filter((url) => !url.startsWith("file:") && !url.startsWith("about:") && !url.startsWith("data:") && !url.startsWith("blob:"));
  check("hors connexion : aucune requête réseau émise par le site", external.length === 0, external.slice(0, 3).join(", "));
  check("aucune erreur JavaScript", pageErrors.length === 0, pageErrors.slice(0, 3).join(" | "));
} catch (error) {
  check("exécution du contrôle navigateur", false, String(error.message || error));
}

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed} contrôle(s) réussi(s), ${failed} échec(s).`);
try { await send("browser.close", {}); } catch { /* le navigateur est fermé de toute façon */ }
cleanup(failed ? 1 : 0);
