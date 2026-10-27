/* SUNO teacher web app. Vanilla JS, no build step: loads fast on a cheap phone.
   One language at a time (हिंदी or English, switch in the header). Children's names, lesson words
   and the teacher's own words stay as they are: they are the data. */
"use strict";

const S = { me: null, tab: "today", today: null, area: "hindi", online: navigator.onLine, polling: {}, lang: initialLang() };
const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const t = (hi, en) => (S.lang === "hi" ? hi : en);

function initialLang() {
  const saved = localStorage.getItem("suno_lang");
  if (saved === "hi" || saved === "en") return saved;
  return (navigator.language || "").toLowerCase().startsWith("hi") ? "hi" : "en";
}
function setLang(l) {
  S.lang = l; localStorage.setItem("suno_lang", l);
  document.documentElement.lang = l;
  document.body.classList.toggle("lang-hi", l === "hi");
}

const REASON = {
  confirm: ["पक्का करना है", "Confirm what you noted"],
  not_heard: ["हफ़्ते भर से नहीं सुना", "Not heard this week"],
  needs_support: ["शायद मदद चाहिए", "May need support"],
  least_known: ["कम जानकारी", "Least known"],
};
const STATUS = {
  evidence: ["पक्का सबूत", "Evidence"],
  check_tomorrow: ["कल फिर सुनें", "Check again"],
  absent: ["अनुपस्थित", "Absent"],
  unattributed: ["कौन? बताइए", "Who was it?"],
  dismissed: ["छोड़ दिया", "Skipped"],
};
const OUTCOME = { correct: ["✓ सही", "✓ correct"], incorrect: ["✗ गलत", "✗ wrong"], partial: ["◐ आधा", "◐ partly"], unclear: ["? साफ़ नहीं", "? unclear"] };
const CELL = { "needs support": [["मदद चाहिए", "Needs support"], "ns"], "on track": [["ठीक", "On track"], "ok"], "not enough evidence": [["—", "—"], "ne"] };
const outcome = (o) => (OUTCOME[o] ? t(...OUTCOME[o]) : "");

// ---------- api ----------
async function api(path, opts = {}) {
  const o = { credentials: "same-origin", ...opts };
  if (o.json) { o.body = JSON.stringify(o.json); o.headers = { "Content-Type": "application/json" }; delete o.json; }
  const r = await fetch(path, o);
  let data = null;
  try { data = await r.json(); } catch (_) {}
  if (r.status === 503 && data && data.error === "offline") throw new Error("offline"); // from the service worker
  if (!r.ok) { const e = new Error((data && data.error) || r.statusText); e.status = r.status; throw e; }
  return data;
}
function toast(msg, ms = 2600) {
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = msg; document.body.appendChild(el);
  setTimeout(() => el.remove(), ms);
}
const clearCached = async () => {
  ["suno_me", "suno_today", "suno_class"].forEach((k) => localStorage.removeItem(k));
  if (window.caches) await caches.delete("suno-api-v1");
  S.today = null;
};

// ---------- roster and skills ----------
const kid = (id) => (S.me?.roster || []).find((c) => c.child_id === id);
function nameOf(id) {
  const c = kid(id); if (!c) return id || "?";
  const dup = S.me.roster.filter((x) => x.first_name === c.first_name).length > 1;
  return dup ? `${c.first_name} (${c.roll_no})` : c.first_name;
}
const nm = (id) => `<span class="deva">${esc(nameOf(id))}</span>`;
const skillOf = (code) => (S.me?.skills.skills || []).find((s) => s.code === code);
const skillName = (code) => { const s = skillOf(code); return s ? t(s.label_hi, s.label_en) : code || ""; };
const areaOf = (a) => S.me.skills.areas.find((x) => x.area === a);
const levelName = (area, i) => { const l = areaOf(area).levels[i]; return t(l.label_hi, l.label_en); };
const initial = (id) => (kid(id)?.first_name || "?").slice(0, 1);
function fmtDay(iso) {
  try { return new Date(iso + "T00:00:00").toLocaleDateString(S.lang === "hi" ? "hi-IN" : "en-IN", { weekday: "long", day: "numeric", month: "long" }); }
  catch (_) { return iso; }
}
const langSwitch = () => `<div class="langswitch" role="group" aria-label="language">
  <button data-lang="hi" class="${S.lang === "hi" ? "on" : ""}">हिं</button><button data-lang="en" class="${S.lang === "en" ? "on" : ""}">EN</button></div>`;
function wireLang(root, rerender) {
  root.querySelectorAll("[data-lang]").forEach((b) => (b.onclick = () => { localStorage.setItem("suno_lang_chosen", "1"); setLang(b.dataset.lang); rerender(); }));
}

// ---------- offline queue (IndexedDB) ----------
function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open("suno", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("queue", { keyPath: "id", autoIncrement: true });
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
}
async function qAll() { const d = await idb(); return new Promise((res) => { const x = d.transaction("queue").objectStore("queue").getAll(); x.onsuccess = () => res(x.result || []); }); }
async function qAdd(item) { const d = await idb(); return new Promise((res) => { const x = d.transaction("queue", "readwrite").objectStore("queue").add(item); x.onsuccess = () => res(x.result); }); }
async function qDel(id) { const d = await idb(); return new Promise((res) => { const x = d.transaction("queue", "readwrite").objectStore("queue").delete(id); x.onsuccess = () => res(); }); }

async function flushQueue() {
  if (!navigator.onLine || !S.me) return;
  for (const it of await qAll()) {
    try {
      const { note_id } = await postNote(it);
      await qDel(it.id);
      toast(t("फ़ोन में रखा नोट भेज दिया", "A note saved offline was sent"));
      pollNote(note_id);
    } catch (e) { if (!e.status) break; if (e.status >= 400 && e.status < 500) await qDel(it.id); }
  }
  renderQueueBadge();
}
async function renderQueueBadge() {
  const n = (await qAll()).length, el = $("#qcount");
  if (el) el.innerHTML = n ? `<div class="card flat small">📥 ${t(`${n} नोट फ़ोन में रखे हैं; नेटवर्क आने पर अपने आप जाएँगे।`, `${n} note(s) saved on this phone; they send when you are back online.`)}</div>` : "";
}
function postNote(it) {
  const fd = new FormData();
  if (it.blob) fd.append("audio", it.blob, it.filename || "note.webm");
  if (it.text) fd.append("text", it.text);
  if (it.day) fd.append("day", it.day);
  return api("/api/notes", { method: "POST", body: fd });
}

// ---------- boot ----------
window.addEventListener("online", () => { S.online = true; renderOffline(); flushQueue(); });
window.addEventListener("offline", () => { S.online = false; renderOffline(); });
if ("serviceWorker" in navigator) {
  // When a new version takes over (after a deploy), reload once so the page never mixes versions.
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (hadController && !reloaded) { reloaded = true; location.reload(); }
  });
  navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).then((r) => r.update()).catch(() => {});
}
setLang(S.lang);

window.addEventListener("hashchange", () => route());
function route() {
  if (location.hash === "#evidence") return renderEvidence();
  if (location.hash === "#privacy") return renderPrivacy();
  return boot();
}
const pageBack = () => { history.pushState("", document.title, location.pathname); boot(); };

async function boot() {
  try {
    S.me = await api("/api/me");
    localStorage.setItem("suno_me", JSON.stringify(S.me));
    shell();
  } catch (e) {
    if (!e.status && localStorage.getItem("suno_me")) { S.me = JSON.parse(localStorage.getItem("suno_me")); shell(); return; }
    renderLanding();
  }
}

// ---------- landing / sign-in ----------
function renderLanding(err = "") {
  $("#app").innerHTML = `
  <div class="landing">
    <section class="story">
      <div class="brand"><div class="brandmark">स</div><div class="wordmark">SUNO<span class="deva">सुनो</span></div><div class="spacer"></div>${langSwitch()}</div>
      <h1>${t("बच्चे को शिक्षक पहले से सुनती हैं।<br><em>SUNO याद रखता है।</em>", "The teacher already hears every child.<br><em>SUNO remembers.</em>")}</h1>
      <p class="lede">${t("कक्षा 1–3 के सरकारी स्कूल के शिक्षकों के लिए: कक्षा के बाद 60 सेकंड का वॉइस नोट, और अगली सुबह 2 मिनट का हिंदी सार: किसे किस चीज़ में मदद चाहिए, आज क्या करें, और आज किन बच्चों को सुनें।",
        "For Grade 1–3 government-school teachers in India: a 60-second voice note after class becomes, by next morning, a 2-minute Hindi brief on who needs help with what, what to do today, and which children to listen to.")}</p>
      <div class="steps3">
        <div class="step"><div class="n">1</div><div><b>${t("शिक्षक बोलती हैं", "She speaks")}</b><span>${t("अपनी भाषा में: किसने क्या पढ़ा, कहाँ अटका।", "In her own words: who read what, where they got stuck.")}</span></div></div>
        <div class="step"><div class="n">2</div><div><b>${t("Claude समझता है, कोड जाँचता है", "Claude reads it, code checks it")}</b><span>${t("हर बात सही बच्चे से जुड़ी, राय कभी सबूत नहीं बनती।", "Every claim tied to the right child; opinions never become evidence.")}</span></div></div>
        <div class="step"><div class="n">3</div><div><b>${t("सुबह का सार", "The morning brief")}</b><span>${t("स्तर के हिसाब से समूह, 10 मिनट की गतिविधि, आज किसे सुनें।", "Groups by level, a 10-minute activity, whom to listen to today.")}</span></div></div>
      </div>
      <div class="proof">
        <div><b id="pf-wrong">0</b><span>${t("सबूत गलत बच्चे पर", "evidence records about the wrong child")}</span></div>
        <div><b id="pf-quiet">–</b><span id="pf-quiet-t">${t("सबसे शांत बच्चे दूसरे हफ़्ते तक सुने गए", "of the quietest children heard by week 2")}</span></div>
        <div><b id="pf-found">–</b><span>${t("मदद चाहने वाले बच्चे 8 हफ़्ते में मिले, एक पूरी डायरी की तुलना में", "the children who need support found by week 8, vs a perfect diary")}</span></div>
      </div>
      <div class="proof-note">${t("सिमुलेशन के नतीजे (असली बच्चे नहीं): eval/results/ में स्क्रिप्ट और मान्यताएँ।", "Simulated results, not real children: scripts and assumptions in eval/results/.")}</div>
      <div style="display:flex;gap:16px;margin-top:14px;flex-wrap:wrap"><a href="#evidence" style="color:var(--accent);font-weight:700">${t("हमने SUNO को कैसे परखा →", "How we tested SUNO →")}</a><a href="#privacy" style="color:#c9cfee">${t("निजता", "Privacy")}</a></div>
      <div class="badges"><span>🔇 ${t("किसी बच्चे की आवाज़ रिकॉर्ड नहीं", "No child's voice recorded")}</span><span>🚫 ${t("कोई टेस्ट नहीं", "No tests")}</span><span>🙅 ${t("शिक्षक का कोई स्कोर नहीं", "No teacher score")}</span><span>📶 ${t("ऑफ़लाइन चलता है", "Works offline")}</span></div>
    </section>
    <section class="signin"><div class="box">
      <h2>${t("SUNO आज़माएँ", "Try SUNO")}</h2>
      <p class="small muted" style="margin-top:0">${t("डेमो कक्षा: 30 काल्पनिक बच्चे, आठ दिन के नोट, और आज सुबह का सार। हर बार नई कॉपी खुलती है।", "A demo Grade 2 class: 30 fictional children, eight days of teacher notes, and this morning's brief. Every visit opens a fresh copy.")}</p>
      <button class="btn warn block lg" id="demo">▶ ${t("डेमो खोलें", "Open the demo")}</button>
      <div class="or">${t("या", "or")}</div>
      <label class="lbl" for="code">${t("अपनी कक्षा का कोड", "Your class code")}</label>
      <input id="code" type="text" autocomplete="off" autocapitalize="characters" placeholder="K7Q2-M9XD">
      <button class="btn block" id="go" style="margin-top:8px">${t("कक्षा खोलें", "Open my class")}</button>
      <div class="err">${esc(err)}</div>
      <details class="card flat" style="margin-top:6px"><summary><b>${t("नई कक्षा बनाएँ", "Create a new class")}</b></summary>
        <div style="margin-top:10px">
          <input id="cname" type="text" placeholder="${t("कक्षा का नाम, जैसे: कक्षा 2-अ", "Class name, e.g. Class 2-A")}">
          <select id="cgrade" style="margin-top:8px"><option value="1">${t("कक्षा 1", "Grade 1")}</option><option value="2" selected>${t("कक्षा 2", "Grade 2")}</option><option value="3">${t("कक्षा 3", "Grade 3")}</option></select>
          <button class="btn alt block" id="create" style="margin-top:8px">${t("कक्षा बनाएँ", "Create class")}</button>
          <p class="tiny">${t("अगले कदम में बच्चों के नाम: रजिस्टर की फ़ोटो से या लिखकर।", "Next you add the children: from a photo of the attendance register, or by typing.")}</p>
        </div>
      </details>
    </div></section>
  </div>`;
  wireLang($("#app"), () => renderLanding(err));
  // Headline numbers come from the evaluation results, never typed in by hand.
  api("/api/evidence").then((e) => {
    if (e.pipeline) $("#pf-wrong") && ($("#pf-wrong").textContent = `${e.pipeline.wrong_child_evidence} / ${e.pipeline.evidence}`);
    const a = (arm, wk, m) => e.term && e.term.arms[arm] && e.term.arms[arm][wk] ? e.term.arms[arm][wk][m] : null;
    const q = a("list_80", "2", "quiet_with_evidence"), q0 = a("no_list", "2", "quiet_with_evidence");
    if (q != null && $("#pf-quiet")) {
      $("#pf-quiet").textContent = `${Math.round(100 * q)}%`;
      $("#pf-quiet-t").textContent = t(`सबसे शांत बच्चे दूसरे हफ़्ते तक सुने गए (SUNO की सूची के बिना ${Math.round(100 * q0)}%)`, `of the quietest children heard by week 2 (${Math.round(100 * q0)}% without SUNO's list)`);
    }
    const f = a("list_80", "8", "children_found"), f0 = a("no_list", "8", "children_found");
    if (f != null && f0 && $("#pf-found")) $("#pf-found").textContent = `${(f / f0).toFixed(1)}×`;
  }).catch(() => {});
  const open = async (code, btn) => {
    btn.disabled = true;
    try { await api("/api/login", { method: "POST", json: { code } }); await clearCached(); await boot(); }
    catch (e) { renderLanding(e.status === 401 ? t("यह कोड नहीं मिला", "That code wasn't found") : t("नेटवर्क नहीं है", "No network")); }
  };
  $("#demo").onclick = () => open("SUNO-DEMO", $("#demo"));
  $("#go").onclick = () => { const c = $("#code").value.trim(); if (c) open(c, $("#go")); };
  $("#code").onkeydown = (e) => { if (e.key === "Enter") $("#go").click(); };
  $("#create").onclick = async () => {
    try {
      const r = await api("/api/classes", { method: "POST", json: { name: $("#cname").value || t("मेरी कक्षा", "My class"), grade: +$("#cgrade").value } });
      await clearCached();
      if (!localStorage.getItem("suno_lang_chosen")) setLang("hi");
      alert(t(`आपकी कक्षा का कोड: ${r.code}\n\nइसे लिखकर रखें: किसी भी फ़ोन पर इसी कोड से आपकी कक्षा खुलेगी।`, `Your class code: ${r.code}\n\nWrite it down: it opens your class on any phone.`));
      await boot();
    } catch (e) { toast(e.message); }
  };
}

// ---------- shell ----------
function shell() {
  $("#app").innerHTML = `
  <header class="top"><div class="row">
    <div class="brandmark" style="width:32px;height:32px;border-radius:9px">स</div>
    <div class="cls"><b class="deva">${esc(S.me.name)}</b><span id="hdate"></span></div>
    <div class="spacer"></div>
    ${S.me.synthetic ? `<span class="chip-syn" title="${t("काल्पनिक डेमो डेटा", "Synthetic demo data: fictional children")}">${t("डेमो", "DEMO · SYNTHETIC")}</span>` : ""}
    ${langSwitch()}
    <button class="iconbtn" id="menu" aria-label="menu">☰</button>
  </div></header>
  <div id="offline"></div>
  <div class="layout">
    <nav class="tabs">
      <button data-t="today"><span class="ic">☀️</span><span>${t("आज", "Today")}</span></button>
      <button data-t="speak"><span class="ic">🎙️</span><span>${t("नोट बोलें", "Speak a note")}</span></button>
      <button data-t="class"><span class="ic">👧🏽</span><span>${t("कक्षा", "Class")}</span></button>
      <button data-t="notes"><span class="ic">🗂️</span><span>${t("नोट्स", "Notes")}</span></button>
    </nav>
    <main class="view" id="view"></main>
  </div>`;
  document.querySelectorAll("nav.tabs button").forEach((b) => (b.onclick = () => go(b.dataset.t)));
  wireLang($("header.top"), shell);
  $("#menu").onclick = openMenu;
  renderOffline();
  go(S.tab);
  flushQueue();
}
function renderOffline() {
  const el = $("#offline"); if (!el) return;
  el.innerHTML = S.online ? "" : `<div class="offline-bar">${t("ऑफ़लाइन: पिछला सार और रिकॉर्डिंग चलती रहेगी।", "Offline: the last brief and recording still work.")}</div>`;
}
function go(tab) {
  S.tab = tab;
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === tab));
  Object.values(S.polling).forEach(clearTimeout); S.polling = {};
  ({ today: renderToday, speak: renderSpeak, class: renderClass, notes: renderNotes })[tab]();
  window.scrollTo(0, 0);
}

// ---------- menu, how it works ----------
function openMenu() {
  sheet(`
    <h2 class="deva">${esc(S.me.name)}</h2>
    ${S.me.code ? `<div class="card flat"><div class="tiny">${t("कक्षा कोड: किसी भी फ़ोन पर आपकी कक्षा खोलता है", "Class code: opens your class on any phone")}</div><div style="font-size:24px;font-weight:800;letter-spacing:2px">${esc(S.me.code)}</div></div>` : ""}
    ${S.me.synthetic ? `<p class="small muted">${t("यह डेमो कक्षा है: सारे बच्चे और नोट काल्पनिक हैं, और असली पाइपलाइन से गुज़रे हैं।", "This is a demo class: every child and note is synthetic, and was run through the real pipeline.")}</p>` : ""}
    <div class="menu-list">
      <button class="btn alt block" id="m-roster">👧🏽 ${t(`बच्चों की सूची (${S.me.roster.length})`, `Children (${S.me.roster.length})`)}</button>
      <button class="btn alt block" id="m-lesson">📖 ${t("इस हफ़्ते का पाठ", "This week's lesson")}</button>
      <button class="btn alt block" id="m-howto">❓ ${t("SUNO कैसे काम करता है", "How SUNO works")}</button>
      <a class="btn alt block" href="/api/export/class.csv">⬇️ ${t("कक्षा की सूची (CSV) डाउनलोड करें", "Download class list (CSV)")}</a>
      <a class="btn alt block" href="#evidence">📊 ${t("हमने SUNO को कैसे परखा", "Evidence: how we tested SUNO")}</a>
      <a class="btn alt block" href="#privacy">🔒 ${t("निजता और डेटा", "Privacy and your data")}</a>
      <button class="btn alt block" id="m-out">${t("बाहर निकलें", "Sign out")}</button>
    </div>`);
  $("#m-roster").onclick = () => openRoster();
  $("#m-lesson").onclick = openLesson;
  $("#m-howto").onclick = () => sheet(howTo());
  document.querySelectorAll('#sheet a[href^="#"]').forEach((a) => (a.onclick = () => closeSheet()));
  $("#m-out").onclick = async () => { try { await api("/api/logout", { method: "POST" }); } catch (_) {} await clearCached(); closeSheet(); renderLanding(); };
}
const howTo = () => `
<h2>${t("SUNO कैसे काम करता है", "How SUNO works")}</h2>
<ol class="small">
<li>${t("<b>सुबह:</b> 2 मिनट का हिंदी सार, और आज किन 5 बच्चों को सुनना है, हर एक से दो शब्द।", "<b>Morning:</b> a 2-minute Hindi brief, and 5 children to listen to today, two words each.")}</li>
<li>${t("<b>कक्षा में:</b> आप वैसे ही पढ़ाएँ। फ़ोन बैग में रहे। कोई रिकॉर्डिंग नहीं।", "<b>In class:</b> teach as usual. Nothing records the classroom; no child's voice is captured.")}</li>
<li>${t("<b>कक्षा के बाद:</b> 60 सेकंड का वॉइस नोट: किसने क्या पढ़ा, कहाँ अटका, कौन नहीं आया।", "<b>After class:</b> a 60-second voice note in her own words: who read what, where they got stuck, who was absent.")}</li>
<li>${t("<b>SUNO:</b> Sarvam आवाज़ को लिखता है; Claude हर बच्चे की बात अलग करता है; कोड नाम, शब्द और भरोसा जाँचता है। राय कभी सबूत नहीं बनती।", "<b>SUNO:</b> Sarvam transcribes; Claude splits the note into per-child observations; code checks every name against the roster and every word against her transcript, and computes confidence. Opinions (\"he is good\", \"she is weak\") never become evidence; they become \"listen again tomorrow\".")}</li>
<li>${t("<b>स्तर:</b> हर बच्चे की सीढ़ी पर जगह (अक्षर → शब्द → मात्रा → वाक्य → कहानी)। तीन या ज़्यादा बातों और दो दिनों के बाद ही नाम आता है।", "<b>Levels:</b> each child's rung on the ladder (letters → words → vowel signs → sentences → story), as in ASER and Teaching at the Right Level. A child is named only after 3+ checked observations over 2+ days.")}</li>
</ol>
<p class="tiny">${t("शिक्षक का कोई स्कोर नहीं। सिर्फ़ आप देखती हैं। वॉइस नोट लिखने के बाद मिटा दिया जाता है।", "There is no teacher score. Only the teacher sees this. Voice notes are deleted after transcription.")}</p>`;

// ---------- sheet ----------
function sheet(html) {
  closeSheet();
  const bg = document.createElement("div");
  bg.className = "sheet-bg"; bg.id = "sheet";
  bg.innerHTML = `<div class="sheet"><button class="close" aria-label="close">×</button>${html}</div>`;
  bg.onclick = (e) => { if (e.target === bg) closeSheet(); };
  document.body.appendChild(bg);
  $(".close", bg).onclick = closeSheet;
  return $(".sheet", bg);
}
function closeSheet() { $("#sheet")?.remove(); }

// ---------- TODAY ----------
async function loadToday() {
  try {
    S.today = await api("/api/today");
    localStorage.setItem("suno_today", JSON.stringify(S.today));
  } catch (e) {
    if (e.status === 401) { renderLanding(); return null; }
    S.today = JSON.parse(localStorage.getItem("suno_today") || "null");
  }
  return S.today;
}

async function renderToday() {
  const v = $("#view");
  if (!S.today) v.innerHTML = `<div class="loading"><span class="spin"></span></div>`;
  const d = await loadToday();
  if (S.tab !== "today" || !d) return;
  $("#hdate").textContent = fmtDay(d.today);
  const b = d.brief;
  if (!S.me.synthetic && !S.me.roster.length) {
    v.innerHTML = `<div class="narrow"><div class="card onboard" style="margin-top:16px"><h3>${t("नमस्ते! पहले बच्चों के नाम जोड़ें।", "Welcome! First, add your children.")}</h3>
      <p class="small">${t("रजिस्टर के पन्ने की फ़ोटो लीजिए, SUNO नाम पढ़ लेगा; या नाम लिख दीजिए।", "Take a photo of your attendance register page and SUNO reads the names, or type them.")}</p>
      <button class="btn warn block" id="ob-roster">👧🏽 ${t("बच्चों के नाम जोड़ें", "Add children")}</button></div></div>`;
    $("#ob-roster").onclick = () => openRoster();
    return;
  }
  const fresh = !S.me.synthetic && !d.heard_this_week.length && !d.notes_today.length;
  v.innerHTML = `
    ${fresh ? `<div class="card onboard" style="margin-top:12px"><h3>${t("SUNO ऐसे चलता है", "How to start")}</h3>
      <ol class="small"><li>${t("नीचे दिए 5 बच्चों को आज पढ़ते समय ध्यान से सुनिए, हर एक से दो शब्द।", "Today, listen to the 5 children below as they read: two words each.")}</li>
      <li>${t("कक्षा के बाद “नोट बोलें” दबाकर 1 मिनट बताइए: किसने क्या पढ़ा, कहाँ अटका, कौन नहीं आया।", "After class, tap “Speak a note” and talk for a minute: who read what, where they got stuck, who was absent.")}</li>
      <li>${t("कल सुबह 2 मिनट का सार सुनिए।", "Tomorrow morning, listen to the 2-minute brief.")}</li></ol>
      <button class="linkbtn" id="ob-lesson">${t("पहले इस हफ़्ते के पाठ के शब्द देख लें →", "First check this week's lesson words →")}</button></div>` : ""}
    <div class="cols">
      <div>
        ${briefCard(b, d)}
        ${d.open_questions ? `<div class="card q-card alert">❓ <div style="flex:1">${t(`${d.open_questions} नाम साफ़ नहीं थे; एक टैप में बताइए।`, `${d.open_questions} name(s) in your notes need one tap.`)}</div><button class="btn alt" id="to-notes">${t("देखें", "Open")}</button></div>` : ""}
        ${S.me.synthetic ? `<div class="card flat">
          <h3>${t("डेमो: अगली सुबह", "Demo: jump to the next morning")}</h3>
          <p class="small muted" style="margin:0 0 10px">${t("नोट भेजने के बाद घड़ी अगले स्कूल दिन पर ले जाइए; SUNO उस सुबह का सार बनाएगा (लगभग 30 सेकंड)।", "After you send a note, move this demo class to the next school morning. SUNO builds that morning's brief live, including your note (about 30 s).")}</p>
          <button class="btn alt block" id="nextday">${t("अगली सुबह →", "Next morning →")}</button></div>` : ""}
      </div>
      <div>
        <h2 class="sec">${t("आज इन्हें सुनिए", "Listen to these children today")}<span class="tiny">${t("कोड ने चुना", "chosen by code")}</span></h2>
        <div class="card">${d.listen_today.length ? d.listen_today.map(listenRow).join("") : `<p class="muted">${t("सब बच्चों के बारे में ताज़ा जानकारी है।", "Everyone has recent evidence.")}</p>`}
          <p class="tiny" style="margin:10px 0 0">${t("पहले वे बातें जो पक्की करनी हैं, फिर जिनके बारे में SUNO सबसे कम जानता है। हर बच्चे से दो शब्द: एक उसके स्तर का, एक सीढ़ी पर ऊपर या नीचे।", "First anything to confirm, then the children SUNO knows least about. Two words each: one at the child's likely level, one a rung up or down.")}</p>
        </div>
        <button class="btn warn block lg" id="to-speak">🎙️ ${t("कक्षा के बाद नोट बोलें", "After class: speak today's note")}</button>
        ${d.language_flags.length ? `<h2 class="sec">${t("घर की भाषा", "Home language")}</h2><div class="card small">${d.language_flags.map((f) => `<div>🗣️ <b>${nm(f.child_id)}</b>: ${f.signal === "helped" ? t("घर की भाषा में समझाने पर समझ गया/गई: दिक्कत भाषा की हो सकती है, समझ की नहीं।", "understood once it was explained in the home language: the gap may be the language, not the concept.") : t("पढ़ाई की भाषा समझने में दिक्कत।", "the language of instruction is a barrier.")}</div>`).join("")}</div>` : ""}
        <h2 class="sec">${t("5 दिन से अलग से नहीं सुना", "Not described for 5 school days")}<span class="tiny">${t("चुप्पी की सूची", "Silence Ledger")}</span></h2>
        <div class="chips">${d.silent.length ? d.silent.map((c) => `<span>${esc(nameOf(c))}</span>`).join("") : `<span>${t("कोई नहीं", "Nobody")}</span>`}</div>
      </div>
    </div>`;
  $("#to-speak").onclick = () => go("speak");
  $("#ob-lesson") && ($("#ob-lesson").onclick = openLesson);
  $("#to-notes") && ($("#to-notes").onclick = () => go("notes"));
  $("#nextday") && ($("#nextday").onclick = async () => {
    $("#nextday").disabled = true;
    try { await api("/api/next-day", { method: "POST" }); S.me.day_offset++; S.today = null; renderToday(); } catch (e) { toast(e.message); $("#nextday").disabled = false; }
  });
  document.querySelectorAll("[data-mkbrief]").forEach((x) => (x.onclick = async () => { try { await api("/api/brief" + (b ? "?force=true" : ""), { method: "POST" }); renderToday(); } catch (e) { toast(e.message); } }));
  wirePlayer();
  if (b && ["queued", "thinking", "speaking"].includes(b.status)) S.polling.today = setTimeout(renderToday, 2500);
}

function briefCard(b, d) {
  const head = `<div class="kicker">${t("सुबह का सार", "Morning brief")}</div><h3>${fmtDay(d.today)}</h3>`;
  if (!b) return `<div class="card brief">${head}
      <p class="summary">${t("अभी सार नहीं बना है।", "There is no brief for this morning yet.")}</p>
      <button class="btn warn" data-mkbrief>${t("सार बनाइए", "Build this morning's brief")}</button></div>`;
  if (["queued", "thinking", "speaking"].includes(b.status)) {
    const step = { queued: t("शुरू हो रहा है", "Starting"), thinking: t("Claude सार लिख रहा है, कोड जाँच रहा है", "Claude is writing it; code is checking every fact"), speaking: t("हिंदी आवाज़ बन रही है", "Making the Hindi voice") }[b.status];
    return `<div class="card brief">${head}<p class="summary"><span class="spin"></span> ${step}…</p></div>`;
  }
  if (b.status === "fallback" || !b.brief) {
    return `<div class="card brief">${head}
      <p class="summary">${t("सार की भाषा जाँच में पास नहीं हुई, इसलिए सिर्फ़ पक्की बातें दिखा रहे हैं।", "The wording failed the checks twice, so SUNO shows only the code-checked facts (fail closed).")}</p>
      <ul class="needs">${d.needs_support.map((x) => `<li><b>${nm(x.child_id)}</b>: ${esc(skillName(x.skill_code))}</li>`).join("") || `<li>${t("अभी किसी के बारे में पक्का नहीं।", "Nothing certain yet.")}</li>`}</ul>
      <button class="btn warn" data-mkbrief style="margin-top:10px">${t("फिर से बनाइए", "Try again")}</button></div>`;
  }
  const br = b.brief, acts = S.me.activities;
  return `<div class="card brief">${head}
    ${b.audio_url ? `<div class="player"><button id="playbtn" aria-label="play">▶</button>
      <div style="flex:1"><div class="meta"><span>${t("सुनिए", "Listen (Hindi voice)")}</span><span id="ptime"></span></div><progress id="pprog" value="0" max="1"></progress></div>
      <audio id="baudio" preload="auto" src="${esc(b.audio_url)}"></audio></div>` : `<p class="small" style="color:#c9cfee">🔇 ${t("आवाज़ उपलब्ध नहीं; नीचे पढ़ें।", "Voice unavailable; read it below.")}</p>`}
    ${S.lang === "en" ? `<p class="summary">${esc(br.summary_en)}</p>` : ""}
    ${br.stuck_where.length ? `<ul class="needs">${br.stuck_where.map((x) => `<li><b>${x.child_ids.map(nm).join(", ")}</b> · ${esc(skillName(x.skill_code))}<div class="what deva">${esc(x.what_hi)}</div></li>`).join("")}</ul>`
      : `<p class="summary">${t("अभी किसी बच्चे के बारे में “मदद चाहिए” कहने लायक पक्का सबूत नहीं।", "Not enough evidence yet to name anyone as needing support.")}</p>`}
    ${br.today.map((g) => { const a = acts.find((x) => x.activity_id === g.activity_id) || {};
      return `<div class="group"><b>${t(`आज ${g.minutes} मिनट`, `Today, ${g.minutes} min`)}: ${esc(t(a.title || g.activity_id, a.title_en || g.activity_id))}</b> · ${g.child_ids.map(nm).join(", ")}
      <details><summary>${t("कैसे करें", "How")}</summary><div class="small deva" style="margin-top:6px">${esc(a.steps || "")}</div></details></div>`; }).join("")}
    <details${S.lang === "hi" ? " open" : ""}><summary>${t("पूरा सार", "Full brief in Hindi")}</summary><div class="fulltext deva">${esc(br.text_hi)}</div></details>
    ${b.problems_fixed && b.problems_fixed.length ? `<details><summary>${t("जाँच ने पहला मसौदा लौटाया", "Guardrail: the first draft was rejected")}</summary><div class="small" style="color:#c9cfee">${b.problems_fixed.map(esc).join("<br>")}</div></details>` : ""}
    <div style="margin-top:12px"><button class="linkbtn" data-mkbrief style="color:#aeb5df;font-size:12.5px">${t("सार फिर से बनाइए", "Rebuild brief")}</button></div>
  </div>`;
}

function wirePlayer() {
  const a = $("#baudio"), btn = $("#playbtn"); if (!a || !btn) return;
  const fmt = (s) => (isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "");
  a.onloadedmetadata = () => ($("#ptime").textContent = fmt(a.duration));
  a.ontimeupdate = () => { $("#pprog").value = a.duration ? a.currentTime / a.duration : 0; };
  a.onended = () => (btn.textContent = "▶");
  btn.onclick = () => { if (a.paused) { a.play(); btn.textContent = "❚❚"; } else { a.pause(); btn.textContent = "▶"; } };
}

function listenRow(x) {
  const r = REASON[x.reason];
  return `<div class="listen"><div class="av">${esc(initial(x.child_id))}</div>
    <div class="who"><div class="name">${esc(nameOf(x.child_id))}</div>
      <div class="tiny">${esc(skillName(x.skill_code))}</div>
      ${r ? `<span class="reason ${x.reason}">${t(...r)}</span>` : ""}
      ${x.reason === "confirm" && x.said ? `<div class="tiny deva" style="margin-top:3px">“${esc(x.said)}”</div>` : ""}</div>
    <div class="items"><div class="item">${esc(x.item)}</div>${x.also ? `<div class="item second">${t("फिर", "then")} · ${esc(x.also.item)}</div>` : ""}</div></div>`;
}

// ---------- SPEAK ----------
let REC = null;
async function renderSpeak() {
  const v = $("#view");
  const d = S.today || (await loadToday());
  if (S.tab !== "speak") return;
  const list = d ? d.listen_today : [];
  v.innerHTML = `<div class="cols">
    <div>
      <h2 class="sec">${t("आज का नोट", "Today's note")}</h2>
      <div class="card">
        <p class="small" style="margin-top:0">${t("लगभग 60 सेकंड, अपनी भाषा में: किसने क्या पढ़ा, कहाँ अटका, कौन नहीं आया।", "About 60 seconds, in your own words: who read what, where they got stuck, who was absent.")}</p>
        <div class="recorder">
          <button class="mic" id="mic" aria-label="record">🎙️</button>
          <div class="timer" id="timer">0:00</div>
          <div class="small muted" id="rec-hint">${t("दबाइए और बोलिए", "Tap and speak")}</div>
        </div>
        <details><summary class="small">${t("बोलने के बजाय लिखें", "Type instead")}</summary>
          <textarea id="ntext" class="deva" placeholder="आज पिंकी ने कमल को क म ल पढ़ा, जोड़ नहीं पाई…" style="margin-top:8px"></textarea>
          <button class="btn block" id="send-text" style="margin-top:8px">${t("भेजें", "Send")}</button>
        </details>
      </div>
      <div id="qcount"></div>
      <div id="progress"></div>
    </div>
    <div>
      ${list.length ? `<h2 class="sec">${t("आज की सूची", "Today's list")}</h2><div class="card small"><ul class="prompt-list">${list.map((x) => `<li><b>${esc(nameOf(x.child_id))}</b> · ${esc(x.item)}${x.also ? ` → ${esc(x.also.item)}` : ""}</li>`).join("")}</ul></div>` : ""}
      <div class="card flat small"><b>${t("उदाहरण", "Example")}</b><div class="deva" style="margin-top:4px">“आज पिंकी ने कमल को क-म-ल पढ़ा, जोड़ नहीं पाई। अमन ने पानी सही पढ़ा। सुरेश नहीं आया।”</div>
        <div class="tiny" style="margin-top:6px">${t("“वह कमज़ोर है” जैसी राय कभी सबूत नहीं बनती; SUNO उसे “कल फिर सुनें” बना देता है।", "Opinions like “he is weak” never become evidence: SUNO turns them into “listen again tomorrow”.")}</div></div>
      <details class="card" id="samples"><summary><b>${t("नमूना नोट (काल्पनिक)", "Sample notes for reviewers (synthetic)")}</b></summary><div id="sample-list" class="small" style="margin-top:8px"><span class="spin"></span></div></details>
    </div></div>`;
  $("#mic").onclick = toggleRec;
  $("#send-text").onclick = async () => {
    const text = $("#ntext").value.trim(); if (!text) return toast(t("नोट लिखें", "Type a note first"));
    await sendNote({ text, day: d?.today }); $("#ntext").value = "";
  };
  $("#samples").ontoggle = loadSamples;
  renderQueueBadge();
}

async function loadSamples() {
  const el = $("#sample-list"); if (!el || el.dataset.loaded) return;
  try {
    const s = await api("/api/samples"); el.dataset.loaded = 1;
    el.innerHTML = s.notes.map((n, i) => `
      <div style="padding:10px 0;border-top:1px solid var(--line)">
        <b>${esc(t(n.title, n.title_en))}</b>
        <div class="sent" style="margin:4px 0">${esc(n.text)}</div>
        ${n.audio ? `<audio controls preload="none" src="${esc(n.audio)}" style="width:100%;height:34px"></audio>` : ""}
        <div style="display:flex;gap:8px;margin-top:6px;flex-wrap:wrap">
          ${n.audio ? `<button class="btn alt" data-s="${i}" data-mode="audio">🎙️ ${t("आवाज़ भेजें", "Send as voice")}</button>` : ""}
          <button class="btn alt" data-s="${i}" data-mode="text">⌨️ ${t("टेक्स्ट भेजें", "Send as text")}</button>
        </div></div>`).join("") + `<p class="tiny">${esc(s.label || "")}</p>`;
    el.querySelectorAll("button[data-s]").forEach((btn) => (btn.onclick = async () => {
      const n = s.notes[+btn.dataset.s];
      if (btn.dataset.mode === "audio") {
        const blob = await (await fetch(n.audio)).blob();
        await sendNote({ blob, filename: n.audio.split("/").pop(), day: S.today?.today });
      } else await sendNote({ text: n.text, day: S.today?.today });
      $("#progress")?.scrollIntoView({ behavior: "smooth" });
    }));
  } catch (e) { el.textContent = t("नमूने नहीं मिले", "Samples unavailable"); }
}

async function toggleRec() {
  if (REC) return REC.stop();
  if (!navigator.mediaDevices?.getUserMedia) return toast(t("इस ब्राउज़र में रिकॉर्डिंग नहीं होती", "Recording isn't supported in this browser"));
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
  catch (_) { return toast(t("माइक की अनुमति दें", "Please allow the microphone")); }
  const mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", ""].find((m) => !m || MediaRecorder.isTypeSupported(m));
  const mr = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: 32000 } : undefined);
  const chunks = [], t0 = Date.now();
  mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const tick = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    $("#timer") && ($("#timer").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
    if (s >= 175) mr.stop();
  }, 250);
  mr.onstop = async () => {
    clearInterval(tick); stream.getTracks().forEach((tr) => tr.stop());
    REC = null; $("#mic")?.classList.remove("on"); $("#rec-hint") && ($("#rec-hint").textContent = t("दबाइए और बोलिए", "Tap and speak"));
    if ((Date.now() - t0) / 1000 < 1.5) return toast(t("बहुत छोटा नोट", "That was too short"));
    const type = mr.mimeType || "audio/webm";
    await sendNote({ blob: new Blob(chunks, { type }), filename: type.includes("mp4") ? "note.m4a" : type.includes("ogg") ? "note.ogg" : "note.webm", day: S.today?.today });
  };
  mr.start(1000); REC = mr;
  $("#mic").classList.add("on"); $("#rec-hint").textContent = t("बोल रहे हैं… रोकने के लिए दबाइए", "Recording… tap to stop");
}

async function sendNote(it) {
  const prog = $("#progress");
  try {
    const { note_id } = await postNote(it);
    pollNote(note_id, prog);
  } catch (e) {
    if (!e.status) { await qAdd({ ...it, created: Date.now() }); toast(t("नेटवर्क नहीं: नोट फ़ोन में रखा", "Offline: the note is saved on this phone")); renderQueueBadge(); }
    else toast(e.message);
  }
}

function progressHtml(status, isAudio) {
  const order = isAudio ? ["transcribing", "thinking", "done"] : ["thinking", "done"];
  const labels = { transcribing: t("आवाज़ से लिख रहे हैं (Sarvam)", "Speech-to-text (Sarvam)"), thinking: t("हर बच्चे की बात अलग कर रहे हैं (Claude), कोड जाँच रहा है", "Claude extracts each child's observations; code checks names, words and confidence"), done: t("तैयार", "Ready") };
  const idx = order.indexOf(status === "queued" ? order[0] : status);
  return `<div class="card"><ul class="steps">${order.map((s, i) => `<li class="${i < idx || status === "done" ? "done" : i === idx ? "now" : "todo"}">${labels[s]}</li>`).join("")}</ul></div>`;
}
const understoodHead = () => `<h2 class="sec">${t("SUNO ने क्या समझा", "What SUNO understood")}</h2>`;

async function pollNote(id, el) {
  let n;
  try { n = await api(`/api/notes/${id}`); } catch (e) { return; }
  if (el && document.body.contains(el)) {
    if (n.status === "failed") el.innerHTML = `<div class="card q-card">${t("नोट समझ नहीं पाए", "The note couldn't be processed")}: ${esc(n.error)}</div>`;
    else if (n.status !== "done") el.innerHTML = progressHtml(n.status, n.source === "audio");
    else { el.innerHTML = understoodHead() + noteBody(n); wireNote(el, n); S.today = null; }
  }
  if (!["done", "failed"].includes(n.status)) S.polling["n" + id] = setTimeout(() => pollNote(id, el), 1500);
  else if (n.status === "done" && !el) toast(t("नोट तैयार", "Note processed"));
}

// ---------- observation cards (shared) ----------
function recCard(r) {
  const st = r.kind === "opinion" && r.status === "check_tomorrow" ? ["राय, सबूत नहीं: कल सुनें", "Opinion, not evidence: listen tomorrow"] : STATUS[r.status] || [r.status, r.status];
  const who = r.child_id ? esc(nameOf(r.child_id)) : `“${esc(r.name_said || "?")}”`;
  const what = r.kind === "absent" ? t("आज अनुपस्थित", "Absent today")
    : `${r.skill_code ? esc(skillName(r.skill_code)) : ""}${r.item ? ` · <span class="it">${esc(r.item)}</span>` : ""} ${r.kind === "observation" ? outcome(r.outcome) : ""}`;
  const conf = r.confidence == null ? "" : `<div class="conf"><span>${t("भरोसा", "Confidence")} ${(r.confidence * 100).toFixed(0)}%</span><div class="bar"><i style="width:${Math.round(r.confidence * 100)}%"></i><b style="left:75%" title="gate 0.75"></b></div></div>`;
  const sig = r.signals ? `<details class="signals"><summary>${t("यह भरोसा कैसे बना (कोड से)", "Why this score (computed in code)")}</summary><table>
      <tr><td>${t("कौन", "Who")}</td><td>${esc(r.attribution)}</td></tr><tr><td>${t("शब्द बताया", "Specific item named")}</td><td>${r.signals.specificity}</td></tr>
      <tr><td>${t("गलती बताई", "Mistake described")}</td><td>${r.signals.concreteness}</td></tr><tr><td>${t("आज देखा", "Seen today")}</td><td>${r.signals.recency}</td></tr>
      <tr><td colspan="2">${t("सीमा 0.75", "Gate 0.75")} · ${r.kind === "opinion" ? t("राय कभी सबूत नहीं बनती", "opinions never become evidence") : t("सीमा से नीचे → कल फिर सुनें", "below the gate → listen again")}</td></tr></table></details>` : "";
  const fb = r.child_id && r.kind !== "absent" ? `<div class="fb">
      <button class="up ${r.feedback === "up" ? "on" : ""}" data-fb="up" data-r="${r.rec_id}">✓ ${t("सही समझा", "Right")}</button>
      <button class="down ${r.feedback === "down" ? "on" : ""}" data-fb="down" data-r="${r.rec_id}">✗ ${t("गलत समझा", "Wrong")}</button></div>` : "";
  return `<div class="card rec ${r.status}">
    <div class="head"><span class="name">${who}</span><span class="tag ${r.kind === "opinion" ? "opinion" : r.status}">${t(...st)}</span></div>
    <div class="what">${what}</div>
    ${S.lang === "en" && r.rationale ? `<div class="why">${esc(r.rationale)}</div>` : ""}
    ${r.home_language && r.home_language !== "none" ? `<div class="small">🗣️ ${r.home_language === "helped" ? t("घर की भाषा में समझ गया/गई", "Understood in the home language") : t("भाषा की दिक्कत", "Language barrier")}</div>` : ""}
    ${r.teacher_quote ? `<div class="quote">${esc(r.teacher_quote)}</div>` : ""}
    ${conf}${sig}${fb}</div>`;
}

function questionCard(q, n) {
  if (q.answered_at) return "";
  const rec = n.records.find((r) => r.mention_id === q.mention_id);
  const which = q.type === "which_child";
  const buttons = q.candidates.map((c) => `<button data-q="${q.q_id}" data-a="${c}">${esc(nameOf(c))}</button>`).join("");
  const others = S.me.roster.filter((c) => !q.candidates.includes(c.child_id));
  const select = which ? "" : `<select data-qsel="${q.q_id}"><option value="">${q.candidates.length ? t("कोई और", "Someone else") : t("बच्चा चुनें", "Choose a child")}</option>${others.map((c) => `<option value="${c.child_id}">${esc(nameOf(c.child_id))}</option>`).join("")}</select>`;
  const said = q.name_said || t("नाम नहीं लिया", "no name said");
  const why = which ? t("यह नाम एक से ज़्यादा बच्चों का है।", "This name matches more than one child.")
    : q.name_said ? t("यह नाम सूची में नहीं है।", "This name isn't on the roster.") + (q.candidates.length ? " " + t("सबसे मिलते-जुलते नाम:", "Closest-sounding names:") : "")
    : t("नाम नहीं लिया गया।", "No name was said.");
  return `<div class="card q-card">
    <b class="deva">“${esc(said)}”</b>: ${which ? t("कौन सा बच्चा?", "Which child?") : t("यह कौन है?", "Who is this?")} <span class="small muted">${why}</span>
    ${rec ? `<div class="small" style="margin-top:4px">${esc(skillName(rec.skill_code))} ${rec.item ? `· <span class="deva">${esc(rec.item)}</span>` : ""} ${outcome(rec.outcome)}</div>` : ""}
    <div class="opts">${buttons}<button data-q="${q.q_id}" data-a="skip">${t("छोड़ें", "Skip")}</button></div>${select}</div>`;
}

function noteBody(n) {
  const order = { unattributed: 0, evidence: 1, check_tomorrow: 2, absent: 3, dismissed: 4 };
  const recs = [...n.records].sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));
  const qs = n.questions.filter((q) => !q.answered_at);
  const shown = recs.filter((r) => r.status !== "unattributed" || (r.kind === "observation" && !n.questions.some((q) => q.mention_id === r.mention_id)));
  return `
    ${n.synthetic ? `<p class="tiny">${t("काल्पनिक नमूना नोट।", "Synthetic sample note.")}</p>` : ""}
    ${qs.map((q) => questionCard(q, n)).join("")}
    ${shown.map(recCard).join("") || `<p class="muted">${t("इस नोट में किसी बच्चे के बारे में बात नहीं मिली।", "No child-specific statements found in this note.")}</p>`}
    ${n.follow_ups.length ? `<div class="card flat small"><b>${t("अगली बार और साफ़ बताने के लिए", "To make it evidence next time")}</b>${n.follow_ups.map((f) => `<div class="deva" style="margin-top:4px">• ${esc(f.question_hi)}</div>`).join("")}</div>` : ""}
    <details class="card flat"><summary class="small">${t("आपका नोट (लिखा हुआ)", "Your note, as transcribed")}${n.seconds ? ` · ${n.seconds}s` : ""}</summary>
      <div style="margin-top:8px">${(n.sentences || []).map((s) => `<div class="sent"><span class="id">${s.sent_id}</span>${esc(s.text)}</div>`).join("")}</div></details>
    <button class="linkbtn" data-trace="${n.note_id}">${t("SUNO ने कैसे तय किया (Claude + कोड) →", "How SUNO decided (Claude + code checks) →")}</button>`;
}

function wireNote(el, n) {
  el.querySelectorAll("button[data-fb]").forEach((b) => (b.onclick = async () => {
    const on = b.classList.contains("on");
    try {
      await api(`/api/records/${b.dataset.r}/feedback`, { method: "POST", json: { verdict: on ? "clear" : b.dataset.fb } });
      b.parentElement.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
      if (!on) b.classList.add("on");
      S.today = null;
    } catch (e) { toast(e.message); }
  }));
  const answer = async (qid, a) => {
    try {
      await api(`/api/questions/${qid}`, { method: "POST", json: { answer: a } });
      const fresh = await api(`/api/notes/${n.note_id}`);
      el.innerHTML = (el.id === "progress" ? understoodHead() : noteHead(fresh)) + noteBody(fresh);
      wireNote(el, fresh); S.today = null; toast(t("धन्यवाद", "Thanks"));
    } catch (e) { toast(e.message); }
  };
  el.querySelectorAll("button[data-q]").forEach((b) => (b.onclick = () => answer(b.dataset.q, b.dataset.a)));
  el.querySelectorAll("select[data-qsel]").forEach((s) => (s.onchange = () => s.value && answer(s.dataset.qsel, s.value)));
  el.querySelectorAll("button[data-trace]").forEach((b) => (b.onclick = () => openTrace(b.dataset.trace)));
}

// ---------- NOTES ----------
const noteHead = (n) => `<h2>${esc(fmtDay(n.day))} <span class="tiny">${n.source === "audio" ? t("वॉइस नोट", "voice note") : t("लिखा / नमूना नोट", "typed or sample note")}</span></h2>`;
async function renderNotes() {
  const v = $("#view");
  v.innerHTML = `<div class="narrow"><h2 class="sec">${t("नोट्स", "Notes")}</h2><div id="qcount"></div><div id="nl"><div class="loading"><span class="spin"></span></div></div></div>`;
  renderQueueBadge();
  let notes;
  try { notes = await api("/api/notes"); } catch (e) { $("#nl").innerHTML = `<p class="muted">${t("ऑफ़लाइन", "Offline")}</p>`; return; }
  if (S.tab !== "notes") return;
  $("#nl").innerHTML = notes.length ? notes.map((n) => `
    <div class="card note-row" data-n="${n.note_id}">
      <div class="t"><b>${esc(fmtDay(n.day))}</b><div class="sn">${esc((n.transcript || n.error || "…").slice(0, 110))}</div></div>
      <span class="status ${n.status}">${n.status === "done" ? "✓" : esc(n.status)}</span></div>`).join("")
    : `<p class="muted">${t("अभी कोई नोट नहीं।", "No notes yet.")}</p>`;
  document.querySelectorAll("[data-n]").forEach((r) => (r.onclick = () => openNote(r.dataset.n)));
}
async function openNote(id) {
  const sh = sheet(`<div class="loading"><span class="spin"></span></div>`);
  const n = await api(`/api/notes/${id}`);
  sh.innerHTML = `<button class="close">×</button>` + noteHead(n) + noteBody(n) +
    `<div style="margin-top:18px"><button class="btn ghost block" id="del-note">🗑️ ${t("यह नोट मिटाएँ", "Delete this note")}</button></div>`;
  $(".close", sh).onclick = closeSheet;
  wireNote(sh, n);
  $("#del-note").onclick = async () => {
    if (!confirm(t("यह नोट और इससे बनी सारी बातें मिट जाएँगी। मिटाएँ?", "Delete this note and everything SUNO took from it?"))) return;
    try { await api(`/api/notes/${id}`, { method: "DELETE" }); closeSheet(); S.today = null; toast(t("मिटा दिया", "Deleted")); renderNotes(); }
    catch (e) { toast(e.message); }
  };
}

async function openTrace(id) {
  const sh = sheet(`<div class="loading"><span class="spin"></span></div>`);
  const d = await api(`/api/notes/${id}/trace`);
  const u = d.usage || {}, tm = d.timings || {};
  sh.innerHTML = `<button class="close">×</button>
    <h2>${t("SUNO ने कैसे तय किया", "How SUNO decided")}</h2>
    <ol class="small">
      <li>Speech-to-text: Sarvam <code>saaras:v4</code></li>
      <li>${t("वाक्यों में बाँटा", "Split into numbered sentences")}</li>
      <li>Claude <code>claude-opus-5-5</code>, adaptive thinking, JSON schema <code>${esc(d.schema_file)}</code>, prompt <code>${esc(d.prompt_file)}</code></li>
      <li>${t("कोड जाँच: हर बात शिक्षक के असली वाक्य से; बच्चा सूची से कोड तय करता है और Claude से मेल खाना चाहिए; शब्द उनके वाक्य में हों; लेबल छिपाए जाते हैं", "Code checks: every claim must cite her real sentences; code resolves the child from the roster and must agree with Claude; items must be in her words; labels are masked")}</li>
      <li>${t("भरोसा कोड से; सीमा 0.75", "Confidence computed in code; gate 0.75")}</li>
    </ol>
    <div class="card flat small">${t("समय", "Time")}: speech-to-text ${tm.speech_to_text_s ?? "–"} s · Claude ${tm.claude_s ?? "–"} s · Claude $${u.usd ?? "–"} (${u.input_tokens ?? 0} in, ${u.cache_read_tokens ?? 0} cached, ${u.output_tokens ?? 0} out)</div>
    <h3>${t("वाक्य", "Sentences")}</h3><div class="card flat">${(d.sentences || []).map((s) => `<div class="sent"><span class="id">${s.sent_id}</span>${esc(s.text)}</div>`).join("")}</div>
    <h3>${t("कोड ने क्या बदला या रोका", "What code changed or refused")}</h3>
    <div class="card flat small">${(d.code_checks || []).length ? d.code_checks.map((p) => `• ${esc(p[0])}: <b>${esc(p[1])}</b> · ${esc(p[2])}`).join("<br>") : t("Claude का जवाब हर जाँच में बिना बदलाव पास हुआ।", "Claude's output passed every check unchanged.")}
    ${d.questions.length ? "<br>" + d.questions.map((q) => `• “${esc(q.name_said)}”: ${q.candidates.length ? "→ " + q.candidates.map(nameOf).join(" / ") : t("सूची में नहीं", "not on the roster")} → ${t("शिक्षक से पूछा", "asked the teacher")}${q.answer ? " → " + (q.answer === "skip" ? t("छोड़ा", "skipped") : nameOf(q.answer)) : ""}`).join("<br>") : ""}</div>
    <h3>${t("कोड के बाद अंतिम रिकॉर्ड", "Final records (after code)")}</h3>
    <pre class="json">${esc(JSON.stringify(d.records.map((r) => ({ child: r.child_id ? nameOf(r.child_id) : null, said: r.name_said, kind: r.kind, skill: r.skill_code, item: r.item, outcome: r.outcome, error: r.error_type, attribution: r.attribution, signals: r.signals, confidence: r.confidence, status: r.status })), null, 1))}</pre>
    <h3>${t("Claude का कच्चा जवाब (कोड से पहले)", "Claude's raw output (before code)")}</h3>
    <pre class="json">${esc(JSON.stringify(d.claude_output, null, 1))}</pre>`;
  $(".close", sh).onclick = closeSheet;
}

// ---------- CLASS ----------
async function renderClass() {
  const v = $("#view");
  v.innerHTML = `<h2 class="sec">${t("कक्षा की तस्वीर", "Class picture")}</h2><div id="cg"><div class="loading"><span class="spin"></span></div></div>`;
  let c;
  try { c = await api("/api/class"); localStorage.setItem("suno_class", JSON.stringify(c)); }
  catch (e) { c = JSON.parse(localStorage.getItem("suno_class") || "null"); if (!c) { $("#cg").textContent = t("ऑफ़लाइन", "Offline"); return; } }
  if (S.tab !== "class") return;
  const areas = S.me.skills.areas, skills = S.me.skills.skills.filter((s) => s.area === S.area);
  const silent = new Set(c.silent), lang = new Set(c.language_flags.map((f) => f.child_id));
  const levelIdx = (cid) => { const l = (c.levels[cid] || {})[S.area]; return l && l.level !== null && l.level !== undefined ? l.level : null; };
  const groups = {};
  S.me.roster.forEach((ch) => { const l = levelIdx(ch.child_id); if (l !== null) (groups[l] = groups[l] || []).push(ch.child_id); });
  let ns = 0, ok = 0;
  Object.values(c.grid).forEach((row) => skills.forEach((s) => { const st = row[s.code].status; if (st === "needs support") ns++; if (st === "on track") ok++; }));
  $("#cg").innerHTML = `
    <div class="areas">${areas.map((a) => `<button data-a="${a.area}" class="${a.area === S.area ? "on" : ""}">${esc(t(a.label_hi, a.label_en))}</button>`).join("")}</div>
    ${Object.keys(groups).length ? `<div class="card groups"><h3>${t("स्तर के हिसाब से समूह", "Groups by level")}<span class="tiny" style="font-weight:500"> · Teaching at the Right Level</span></h3>
      ${Object.keys(groups).sort().map((l) => `<div class="g"><span class="cell lvl">${esc(levelName(S.area, +l))}</span> ${groups[l].map(nm).join(", ")}</div>`).join("")}</div>` : ""}
    <div class="legend"><span><span class="cell ns">${t("मदद चाहिए", "Needs support")}</span> ${ns}</span><span><span class="cell ok">${t("ठीक", "On track")}</span> ${ok}</span><span><span class="cell ne">—</span> ${t("अभी पता नहीं", "Not enough evidence yet")}</span></div>
    <div class="grid-wrap"><table class="grid">
      <thead><tr><th class="n">${t("बच्चा", "Child")}</th><th class="skill">${t("स्तर", "Level")}</th>${skills.map((s) => `<th class="skill">${esc(t(s.label_hi, s.label_en))}</th>`).join("")}</tr></thead>
      <tbody>${S.me.roster.map((ch) => { const l = levelIdx(ch.child_id); return `<tr data-c="${ch.child_id}"><td class="n">${esc(nameOf(ch.child_id))}${silent.has(ch.child_id) ? ' <span title="Silence Ledger">🔇</span>' : ""}${lang.has(ch.child_id) ? ' <span title="home language">🗣️</span>' : ""}</td>
        <td>${l !== null ? `<span class="cell lvl">${esc(levelName(S.area, l))}</span>` : `<span class="cell ne">—</span>`}</td>
        ${skills.map((s) => { const cell = c.grid[ch.child_id][s.code]; const [w, cls] = CELL[cell.status]; return `<td><span class="cell ${cls}" title="${cell.moments} obs, ${cell.days} days">${t(...w)}</span></td>`; }).join("")}</tr>`; }).join("")}</tbody>
    </table></div>
    <p class="tiny">${t("स्तर = सीढ़ी पर बच्चे की जगह, तभी दिखता है जब SUNO पक्का हो। एक बात कई कौशलों के बारे में बताती है: जो वाक्य पढ़ लेता है वह अक्षर जानता है। “—” तभी बदलता है जब दो दिनों में तीन या ज़्यादा पक्की बातें हों। 🔇 = 5 दिन से नहीं सुना। 🗣️ = घर की भाषा में समझा।",
      "Level = the child's rung on the ladder, shown only when SUNO is sure. One observation informs several skills: a child who reads a sentence knows her letters. A cell changes from “—” only after 3+ checked observations over 2+ days. 🔇 = not described for 5 school days. 🗣️ = understood once explained in the home language. Tap a child for the evidence.")}</p>`;
  document.querySelectorAll(".areas button").forEach((b) => (b.onclick = () => { S.area = b.dataset.a; renderClass(); }));
  document.querySelectorAll("tr[data-c]").forEach((r) => (r.onclick = () => openChild(r.dataset.c)));
}

async function openChild(id) {
  const sh = sheet(`<div class="loading"><span class="spin"></span></div>`);
  const d = await api(`/api/children/${id}`);
  const rows = S.me.skills.skills.filter((s) => d.grid[s.code].moments > 0);
  const lv = S.me.skills.areas.filter((a) => d.levels[a.area]).map((a) => {
    const l = d.levels[a.area], nx = d.next_steps[a.area];
    return `<div style="padding:8px 0;border-top:1px solid var(--line)"><b>${esc(t(a.label_hi, a.label_en))}</b>: ${l.level !== null ? `<span class="cell lvl">${esc(levelName(a.area, l.level))}</span>` : `<span class="cell ne">${t("स्तर अभी पक्का नहीं", "Level not certain yet")}</span>`}
      ${nx ? ` · ${t("अगला कदम", "Next step")}: <b>${esc(skillName(nx))}</b>` : ""} <span class="tiny">${l.moments} ${t("बातें", "obs")} · ${l.days} ${t("दिन", "days")}</span></div>`; }).join("");
  sh.innerHTML = `<button class="close">×</button>
    <h2><span class="deva">${esc(nameOf(id))}</span> <span class="tiny">${t("रोल", "Roll")} ${d.child.roll_no}</span></h2>
    ${d.language_flag ? `<div class="card flat small">🗣️ ${d.language_flag.signal === "helped" ? t("घर की भाषा में समझाने पर समझ जाता/जाती है: दिक्कत भाषा की हो सकती है, समझ की नहीं।", "Understands once it's explained in the home language: the gap may be the language, not the concept.") : t("पढ़ाई की भाषा समझने में दिक्कत।", "The language of instruction is a barrier.")}</div>` : ""}
    ${lv ? `<div class="card small">${lv}</div>` : ""}
    <div class="card">${rows.length ? rows.map((s) => { const g = d.grid[s.code]; const [w, cls] = CELL[g.status];
      return `<div style="display:flex;justify-content:space-between;gap:8px;padding:5px 0"><span>${esc(skillName(s.code))}</span><span class="cell ${cls}">${t(...w)}</span></div>`; }).join("")
      : `<p class="muted small">${t("अभी कोई पक्की बात नहीं।", "No checked observations yet.")}</p>`}</div>
    <h2 class="sec">${t("आपने क्या बताया", "What the teacher said, newest first")}</h2>
    ${d.records.map((r) => `<div class="tiny" style="margin-top:10px">${esc(fmtDay(r.day))}</div>` + recCard(r)).join("") || `<p class="muted">${t("अभी कुछ नहीं।", "Nothing yet.")}</p>`}`;
  $(".close", sh).onclick = closeSheet;
  wireNote(sh, { note_id: null, records: d.records });
}

// ---------- roster editor (typed, or from a photo of the attendance register) ----------
function openRoster(draft) {
  const rows = draft || S.me.roster.map((c) => ({ child_id: c.child_id, first_name: c.first_name, roll_no: c.roll_no,
    aliases: (c.aliases || []).filter((a) => !/^[A-Za-z]/.test(a)) }));
  const sh = sheet(`
    <h2>${t("बच्चों की सूची", "Children")}</h2>
    <p class="small muted">${t("सिर्फ़ पहला नाम। उपनाम (जैसे गुड्डू) दूसरे खाने में।", "First names only. A nickname (like Guddu) goes in the second box.")}</p>
    <label class="btn warn block" style="margin:8px 0">📷 ${t("रजिस्टर की फ़ोटो से भरें", "Fill from a photo of the attendance register")}
      <input type="file" id="reg-photo" accept="image/*" capture="environment" style="display:none"></label>
    <div id="reg-status" class="small"></div>
    <div id="rows">${rows.map(rosterRow).join("")}</div>
    <button class="btn alt block" id="add-row" style="margin-top:6px">+ ${t("बच्चा जोड़ें", "Add a child")}</button>
    <button class="btn block" id="save-roster" style="margin-top:10px">${t("सूची सहेजें", "Save the list")}</button>
    <p class="tiny">${t("फ़ोटो Claude पढ़ता है और रखी नहीं जाती। उपनाम और पिता का नाम हटा दिए जाते हैं; सहेजने से पहले आप जाँचती हैं।", "Claude reads the photo; it is not stored. Surnames and fathers' names are dropped, and you check the list before saving.")}</p>`);
  const wire = () => sh.querySelectorAll("button[data-del]").forEach((b) => (b.onclick = () => b.closest(".roster-row").remove()));
  wire();
  $("#add-row", sh).onclick = () => { $("#rows", sh).insertAdjacentHTML("beforeend", rosterRow({})); wire(); };
  $("#reg-photo", sh).onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    $("#reg-status", sh).innerHTML = `<span class="spin"></span> ${t("फ़ोटो पढ़ रहे हैं…", "Reading the photo (Claude)…")}`;
    const fd = new FormData(); fd.append("photo", await shrink(f), "register.jpg");
    try {
      const r = await api("/api/roster/photo", { method: "POST", body: fd });
      const have = [...sh.querySelectorAll(".roster-row")].map(readRow).filter((x) => x.first_name);
      $("#rows", sh).innerHTML = [...have, ...r.children.map((c) => ({ first_name: c.first_name, roll_no: c.roll_no }))].map(rosterRow).join(""); wire();
      $("#reg-status", sh).innerHTML = `✓ ${t(`${r.children.length} नाम मिले${r.unreadable ? `, ${r.unreadable} पढ़े नहीं जा सके` : ""}। जाँचकर सहेजें।`, `${r.children.length} names found${r.unreadable ? `, ${r.unreadable} unreadable` : ""}. Check them, then save.`)} <span class="tiny deva">${esc(r.note || "")}</span>`;
    } catch (err) { $("#reg-status", sh).textContent = t("फ़ोटो नहीं पढ़ी जा सकी: ", "Couldn't read the photo: ") + err.message; }
  };
  $("#save-roster", sh).onclick = async () => {
    const children = [...sh.querySelectorAll(".roster-row")].map(readRow).filter((x) => x.first_name);
    if (!children.length) return toast(t("कम से कम एक नाम लिखें", "Add at least one name"));
    try {
      await api("/api/roster", { method: "PUT", json: { children } });
      S.me = await api("/api/me"); localStorage.setItem("suno_me", JSON.stringify(S.me));
      closeSheet(); toast(t(`${S.me.roster.length} बच्चे सहेजे`, `${S.me.roster.length} children saved`)); S.today = null; go(S.tab);
    } catch (err) { toast(err.message); }
  };
}
function rosterRow(c) {
  return `<div class="roster-row" data-id="${esc(c.child_id || "")}">
    <input class="roll" type="number" min="1" value="${esc(c.roll_no ?? "")}" placeholder="${t("रोल", "Roll")}">
    <input class="name" type="text" value="${esc(c.first_name || "")}" placeholder="${t("पहला नाम", "First name")}">
    <input class="nick" type="text" value="${esc((c.aliases || [])[0] || "")}" placeholder="${t("उपनाम", "Nickname")}">
    <button data-del aria-label="remove">✕</button></div>`;
}
function readRow(el) {
  const nick = $(".nick", el).value.trim();
  return { child_id: el.dataset.id || null, first_name: $(".name", el).value.trim(), roll_no: parseInt($(".roll", el).value, 10) || null, aliases: nick ? [nick] : [] };
}
async function shrink(file, max = 1600) {
  // Phone photos are large: send a smaller JPEG so it uploads on a weak connection.
  try {
    const img = await createImageBitmap(file);
    const k = Math.min(1, max / Math.max(img.width, img.height));
    const cv = document.createElement("canvas"); cv.width = img.width * k; cv.height = img.height * k;
    cv.getContext("2d").drawImage(img, 0, 0, cv.width, cv.height);
    return await new Promise((res) => cv.toBlob(res, "image/jpeg", 0.85));
  } catch (_) { return file; }
}

// ---------- this week's lesson ----------
function openLesson() {
  const L = S.me.lesson;
  const sh = sheet(`
    <h2>${t("इस हफ़्ते का पाठ", "This week's lesson")}</h2>
    <p class="small muted">${t("इस हफ़्ते की किताब के शब्द और सवाल। SUNO इन्हीं से बताएगा कि किस बच्चे से क्या पढ़वाएँ। ✓ = इस हफ़्ते का मुख्य हिस्सा।", "Words and sums from this week's pages. SUNO picks today's listening items from these. ✓ = this week's focus.")}</p>
    <input id="l-title" class="deva" type="text" value="${esc(L.title || "")}" placeholder="${t("पाठ का नाम, जैसे: पाठ 12, कमल का फूल", "Lesson name, e.g. Lesson 12")}">
    ${S.me.skills.areas.map((a) => `<h3 style="margin-top:16px">${esc(t(a.label_hi, a.label_en))}</h3>` + S.me.skills.skills.filter((sk) => sk.area === a.area).map((sk) => `
      <div class="lesson-skill"><label><input type="checkbox" data-focus="${sk.code}" ${(L.focus_skills || []).includes(sk.code) ? "checked" : ""}> ${esc(skillName(sk.code))}</label>
      <input type="text" class="deva" data-items="${sk.code}" value="${esc((L.items[sk.code] || []).join(", "))}" placeholder="${esc(sk.example)}"></div>`).join("")).join("")}
    <button class="btn block" id="save-lesson" style="margin-top:14px">${t("सहेजें", "Save")}</button>`);
  $("#save-lesson", sh).onclick = async () => {
    const items = {}, focus = [];
    sh.querySelectorAll("[data-items]").forEach((i) => { items[i.dataset.items] = i.value.split(/[,،\n]/).map((x) => x.trim()).filter(Boolean); });
    sh.querySelectorAll("[data-focus]").forEach((c) => c.checked && focus.push(c.dataset.focus));
    try {
      await api("/api/lesson", { method: "PUT", json: { title: $("#l-title", sh).value, focus_skills: focus, items } });
      S.me = await api("/api/me"); localStorage.setItem("suno_me", JSON.stringify(S.me));
      closeSheet(); toast(t("पाठ सहेजा", "Lesson saved")); S.today = null; go(S.tab);
    } catch (err) { toast(err.message); }
  };
}

// ---------- Evidence page (public): numbers come from /api/evidence, i.e. from the scripts' output ----------
const pct = (a, b) => (b ? `${Math.round((100 * a) / b)}%` : "–");
const pc = (x) => (x == null || x !== x ? "–" : `${Math.round(100 * x)}%`);
function pageShell(title, body) {
  $("#app").innerHTML = `
  <header class="top"><div class="row"><div class="brandmark" style="width:32px;height:32px;border-radius:9px">स</div>
    <div class="wordmark" style="font-size:18px">SUNO<span class="deva">सुनो</span></div><div class="spacer"></div>${langSwitch()}
    <button class="btn alt" id="back" style="padding:7px 12px">← ${t("वापस", "Back")}</button></div></header>
  <main class="view" style="max-width:920px;margin:0 auto;padding-top:18px"><h1 style="font-size:28px;margin:6px 0 4px">${title}</h1>${body}</main>`;
  $("#back").onclick = pageBack;
  wireLang($("header.top"), route);
  window.scrollTo(0, 0);
}

async function renderEvidence() {
  pageShell(t("हमने SUNO को कैसे परखा", "How we tested SUNO"), `<div class="loading"><span class="spin"></span></div>`);
  let e = {};
  try { e = await api("/api/evidence"); } catch (_) {}
  const P = e.pipeline, T = e.term, C = e.cost, R = e.real_speech;
  const arm = (a, wk, m) => (T && T.arms[a] && T.arms[a][wk] ? pc(T.arms[a][wk][m]) : "–");
  const body = `
    <p class="muted">${t("असली कक्षा का सबूत 1 नवंबर से पहले संभव नहीं था, इसलिए हमने SUNO को सिमुलेशन में परखा। हर संख्या एक स्क्रिप्ट से आती है; मान्यताएँ eval/sim/ में लिखी हैं। नवंबर में असली कक्षाओं में परीक्षण।", "Real classroom evidence wasn't possible before 1 Nov, so we tested SUNO in simulation. Every number below comes from a script in the repo, and the assumptions are written in eval/sim/. Classroom testing follows in November.")}</p>

    <h2 class="sec">${t("1. AI कहाँ और कैसे", "1. Where the AI is, layer by layer")}</h2>
    <div class="card small"><ol style="margin:0;padding-left:20px;line-height:1.7">
      <li><b>${t("इनपुट", "Input")}</b>: ${t("शिक्षक का 60 सेकंड का वॉइस नोट (या लिखा नोट)। किसी बच्चे की आवाज़ नहीं।", "the teacher's 60-second voice note (or a typed note). No child's voice, no classroom recording.")}</li>
      <li><b>${t("बोली से लिखाई", "Speech to text")}</b>: Sarvam <code>saaras:v4</code> → ${t("गिने हुए वाक्य", "numbered sentences")}.</li>
      <li><b>Claude ①</b> <code>claude-opus-5-5</code>: ${t("हर बच्चे की बात अलग: कौशल, शब्द, नतीजा, गलती का प्रकार, घर की भाषा।", "splits the note into per-child observations: skill, item, outcome, mistake type, home-language signal.")} <span class="tiny">prompts/observations.v2.md · schemas/observations.v1.json</span></li>
      <li><b>${t("कोड की जाँच", "Code guardrails")}</b>: ${t("नीचे देखें।", "see section 2.")}</li>
      <li><b>${t("कोड का फ़ैसला", "Code decides")}</b>: ${t("बच्चे का सीढ़ी पर स्तर (Bayes), चुप्पी की सूची, आज किसे सुनें।", "each child's level on the ladder (Bayesian), the Silence Ledger, and whom to listen to today.")}</li>
      <li><b>Claude ②</b>: ${t("कोड के तय तथ्यों को सरल हिंदी सार में लिखता है; कोड फिर जाँचता है।", "words the morning brief from facts code decided; code checks it again.")} <span class="tiny">prompts/brief.v3.md · schemas/brief.v2.json</span></li>
      <li><b>${t("आउटपुट", "Output")}</b>: Sarvam <code>bulbul:v3</code> ${t("हिंदी आवाज़ में सार।", "speaks the brief in Hindi.")}</li>
      <li><b>${t("सेटअप", "Setup")}</b>: ${t("Claude ③ (vision) हाज़िरी रजिस्टर की फ़ोटो से सिर्फ़ पहले नाम पढ़ता है; शिक्षक जाँचती हैं।", "Claude ③ (vision) reads first names from a photo of the attendance register; the teacher checks the list.")}</li>
    </ol></div>

    <h2 class="sec">${t("2. गलत या अनुचित AI जवाब कैसे रोके जाते हैं", "2. How wrong or inappropriate AI output is handled")}</h2>
    <div class="card small"><ul style="margin:0;padding-left:20px;line-height:1.7">
      <li>${t("हर बात को शिक्षक के असली वाक्य का हवाला देना होगा; नाम, उद्धरण और शब्द उनके शब्दों में होने चाहिए, नहीं तो हटाया जाता है।", "Every claim must cite the teacher's real sentences; the name, quote and item must appear in her words, or they are removed.")}</li>
      <li>${t("बच्चा कोड तय करता है (नाम का ध्वनि-मिलान, रोल नंबर); Claude से न मिले तो एक टैप का सवाल।", "Code resolves the child itself (phonetic name matching, roll numbers in digits or Hindi words) and must agree with Claude; any mismatch or shared name becomes a one-tap question.")}</li>
      <li>${t("भरोसा कोड गिनता है, Claude कभी नहीं; 0.75 से नीचे की बात “कल फिर सुनें” बनती है।", "Confidence is computed in code, never by Claude; below 0.75 a claim becomes “listen again tomorrow”.")}</li>
      <li>${t("राय और लेबल (“कमज़ोर”) कभी सबूत नहीं; लेबल छिपाए जाते हैं और कभी दोहराए नहीं जाते।", "Opinions and labels (“weak”, कमज़ोर) never become evidence; labels are masked and never repeated.")}</li>
      <li>${t("बोली-से-लिखाई अगर बच्चे की गलती मिटा दे (“किताब को किताब पढ़ा”), तो उसे “सही” नहीं माना जाता।", "If speech-to-text erases the child's misreading (“किताब को किताब पढ़ा”), it can't count as correct.")}</li>
      <li>${t("नाम तभी, जब दो दिनों में तीन या ज़्यादा पक्की बातें हों।", "A child is named only after 3+ checked observations over 2+ days.")}</li>
      <li>${t("सार की हर बात कोड के तथ्यों से जाँची जाती है; दो बार फ़ेल होने पर सिर्फ़ कोड के तथ्य दिखते हैं।", "The brief is checked against code's facts; if it fails twice, the app shows only the code-checked facts (fail closed).")}</li>
      <li>${t("शिक्षक हर बात पर ✓/✗ कर सकती हैं; ✗ उसे हटा देता है।", "The teacher can mark any observation ✓ or ✗; ✗ removes it from the tracker.")}</li>
      <li>${t("हर नोट का पूरा ब्योरा ऐप में: Claude का कच्चा जवाब, हर जाँच, भरोसे का हिसाब।", "Every note has a trace in the app: Claude's raw output, every code check, the confidence arithmetic.")}</li>
    </ul></div>

    <h2 class="sec">${t("3. नकली कक्षाओं पर असली पाइपलाइन", "3. The real pipeline on simulated classrooms")}</h2>
    ${P ? `<div class="card small"><p style="margin-top:0">${t(`${P.notes} वॉइस नोट, 4 शिक्षण शैलियाँ (${P.styles.join(", ")}): नकली शिक्षक बताती हैं कि बच्चों ने असल में क्या किया, जिसमें एक जैसे नाम, अनजाने उपनाम, लेबल और राय भी हैं। Sarvam आवाज़ बनाता और फिर लिखता है; SUNO की असली पाइपलाइन; सच्चाई पहले से पता।`, `${P.notes} voice notes from simulated teachers in 4 styles (${P.styles.join(", ")}), stating what children actually did, including shared names, unknown nicknames, labels and opinions. Each was voiced and transcribed by Sarvam and run through SUNO's real pipeline, with ground truth known.`)}</p>
      <table class="signals" style="width:100%;font-size:14px">
        <tr><td>${t("गलत बच्चे पर सबूत", "Evidence about the wrong child")}</td><td><b>${P.wrong_child_evidence} / ${P.evidence}</b></td></tr>
        <tr><td>${t("सही/गलत की दिशा सही", "Right/wrong direction correct")}</td><td><b>${P.direction_ok} / ${P.evidence}</b></td></tr>
        <tr><td>${t("राय, लेबल, अस्पष्ट बातें जो सबूत बनीं", "Opinions, labels, vague remarks that became evidence")}</td><td><b>${P.not_evidence_became_evidence} / ${P.not_evidence}</b></td></tr>
        <tr><td>${t("लेबल दोहराए गए", "Labels repeated by SUNO")}</td><td><b>${P.labels_repeated}</b> (${t(`${P.labels_used} बातों में लेबल था`, `${P.labels_used} statements used one`)})</td></tr>
        <tr><td>${t("साफ़ नाम वाली ठोस बातें जो सबूत बनीं", "Specific observations about a clearly named child that became evidence")}</td><td><b>${pct(P.clear_obs_evidence, P.clear_obs)}</b> (${P.clear_obs_evidence}/${P.clear_obs})</td></tr>
        <tr><td>${t("अस्पष्ट नाम, एक टैप से सुलझे", "Unclear names resolved with one tap")}</td><td><b>${P.unclear_names_resolved} / ${P.unclear_names}</b></td></tr>
      </table><p class="tiny">eval/results/sim_pipeline.md</p></div>` : `<p class="muted">–</p>`}

    ${R ? `<h2 class="sec">${t("3b. असली आवाज़, असली फ़ोन", "3b. A real human voice on an ordinary phone")}</h2>
    <div class="card small"><p style="margin-top:0">${t(`एक असली व्यक्ति ने काल्पनिक कक्षा के नोट फ़ोन पर पढ़े: शांत कमरा, पंखा, और कक्षा का शोर (${R.recordings} रिकॉर्डिंग)। बोली-से-लिखाई की शब्द-गलती दर: ${Object.entries(R.settings).map(([k, v]) => `${k} ${Math.round(100 * v.wer)}%`).join(", ")}।`, `One real speaker read scripted notes (a fictional class) into an ordinary phone in a quiet room, with a fan on, and with classroom noise playing (${R.recordings} recordings). Speech-to-text word error rate: ${Object.entries(R.settings).map(([k, v]) => `${k} ${Math.round(100 * v.wer)}%`).join(", ")}.`)}</p>
      <table class="signals" style="width:100%;font-size:14px">
        <tr><td>${t("गलत बच्चे पर सबूत", "Evidence about the wrong child")}</td><td><b>${R.wrong_child_evidence} / ${R.evidence}</b></td></tr>
        <tr><td>${t("सही/गलत की दिशा सही", "Right/wrong direction correct")}</td><td><b>${R.direction_ok} / ${R.evidence}</b></td></tr>
        <tr><td>${t("राय और अस्पष्ट बातें जो सबूत बनीं", "Opinions and vague remarks that became evidence")}</td><td><b>${R.not_evidence_became_evidence} / ${R.not_evidence}</b></td></tr>
        <tr><td>${t("साफ़ नाम वाली ठोस बातें जो सबूत बनीं", "Specific observations that became evidence")}</td><td><b>${pct(R.clear_obs_evidence, R.clear_obs)}</b> (${R.clear_obs_evidence}/${R.clear_obs})</td></tr>
        <tr><td>${t("अनुपस्थिति दर्ज", "Absences recorded")}</td><td><b>${R.absent_found} / ${R.absent}</b></td></tr>
      </table>
      <p style="margin-bottom:0">${t("इस परीक्षण ने दो बदलाव करवाए: सबूत के लिए ठोस शब्द या सवाल ज़रूरी, और “रोल तेरा” जैसे बोले गए रोल नंबर पढ़ना।", "This test changed two things: evidence now needs a specific word or sum, and roll numbers as people say them (“रोल तेरा” = 13) are understood.")}</p>
      <p class="tiny">${t("सीमा: एक ही वक्ता (पुरुष)।", "Limit: one speaker (a man); most primary teachers are women.")} eval/results/real_notes.md</p></div>` : ""}

    <h2 class="sec">${t("4. 12 हफ़्ते का सत्र, 200 बार", "4. A 12-week term, simulated 200 times")}</h2>
    ${T ? `<div class="card small"><p style="margin-top:0">${t("SUNO के असली ट्रैकर और प्लानर के साथ; ऊपर की गलती दरें (कम से कम 3/n)। तुलना: शिक्षक जो अपने आप देखती हैं उसकी एक पूरी डायरी।", "Uses SUNO's real tracker and planner, with the error rates above (floored at 3/n). The baseline is a perfect written diary of what the teacher notices on her own.")}</p>
      <table class="signals" style="width:100%;font-size:14px">
        <tr><td></td><td><b>${t("पूरी डायरी", "Perfect diary")}</b></td><td><b>${t("SUNO की सूची, 80% माना", "SUNO's list, followed 80%")}</b></td></tr>
        <tr><td>${t("सबसे शांत तिहाई, 2 हफ़्ते में सुने गए", "Quietest third heard by week 2")}</td><td>${arm("no_list", "2", "quiet_with_evidence")}</td><td><b>${arm("list_80", "2", "quiet_with_evidence")}</b></td></tr>
        <tr><td>${t("मदद चाहने वाले बच्चे, 8 हफ़्ते में मिले", "Children who need support found by week 8")}</td><td>${arm("no_list", "8", "children_found")}</td><td><b>${arm("list_80", "8", "children_found")}</b></td></tr>
        <tr><td>${t("शांत बच्चों की कमियाँ, 8 हफ़्ते में", "Quiet children's gaps found by week 8")}</td><td>${arm("no_list", "8", "quiet_struggling_found")}</td><td><b>${arm("list_80", "8", "quiet_struggling_found")}</b></td></tr>
        <tr><td>${t("“मदद चाहिए” जो सही थे", "“Needs support” flags that were right")}</td><td>${arm("no_list", "12", "children_flag_precision")}</td><td><b>${arm("list_80", "12", "children_flag_precision")}</b></td></tr>
      </table>
      <p style="margin-bottom:0">${t("सिमुलेशन ने डिज़ाइन बदला: पहला प्लानर पहचान को बिगाड़ रहा था (थोड़ी बातें बहुत बच्चों में बँट जाती थीं)। इसलिए सीढ़ी-आधारित स्तर और हर बच्चे से दो शब्द।", "The simulation changed the design: the first planner made detection worse (a few observations spread over too many children). That led to the ladder model and two words per child.")}</p><p class="tiny">eval/results/sim_term.md · ${T.runs} runs</p></div>` : `<p class="muted">–</p>`}

    <h2 class="sec">${t("5. चलाने का खर्च", "5. Running cost")}</h2>
    ${C ? `<div class="card small">${t(`हर स्कूल दिन, हर शिक्षक: ₹${C.day_inr.toFixed(1)} (Claude + Sarvam), यानी लगभग <b>₹${Math.round(C.child_year_inr)} प्रति बच्चा प्रति वर्ष</b>। उसी डिज़ाइन में सस्ता तरीका: अनुमानित ₹${Math.round(C.lean_child_year_inr)}।`, `Per teacher per school day: ₹${C.day_inr.toFixed(1)} (Claude + Sarvam), about <b>₹${Math.round(C.child_year_inr)} per child per year</b>. A leaner configuration of the same design: about ₹${Math.round(C.lean_child_year_inr)} (estimate).`)}<p class="tiny">eval/results/cost.md · ${t("लॉग किए गए असली उपयोग से", "from logged usage")}</p></div>` : ""}

    <h2 class="sec">${t("6. सीमाएँ, साफ़-साफ़", "6. Limits, stated plainly")}</h2>
    <div class="card small"><ul style="margin:0;padding-left:20px;line-height:1.7">
      <li>${t("ज़्यादातर नतीजे सिमुलेशन के हैं; असली आवाज़ का परीक्षण एक ही वक्ता का है। असली शिक्षकों की बोली, आदतें और राय अभी परखी जानी हैं।", "Most results are simulated, and the real-voice test has one speaker. Real teachers' speech, habits and judgement are still to be tested.")}</li>
      <li>${t("दिन में ~5 बच्चों पर, किसी बच्चे की कमी पक्के तौर पर लगभग 6 हफ़्ते में दिखती है।", "At about 5 children a day, a struggling child is flagged with confidence after about 6 weeks.")}</li>
      <li>${t("SUNO शिक्षक की बात पर चलता है; अगले कदम में ASER टेस्ट से तुलना (वही बच्चे) होगी।", "SUNO relies on what the teacher reports; next is a comparison with the ASER test on the same children.")}</li>
    </ul></div>`;
  pageShell(t("हमने SUNO को कैसे परखा", "How we tested SUNO"), body);
}

// ---------- Privacy page (public), with "delete my class" when signed in ----------
async function renderPrivacy() {
  let me = null;
  try { me = await api("/api/me"); } catch (_) {}
  pageShell(t("निजता और आपका डेटा", "Privacy and your data"), `
    <div class="card"><h3>${t("SUNO क्या कभी नहीं रखता", "What SUNO never keeps")}</h3><ul class="small" style="line-height:1.7;padding-left:20px;margin:0">
      <li>${t("किसी बच्चे की आवाज़: कक्षा रिकॉर्ड नहीं होती।", "Any child's voice: the classroom is never recorded.")}</li>
      <li>${t("शिक्षक का वॉइस नोट: लिखाई के बाद तुरंत हटाया जाता है।", "The teacher's voice note: it is deleted right after transcription.")}</li>
      <li>${t("रजिस्टर की फ़ोटो: पढ़कर हटाई जाती है।", "The register photo: read, then discarded.")}</li>
      <li>${t("उपनाम, पिता का नाम, जन्मतिथि, फ़ोटो: कभी नहीं।", "Surnames, fathers' names, dates of birth, photos: never.")}</li>
      <li>${t("शिक्षक का कोई स्कोर या प्रदर्शन का कोई खाना: कहीं नहीं।", "Any teacher score or performance field: none exists.")}</li></ul></div>
    <div class="card"><h3>${t("SUNO क्या रखता है", "What SUNO keeps")}</h3><p class="small" style="margin:0">${t("बच्चों के पहले नाम और रोल नंबर; शिक्षक के नोट की लिखाई; उनसे बनी बातें (कौशल, शब्द, नतीजा); सुबह का सार और उसकी आवाज़। सिर्फ़ कक्षा कोड वाला ही इसे देख सकता है।", "Children's first names and roll numbers; the text of the teacher's notes; the observations drawn from them (skill, item, outcome); the morning brief and its audio. Only someone with the class code can see it.")}</p></div>
    <div class="card"><h3>${t("डेटा किसका है", "Who owns the data")}</h3><p class="small" style="margin:0">${t("डेटा स्कूल या राज्य का है; SUNO उनकी ओर से प्रोसेस करता है (DPDP अधिनियम 2023 और नियम 2025 के अनुसार, शैक्षणिक संस्थान डेटा फ़िड्यूशियरी)। स्कूल में इस्तेमाल से पहले प्रधानाध्यापक की लिखित अनुमति और SMC बैठक में अभिभावकों को जानकारी। AI मॉडल इस डेटा पर प्रशिक्षित नहीं होते।", "The school or state owns the data; SUNO processes it on their behalf (under the DPDP Act 2023 and Rules 2025, the educational institution is the data fiduciary). Before use in a school: the head teacher's written permission, and parents informed at a School Management Committee meeting. AI models are not trained on this data.")}</p></div>
    ${me ? `<div class="card" style="border-color:#F3C5C8"><h3>${t("अपनी कक्षा मिटाएँ", "Delete my class")}</h3>
      <p class="small">${t("सारे बच्चे, नोट, बातें और सार हमेशा के लिए मिट जाएँगे। पुष्टि के लिए कक्षा कोड लिखें:", "All children, notes, observations and briefs are deleted for good. Type your class code to confirm:")} <b>${esc(me.code || me.name)}</b></p>
      <input id="del-confirm" type="text" autocomplete="off">
      <button class="btn block" id="del-class" style="margin-top:8px;background:var(--red)">${t("कक्षा हमेशा के लिए मिटाएँ", "Delete this class permanently")}</button></div>` : ""}
    <p class="tiny">${t("यह हमारी समझ है, क़ानूनी सलाह नहीं।", "This is our reading of the law, not legal advice.")}</p>`);
  $("#del-class") && ($("#del-class").onclick = async () => {
    try {
      await api("/api/class", { method: "DELETE", json: { confirm: $("#del-confirm").value } });
      await clearCached(); toast(t("कक्षा मिटा दी गई", "Class deleted")); pageBack();
    } catch (e) { toast(e.message); }
  });
}

route();
