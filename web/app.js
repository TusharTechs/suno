/* SUNO teacher web app. Vanilla JS, no build step: loads fast on a cheap phone. */
"use strict";

const S = { me: null, tab: "today", today: null, area: "hindi", online: navigator.onLine, polling: {} };
const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const REASON = {
  confirm: ["पक्का करना है", "confirm what you said"],
  not_heard: ["हफ़्ते भर से नहीं सुना", "not heard this week"],
  needs_support: ["मदद चाहिए", "needs support"],
  least_known: ["कम जानकारी", "least known"],
};
const STATUS = {
  evidence: ["पक्का सबूत", "evidence"],
  check_tomorrow: ["कल फिर सुनें", "check again"],
  absent: ["अनुपस्थित", "absent"],
  unattributed: ["कौन? बताइए", "who was it?"],
  dismissed: ["छोड़ दिया", "skipped"],
};
const OUTCOME = { correct: "✓ सही", incorrect: "✗ गलत", partial: "◐ आधा", unclear: "? साफ़ नहीं" };
const CELL = {
  "needs support": ["मदद चाहिए", "ns"],
  "on track": ["ठीक", "ok"],
  "not enough evidence": ["—", "ne"],
};

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
  const t = document.createElement("div");
  t.className = "toast"; t.textContent = msg; document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

// ---------- roster helpers ----------
const kid = (id) => (S.me?.roster || []).find((c) => c.child_id === id);
function nameOf(id) {
  const c = kid(id); if (!c) return id || "?";
  const dup = S.me.roster.filter((x) => x.first_name === c.first_name).length > 1;
  return dup ? `${c.first_name} (${c.roll_no})` : c.first_name;
}
const skillOf = (code) => (S.me?.skills.skills || []).find((s) => s.code === code);
const skillHi = (code) => skillOf(code)?.label_hi || code || "";
const skillEn = (code) => skillOf(code)?.label_en || "";
const initial = (id) => (kid(id)?.first_name || "?").slice(0, 1);

// ---------- offline queue (IndexedDB) ----------
function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open("suno", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("queue", { keyPath: "id", autoIncrement: true });
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
}
async function qAll() { const d = await idb(); return new Promise((res) => { const t = d.transaction("queue").objectStore("queue").getAll(); t.onsuccess = () => res(t.result || []); }); }
async function qAdd(item) { const d = await idb(); return new Promise((res) => { const t = d.transaction("queue", "readwrite").objectStore("queue").add(item); t.onsuccess = () => res(t.result); }); }
async function qDel(id) { const d = await idb(); return new Promise((res) => { const t = d.transaction("queue", "readwrite").objectStore("queue").delete(id); t.onsuccess = () => res(); }); }

async function flushQueue() {
  if (!navigator.onLine || !S.me) return;
  const items = await qAll();
  for (const it of items) {
    try {
      const { note_id } = await postNote(it);
      await qDel(it.id);
      toast("फ़ोन में रखा नोट भेज दिया · queued note sent");
      pollNote(note_id);
    } catch (e) { if (!e.status) break; if (e.status >= 400 && e.status < 500) await qDel(it.id); }
  }
  renderQueueBadge();
}
async function renderQueueBadge() {
  const n = (await qAll()).length; const el = $("#qcount");
  if (el) el.innerHTML = n ? `<div class="card small">📥 ${n} नोट फ़ोन में रखे हैं, नेटवर्क आने पर अपने आप जाएँगे <span class="en">· ${n} note(s) saved offline; they send when you are back online</span></div>` : "";
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
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});

async function boot() {
  try {
    S.me = await api("/api/me");
    localStorage.setItem("suno_me", JSON.stringify(S.me));
    shell();
  } catch (e) {
    if (!e.status && localStorage.getItem("suno_me")) { S.me = JSON.parse(localStorage.getItem("suno_me")); shell(); return; }
    renderLogin();
  }
}

// ---------- login ----------
function renderLogin(err = "") {
  $("#app").innerHTML = `
  <div class="login">
    <div class="hero">
      <div class="logo">SUNO <b>सुनो</b></div>
      <p>कक्षा के बाद 60 सेकंड बोलिए। अगली सुबह 2 मिनट में सुनिए किसे किस चीज़ में मदद चाहिए।<br>
      <span class="en">Speak for 60 seconds after class. Next morning, hear in 2 minutes who needs help with what.</span></p>
    </div>
    <div class="card">
      <label class="small">कोड डालें <span class="en">· access code</span></label>
      <input id="code" type="text" autocomplete="off" placeholder="SUNO-DEMO">
      <div class="demo-hint">जज/समीक्षक: डेमो कोड <b>SUNO-DEMO</b> <span class="en">· Reviewers: demo code <b>SUNO-DEMO</b>. Every login gets its own fresh copy of a synthetic Grade 2 class.</span></div>
      <button class="btn block" id="go">खोलें <span class="en" style="color:#c6cbe6">· open</span></button>
      <div class="err">${esc(err)}</div>
    </div>
    <details class="card"><summary>अपनी कक्षा बनाएँ <span class="en">· create your own class</span></summary>
      <div style="margin-top:10px">
        <input id="cname" type="text" placeholder="कक्षा का नाम, जैसे: कक्षा 2-अ">
        <select id="cgrade" style="margin-top:8px"><option value="1">कक्षा 1</option><option value="2" selected>कक्षा 2</option><option value="3">कक्षा 3</option></select>
        <button class="btn block alt" id="create" style="margin-top:8px">कक्षा बनाएँ <span class="en">· create</span></button>
        <p class="small muted">अगले कदम में बच्चों के नाम: रजिस्टर की फ़ोटो से या लिखकर। <span class="en">Next: add the children, from a photo of your attendance register or by typing.</span></p>
      </div>
    </details>
  </div>`;
  $("#go").onclick = async () => {
    const code = $("#code").value.trim() || "SUNO-DEMO";
    $("#go").disabled = true;
    try {
      await api("/api/login", { method: "POST", json: { code } });
      ["suno_me", "suno_today", "suno_class"].forEach((k) => localStorage.removeItem(k));
      if (window.caches) await caches.delete("suno-api-v1");
      S.today = null; await boot();
    }
    catch (e) { renderLogin(e.status === 401 ? "यह कोड नहीं मिला · code not recognised" : "नेटवर्क नहीं है · no network"); }
  };
  $("#code").onkeydown = (e) => { if (e.key === "Enter") $("#go").click(); };
  $("#create").onclick = async () => {
    try {
      const r = await api("/api/classes", { method: "POST", json: { name: $("#cname").value || "मेरी कक्षा", grade: +$("#cgrade").value } });
      ["suno_me", "suno_today", "suno_class"].forEach((k) => localStorage.removeItem(k)); S.today = null;
      alert(`आपकी कक्षा का कोड: ${r.code}\nYour class code: ${r.code}\n\nइसे लिखकर रखें: दूसरे फ़ोन पर इसी कोड से खुलेगा। · Write it down: it opens your class on any phone.`);
      await boot();
    } catch (e) { toast(e.message); }
  };
}

// ---------- shell ----------
function hiOnly() {
  const v = localStorage.getItem("suno_hi_only_" + S.me.class_id);
  return v === null ? !S.me.synthetic : v === "1";
}
function shell() {
  document.body.classList.toggle("hi-only", hiOnly());
  $("#app").innerHTML = `
  <header class="top"><div class="row">
    <div><div class="logo">SUNO<b>सुनो</b></div></div>
    <div class="cls"><div>${esc(S.me.name)}</div><div id="hdate" class="en" style="color:#c6cbe6"></div></div>
    <div class="spacer"></div>
    ${S.me.synthetic ? `<span class="chip-syn" title="Synthetic demo data: fictional children">SYNTHETIC DEMO</span>` : ""}
    <button class="btn-ghost" id="menu">⋯</button>
  </div></header>
  <div id="offline"></div>
  <main class="wrap" id="view"></main>
  <nav class="tabs">
    <button data-t="today"><span class="ic">☀️</span>आज<span class="en">Today</span></button>
    <button data-t="speak"><span class="ic">🎙️</span>बोलिए<span class="en">Note</span></button>
    <button data-t="class"><span class="ic">👧🏽</span>कक्षा<span class="en">Class</span></button>
    <button data-t="notes"><span class="ic">🗂️</span>नोट्स<span class="en" id="notes-tab">Notes</span></button>
  </nav>`;
  document.querySelectorAll("nav.tabs button").forEach((b) => (b.onclick = () => go(b.dataset.t)));
  $("#menu").onclick = openMenu;
  renderOffline();
  go(S.tab);
  flushQueue();
}
function renderOffline() {
  const el = $("#offline"); if (!el) return;
  el.innerHTML = S.online ? "" : `<div class="offline-bar">ऑफ़लाइन: पिछला सार और रिकॉर्डिंग चलती रहेगी · Offline: last brief and recording still work</div>`;
}
function go(tab) {
  S.tab = tab;
  document.querySelectorAll("nav.tabs button").forEach((b) => b.classList.toggle("on", b.dataset.t === tab));
  Object.values(S.polling).forEach(clearTimeout); S.polling = {};
  ({ today: renderToday, speak: renderSpeak, class: renderClass, notes: renderNotes })[tab]();
  window.scrollTo(0, 0);
}
function fmtDay(iso) {
  try { return new Date(iso + "T00:00:00").toLocaleDateString("hi-IN", { weekday: "long", day: "numeric", month: "long" }); }
  catch (_) { return iso; }
}

function openMenu() {
  sheet(`
    <h2>${esc(S.me.name)}</h2>
    ${S.me.code ? `<p class="small">कक्षा कोड <span class="en">· class code</span>: <b style="font-family:var(--sans);font-size:18px;letter-spacing:1px">${esc(S.me.code)}</b><br><span class="muted">इसी कोड से किसी भी फ़ोन पर खुलेगा · opens your class on any phone</span></p>` : ""}
    ${S.me.synthetic ? `<p class="small">यह डेमो कक्षा है: सारे बच्चे और नोट काल्पनिक हैं। <span class="en">Demo class: every child and note is synthetic, written by Team Sunvai and run through the real pipeline.</span></p>` : ""}
    <div class="menu-list">
      <button class="btn alt block" id="m-roster">👧🏽 बच्चों की सूची (${S.me.roster.length}) <span class="en">· children</span></button>
      <button class="btn alt block" id="m-lesson">📖 इस हफ़्ते का पाठ <span class="en">· this week's words</span></button>
      <button class="btn alt block" id="m-lang">${hiOnly() ? "🔤 अंग्रेज़ी भी दिखाएँ · show English" : "🔤 सिर्फ़ हिंदी · Hindi only"}</button>
      <button class="btn alt block" id="m-howto">❓ SUNO कैसे काम करता है <span class="en">· how SUNO works</span></button>
      <button class="btn alt block" id="m-out">बाहर निकलें <span class="en">· sign out</span></button>
    </div>`);
  $("#m-roster").onclick = openRoster;
  $("#m-lesson").onclick = openLesson;
  $("#m-lang").onclick = () => { localStorage.setItem("suno_hi_only_" + S.me.class_id, hiOnly() ? "0" : "1"); closeSheet(); shell(); };
  $("#m-out").onclick = async () => {
    try { await api("/api/logout", { method: "POST" }); } catch (_) {}
    ["suno_me", "suno_today", "suno_class"].forEach((k) => localStorage.removeItem(k));
    if (window.caches) await caches.delete("suno-api-v1");
    closeSheet(); renderLogin();
  };
  $("#m-howto").onclick = () => sheet(HOWTO);
}
const HOWTO = `
<h2>SUNO कैसे काम करता है <span class="en">How SUNO works</span></h2>
<ol class="small">
<li><b>सुबह:</b> 2 मिनट का हिंदी सार, और आज किन 5 बच्चों को सुनना है, किस शब्द या सवाल से। <span class="en">Morning: a 2-minute Hindi brief, and 5 children to listen to today, each with one item from this week's lesson.</span></li>
<li><b>कक्षा में:</b> आप वैसे ही पढ़ाएँ। फ़ोन बैग में रहे। कोई रिकॉर्डिंग नहीं। <span class="en">In class: teach as usual. Nothing records the classroom; no child's voice is captured.</span></li>
<li><b>कक्षा के बाद:</b> 60 सेकंड का वॉइस नोट: किसने क्या पढ़ा, कहाँ अटका, कौन नहीं आया। <span class="en">After class: a 60-second voice note in your own words.</span></li>
<li><b>SUNO:</b> Sarvam आवाज़ को लिखता है; Claude हर बच्चे की बात अलग करता है; कोड नाम, शब्द और भरोसा जाँचता है। <span class="en">Sarvam transcribes; Claude splits the note into per-child observations; code checks every name against the roster, every word against your transcript, and computes confidence. Opinions ("he is good", "she is weak") never become evidence: they become "listen again tomorrow".</span></li>
<li><b>नाम</b> तीन या ज़्यादा पक्की बातों और कम से कम दो दिन के बाद ही "मदद चाहिए" में आता है। <span class="en">A child is named only after 3+ checked observations over 2+ days.</span></li>
</ol>
<p class="en">No teacher score exists. Only you see this. Voice notes are deleted after transcription.</p>`;

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
    if (e.status === 401) return renderLogin();
    S.today = JSON.parse(localStorage.getItem("suno_today") || "null");
  }
  return S.today;
}

async function renderToday() {
  const v = $("#view");
  if (!S.today) v.innerHTML = `<p class="muted" style="padding:30px 0;text-align:center"><span class="spin"></span></p>`;
  const t = await loadToday();
  if (S.tab !== "today" || !t) return;
  $("#hdate").textContent = fmtDay(t.today);
  const b = t.brief;
  const fresh = !S.me.synthetic && !t.heard_this_week.length && !t.notes_today.length;
  if (!S.me.synthetic && !S.me.roster.length) {
    v.innerHTML = `<div class="card onboard" style="margin-top:16px"><b>नमस्ते! पहले बच्चों के नाम जोड़ें।</b>
      <p class="small">रजिस्टर के पन्ने की फ़ोटो लीजिए, SUNO नाम पढ़ लेगा; या नाम लिख दीजिए। <span class="en">Take a photo of your attendance register page, or type the names.</span></p>
      <button class="btn warn block" id="ob-roster">👧🏽 बच्चों के नाम जोड़ें <span class="en" style="color:var(--ink2)">· add children</span></button></div>`;
    $("#ob-roster").onclick = () => openRoster();
    return;
  }
  v.innerHTML = `
    ${fresh ? `<div class="card onboard" style="margin-top:14px"><b>SUNO ऐसे चलता है</b> <span class="en">· how it works</span>
      <ol class="small"><li>नीचे दिए 5 बच्चों को आज पढ़ते समय ध्यान से सुनिए, हर एक से दो शब्द।</li>
      <li>कक्षा के बाद "बोलिए" दबाकर 1 मिनट बताइए: किसने क्या पढ़ा, कहाँ अटका, कौन नहीं आया।</li>
      <li>कल सुबह 2 मिनट का सार सुनिए: किसे किस चीज़ में मदद चाहिए, और आज क्या करें।</li></ol>
      <p class="small">पहले <button class="link" id="ob-lesson">इस हफ़्ते के पाठ के शब्द</button> देख लें। <span class="en">First check this week's words.</span></p></div>` : ""}
    ${briefCard(b, t)}
    <h2>आज इन्हें सुनिए <span class="en">Listen to these today</span></h2>
    <div class="card">${t.listen_today.length ? t.listen_today.map(listenRow).join("") : `<p class="muted">सब बच्चों के बारे में ताज़ा जानकारी है। <span class="en">Everyone has recent evidence.</span></p>`}
      <p class="en" style="margin:8px 0 0">Chosen by code: claims to confirm first, then children SUNO knows least about. Not the same child two days running.</p>
    </div>
    <button class="btn warn block" id="to-speak">🎙️ कक्षा के बाद नोट बोलिए <span class="en" style="color:var(--ink2)">· speak today's note</span></button>
    ${t.open_questions ? `<div class="card q-card" style="margin-top:12px">❓ ${t.open_questions} नाम साफ़ नहीं थे, एक टैप में बताइए <span class="en">· ${t.open_questions} name(s) need one tap</span> <button class="link" id="to-notes">देखें · open</button></div>` : ""}
    ${t.language_flags.length ? `<h2>घर की भाषा <span class="en">Home language</span></h2><div class="card small">${t.language_flags.map((f) => `<div>🗣️ <b>${esc(nameOf(f.child_id))}</b>: ${f.signal === "helped" ? "घर की भाषा में समझाने पर समझ गया/गई" : "पढ़ाई की भाषा समझने में दिक्कत"} <span class="en">· ${f.signal === "helped" ? "understood once explained in the home language: the gap may be language, not the concept" : "the language of instruction is a barrier"}</span></div>`).join("")}</div>` : ""}
    <h2>5 दिन से नहीं सुना <span class="en">Silence Ledger · not described for 5 school days</span></h2>
    <div class="chips">${t.silent.length ? t.silent.map((c) => `<span>${esc(nameOf(c))}</span>`).join("") : `<span class="muted">कोई नहीं · nobody</span>`}</div>
    ${S.me.synthetic ? `
    <div class="card" style="margin-top:18px">
      <b>डेमो: अगली सुबह</b> <span class="en">· Demo: next morning</span>
      <p class="small muted" style="margin:4px 0 10px">नोट भेजने के बाद, घड़ी अगले स्कूल दिन पर ले जाइए; SUNO उस सुबह का सार बनाएगा (लगभग 30 सेकंड)। <span class="en">After sending a note, move this demo class to the next school morning; SUNO builds that morning's brief live (about 30 s).</span></p>
      <button class="btn alt block" id="nextday">अगली सुबह → <span class="en">· next morning</span></button>
    </div>` : ""}`;
  $("#to-speak").onclick = () => go("speak");
  $("#ob-lesson") && ($("#ob-lesson").onclick = openLesson);
  $("#to-notes") && ($("#to-notes").onclick = () => go("notes"));
  $("#nextday") && ($("#nextday").onclick = async () => {
    $("#nextday").disabled = true;
    try { await api("/api/next-day", { method: "POST" }); S.me.day_offset++; renderToday(); } catch (e) { toast(e.message); $("#nextday").disabled = false; }
  });
  $("#mkbrief") && ($("#mkbrief").onclick = async () => { try { await api("/api/brief" + (b ? "?force=true" : ""), { method: "POST" }); renderToday(); } catch (e) { toast(e.message); } });
  wirePlayer();
  if (b && ["queued", "thinking", "speaking"].includes(b.status)) S.polling.today = setTimeout(renderToday, 2500);
}

function briefCard(b, t) {
  const date = `<div class="date">${esc(fmtDay(t.today))}</div>`;
  if (!b) return `<div class="card brief"><h3>आज का सार <span class="en">Today's brief</span></h3>${date}
      <p class="small" style="opacity:.85">अभी सार नहीं बना है। <span class="en">No brief for this morning yet.</span></p>
      <button class="btn warn" id="mkbrief">सार बनाइए <span class="en" style="color:var(--ink2)">· build it</span></button></div>`;
  if (["queued", "thinking", "speaking"].includes(b.status)) {
    const step = { queued: "शुरू हो रहा है", thinking: "Claude सार लिख रहा है, कोड जाँच रहा है", speaking: "आवाज़ बन रही है" }[b.status];
    return `<div class="card brief"><h3>आज का सार <span class="en">Today's brief</span></h3>${date}
      <p style="margin-top:12px"><span class="spin"></span> ${step}… <span class="en">${{ queued: "starting", thinking: "Claude is writing it; code is checking it", speaking: "making the voice" }[b.status]}</span></p></div>`;
  }
  if (b.status === "fallback" || !b.brief) {
    return `<div class="card brief"><h3>आज का सार <span class="en">Today's brief</span></h3>${date}
      <p class="small">सार की भाषा जाँच में पास नहीं हुई, इसलिए सिर्फ़ पक्की बातें दिखा रहे हैं। <span class="en">The wording failed the checks twice, so SUNO shows only the code-checked facts (fail closed).</span></p>
      <ul class="stuck">${t.needs_support.map((x) => `<li><b>${esc(nameOf(x.child_id))}</b>: ${esc(skillHi(x.skill_code))} में मदद चाहिए</li>`).join("") || "<li>अभी किसी के बारे में पक्का नहीं</li>"}</ul>
      <button class="btn warn" id="mkbrief" style="margin-top:10px">फिर से बनाइए · retry</button></div>`;
  }
  const br = b.brief;
  const acts = S.me.activities;
  return `<div class="card brief">
    <h3>आज का सार <span class="en">Today's brief</span></h3>${date}
    ${b.audio_url ? `<div class="play"><button class="big" id="playbtn" aria-label="play">▶</button>
      <div style="flex:1"><div class="meta">सुनिए <span class="en">· listen</span> <span id="ptime" class="en"></span></div><progress id="pprog" value="0" max="1"></progress></div>
      <audio id="baudio" preload="auto" src="${esc(b.audio_url)}"></audio></div>` : `<p class="small" style="opacity:.8">🔇 आवाज़ उपलब्ध नहीं; नीचे पढ़ें <span class="en">· voice unavailable, read below</span></p>`}
    ${br.stuck_where.length ? `<ul class="stuck">${br.stuck_where.map((s) => `<li><b>${s.child_ids.map(nameOf).map(esc).join(", ")}</b> · ${esc(skillHi(s.skill_code))}<br><span style="opacity:.92">${esc(s.what_hi)}</span></li>`).join("")}</ul>`
      : `<p class="small" style="opacity:.85">अभी किसी बच्चे के बारे में "मदद चाहिए" कहने लायक पक्का सबूत नहीं। <span class="en">Not enough evidence yet to name anyone.</span></p>`}
    ${br.today.map((g) => { const a = acts.find((x) => x.activity_id === g.activity_id) || {};
      return `<div class="group"><b>आज ${g.minutes} मिनट: ${esc(a.title || g.activity_id)}</b> <span class="en">${esc(a.title_en || "")}</span><br>${g.child_ids.map(nameOf).map(esc).join(", ")}
      <details><summary>कैसे करें <span class="en">· steps</span></summary><div class="small" style="margin-top:6px">${esc(a.steps || "")}</div></details></div>`; }).join("")}
    <details><summary>पूरा सार पढ़ें <span class="en">· read the full brief</span></summary><div class="brief-text">${esc(br.text_hi)}</div></details>
    <details><summary>In English</summary><div class="brief-text en" style="color:#dfe3f6;font-size:14px">${esc(br.summary_en)}</div></details>
    ${b.problems_fixed && b.problems_fixed.length ? `<details><summary class="en" style="color:#c6cbe6">Guardrail: the first draft was rejected</summary><div class="small en" style="color:#c6cbe6">${b.problems_fixed.map(esc).join("<br>")}</div></details>` : ""}
    <div style="margin-top:10px"><button class="link" id="mkbrief" style="color:#c6cbe6;font-size:12px">सार फिर से बनाइए · rebuild</button></div>
  </div>`;
}

function wirePlayer() {
  const a = $("#baudio"), btn = $("#playbtn"); if (!a || !btn) return;
  const fmt = (s) => isFinite(s) ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}` : "";
  a.onloadedmetadata = () => ($("#ptime").textContent = "· " + fmt(a.duration));
  a.ontimeupdate = () => { $("#pprog").value = a.duration ? a.currentTime / a.duration : 0; };
  a.onended = () => (btn.textContent = "▶");
  btn.onclick = () => { if (a.paused) { a.play(); btn.textContent = "❚❚"; } else { a.pause(); btn.textContent = "▶"; } };
}

function listenRow(x) {
  const [hi, en] = REASON[x.reason] || ["", ""];
  return `<div class="listen"><div class="av">${esc(initial(x.child_id))}</div>
    <div class="who"><div class="name">${esc(nameOf(x.child_id))}</div>
      <div class="small muted">${esc(skillHi(x.skill_code))} <span class="en">· ${esc(skillEn(x.skill_code))}</span></div>
      <span class="reason ${x.reason}">${hi} <span class="en">· ${en}</span></span>
      ${x.reason === "confirm" && x.said ? `<div class="en" style="margin-top:2px">you said: “${esc(x.said)}”</div>` : ""}</div>
    <div style="text-align:right"><div class="item">${esc(x.item)}</div>${x.also ? `<div class="item also">फिर · ${esc(x.also.item)}</div>` : ""}</div></div>`;
}

// ---------- SPEAK ----------
let REC = null;
async function renderSpeak() {
  const v = $("#view");
  const t = S.today || (await loadToday());
  if (S.tab !== "speak") return;
  const list = t ? t.listen_today : [];
  v.innerHTML = `
    <h2>आज का नोट <span class="en">Today's note</span></h2>
    <div class="card">
      <div class="small">60 सेकंड, अपनी भाषा में: किसने क्या पढ़ा, कहाँ अटका, कौन नहीं आया। <span class="en">About 60 seconds, in your own words: who read what, where they got stuck, who was absent.</span></div>
      ${list.length ? `<div class="small" style="margin-top:8px"><b>आज की सूची</b> <span class="en">· today's list</span>:</div>
      <ul class="prompt-list">${list.map((x) => `<li><b>${esc(nameOf(x.child_id))}</b> · ${esc(x.item)}${x.also ? ` → ${esc(x.also.item)}` : ""}</li>`).join("")}</ul>` : ""}
      <div class="en">Example: “आज पिंकी ने कमल को क-म-ल पढ़ा, जोड़ नहीं पाई। अमन ने पानी सही पढ़ा। सुरेश नहीं आया।”</div>
    </div>
    <div class="rec-wrap">
      <button class="mic" id="mic" aria-label="record">🎙️</button>
      <div class="timer" id="timer">0:00</div>
      <div class="small muted" id="rec-hint">दबाइए और बोलिए · tap and speak</div>
    </div>
    <div id="qcount"></div>
    <div id="progress"></div>
    <details class="card"><summary>टाइप करें <span class="en">· type instead</span></summary>
      <textarea id="ntext" placeholder="आज पिंकी ने कमल को क म ल पढ़ा, जोड़ नहीं पाई…"></textarea>
      <button class="btn block" id="send-text" style="margin-top:8px">भेजें <span class="en" style="color:#c6cbe6">· send</span></button>
    </details>
    <details class="card" id="samples"><summary>नमूना नोट <span class="en">· sample notes for reviewers (synthetic)</span></summary><div id="sample-list" class="small" style="margin-top:8px"><span class="spin"></span></div></details>`;
  $("#mic").onclick = toggleRec;
  $("#send-text").onclick = async () => {
    const text = $("#ntext").value.trim(); if (!text) return toast("नोट लिखें · type a note");
    await sendNote({ text, day: t?.today }); $("#ntext").value = "";
  };
  $("#samples").ontoggle = loadSamples;
  renderQueueBadge();
}

async function loadSamples() {
  const el = $("#sample-list"); if (!el || el.dataset.loaded) return;
  try {
    const s = await api("/api/samples"); el.dataset.loaded = 1;
    el.innerHTML = s.notes.map((n, i) => `
      <div style="padding:8px 0;border-top:1px solid var(--line)">
        <b>${esc(n.title)}</b> <span class="en">· ${esc(n.title_en)}</span>
        <div class="sent" style="margin:4px 0">${esc(n.text)}</div>
        ${n.audio ? `<audio controls preload="none" src="${esc(n.audio)}" style="width:100%;height:34px"></audio>` : ""}
        <div style="display:flex;gap:8px;margin-top:6px">
          ${n.audio ? `<button class="btn alt" data-s="${i}" data-mode="audio">🎙️ आवाज़ भेजें <span class="en">· send audio</span></button>` : ""}
          <button class="btn alt" data-s="${i}" data-mode="text">⌨️ टेक्स्ट भेजें <span class="en">· send text</span></button>
        </div></div>`).join("") + `<p class="en">${esc(s.label || "")}</p>`;
    el.querySelectorAll("button[data-s]").forEach((b) => (b.onclick = async () => {
      const n = s.notes[+b.dataset.s];
      if (b.dataset.mode === "audio") {
        const blob = await (await fetch(n.audio)).blob();
        await sendNote({ blob, filename: n.audio.split("/").pop(), day: S.today?.today });
      } else await sendNote({ text: n.text, day: S.today?.today });
    }));
  } catch (e) { el.textContent = "नमूने नहीं मिले · samples unavailable"; }
}

async function toggleRec() {
  if (REC) return REC.stop();
  if (!navigator.mediaDevices?.getUserMedia) return toast("इस ब्राउज़र में रिकॉर्डिंग नहीं · recording not supported here");
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
  catch (_) { return toast("माइक की अनुमति दें · please allow the microphone"); }
  const mime = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", ""].find((m) => !m || MediaRecorder.isTypeSupported(m));
  const mr = new MediaRecorder(stream, mime ? { mimeType: mime, audioBitsPerSecond: 32000 } : undefined);
  const chunks = []; const t0 = Date.now();
  mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const tick = setInterval(() => {
    const s = Math.floor((Date.now() - t0) / 1000);
    $("#timer") && ($("#timer").textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
    if (s >= 175) mr.stop();
  }, 250);
  mr.onstop = async () => {
    clearInterval(tick); stream.getTracks().forEach((tr) => tr.stop());
    REC = null; $("#mic")?.classList.remove("on"); $("#rec-hint") && ($("#rec-hint").textContent = "दबाइए और बोलिए · tap and speak");
    const secs = (Date.now() - t0) / 1000;
    if (secs < 1.5) return toast("बहुत छोटा नोट · too short");
    const type = mr.mimeType || "audio/webm";
    const blob = new Blob(chunks, { type });
    await sendNote({ blob, filename: type.includes("mp4") ? "note.m4a" : type.includes("ogg") ? "note.ogg" : "note.webm", day: S.today?.today });
  };
  mr.start(1000); REC = mr;
  $("#mic").classList.add("on"); $("#rec-hint").textContent = "बोल रहे हैं… रोकने के लिए दबाइए · recording, tap to stop";
}

async function sendNote(it) {
  const prog = $("#progress");
  try {
    const { note_id } = await postNote(it);
    pollNote(note_id, prog);
  } catch (e) {
    if (!e.status) {
      await qAdd({ ...it, created: Date.now() });
      toast("नेटवर्क नहीं: नोट फ़ोन में रखा · offline: saved on the phone");
      renderQueueBadge();
    } else toast(e.message);
  }
}

function progressHtml(status, isAudio) {
  const order = isAudio ? ["transcribing", "thinking", "done"] : ["thinking", "done"];
  const labels = { transcribing: ["आवाज़ से लिख रहे हैं", "Sarvam speech-to-text"], thinking: ["हर बच्चे की बात अलग कर रहे हैं, जाँच रहे हैं", "Claude extracts observations · code checks names, words, confidence"], done: ["तैयार", "ready"] };
  const idx = order.indexOf(status === "queued" ? order[0] : status);
  return `<div class="card"><ul class="steps">${order.map((s, i) => `<li class="${i < idx || status === "done" ? "done" : i === idx ? "now" : "todo"}">${labels[s][0]} <span class="en">· ${labels[s][1]}</span></li>`).join("")}</ul></div>`;
}

async function pollNote(id, el) {
  let n;
  try { n = await api(`/api/notes/${id}`); } catch (e) { return; }
  if (el && document.body.contains(el)) {
    if (n.status === "failed") el.innerHTML = `<div class="card q-card">नोट समझ नहीं पाए: ${esc(n.error)} <span class="en">· the note could not be processed</span></div>`;
    else if (n.status !== "done") el.innerHTML = progressHtml(n.status, n.source === "audio");
    else { el.innerHTML = `<h2>SUNO ने क्या समझा <span class="en">What SUNO understood</span></h2>` + noteBody(n); wireNote(el, n); S.today = null; }
  }
  if (!["done", "failed"].includes(n.status)) S.polling["n" + id] = setTimeout(() => pollNote(id, el), 1500);
  else if (n.status === "done" && !el) toast("नोट तैयार · note processed");
}

// ---------- note view (shared) ----------
function recCard(r) {
  const st = r.kind === "opinion" && r.status === "check_tomorrow" ? ["राय, सबूत नहीं: कल सुनें", "opinion, not evidence: listen tomorrow"] : STATUS[r.status] || [r.status, ""];
  const who = r.child_id ? nameOf(r.child_id) : `“${r.name_said || "?"}”`;
  const what = r.kind === "absent" ? "आज अनुपस्थित · absent today"
    : `${r.skill_code ? esc(skillHi(r.skill_code)) : ""}${r.item ? ` · <b>${esc(r.item)}</b>` : ""} ${r.kind === "observation" ? OUTCOME[r.outcome] || "" : ""}`;
  const conf = r.confidence == null ? "" : `<div class="conf"><span>भरोसा · confidence ${(r.confidence * 100).toFixed(0)}%</span><div class="bar"><i style="width:${Math.round(r.confidence * 100)}%"></i><b style="left:75%"></b></div></div>`;
  const sig = r.signals ? `<details><summary class="en">why this score (computed in code)</summary><table class="signals">
      <tr><td>who</td><td>${esc(r.attribution)}</td></tr><tr><td>specific item named</td><td>${r.signals.specificity}</td></tr>
      <tr><td>what went wrong described</td><td>${r.signals.concreteness}</td></tr><tr><td>seen today</td><td>${r.signals.recency}</td></tr>
      <tr><td colspan="2">gate 0.75 · ${r.kind === "opinion" ? "opinions never become evidence" : "below the gate → listen again"}</td></tr></table></details>` : "";
  const fb = r.child_id && r.kind !== "absent" ? `<div class="fb">
      <button class="up ${r.feedback === "up" ? "on" : ""}" data-fb="up" data-r="${r.rec_id}">✓ सही समझा</button>
      <button class="down ${r.feedback === "down" ? "on" : ""}" data-fb="down" data-r="${r.rec_id}">✗ गलत समझा</button></div>` : "";
  return `<div class="card rec ${r.status}">
    <div class="head"><span class="name">${esc(who)}</span><span class="tag ${r.kind === "opinion" ? "opinion" : r.status}">${st[0]}</span><span class="en">${st[1]}</span></div>
    <div class="what">${what}</div>
    ${r.rationale ? `<div class="en">${esc(r.rationale)}</div>` : ""}
    ${r.home_language !== "none" && r.home_language ? `<div class="small">🗣️ ${r.home_language === "helped" ? "घर की भाषा में समझ गया/गई · understood in the home language" : "भाषा की दिक्कत · language barrier"}</div>` : ""}
    ${r.teacher_quote ? `<div class="quote">${esc(r.teacher_quote)}</div>` : ""}
    ${conf}${sig}${fb}</div>`;
}

function questionCard(q, n) {
  const rec = n.records.find((r) => r.mention_id === q.mention_id);
  if (q.answered_at) return "";
  const which = q.type === "which_child";
  const buttons = q.candidates.map((c) => `<button data-q="${q.q_id}" data-a="${c}">${esc(nameOf(c))}</button>`).join("");
  const others = S.me.roster.filter((c) => !q.candidates.includes(c.child_id));
  const select = which ? "" : `<select data-qsel="${q.q_id}"><option value="">${q.candidates.length ? "कोई और · someone else" : "बच्चा चुनें · choose a child"}</option>${others.map((c) => `<option value="${c.child_id}">${esc(nameOf(c.child_id))}</option>`).join("")}</select>`;
  const pick = buttons + select;
  const said = q.name_said || "नाम नहीं लिया";
  return `<div class="card q-card">
    <b>“${esc(said)}”</b>: ${which ? "कौन सा बच्चा?" : "यह कौन है?"} <span class="en">· ${which ? "this name matches more than one child" : q.name_said ? "this name is not on the roster" + (q.candidates.length ? "; closest-sounding names below" : "") : "no name was said"}</span>
    ${rec ? `<div class="small" style="margin-top:4px">${esc(skillHi(rec.skill_code))} ${rec.item ? "· " + esc(rec.item) : ""} ${OUTCOME[rec.outcome] || ""}</div>` : ""}
    <div class="opts">${pick}<button data-q="${q.q_id}" data-a="skip">छोड़ें · skip</button></div></div>`;
}

function noteBody(n) {
  const order = { unattributed: 0, evidence: 1, check_tomorrow: 2, absent: 3, dismissed: 4 };
  const recs = [...n.records].sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));
  const qs = n.questions.filter((q) => !q.answered_at);
  return `
    ${n.synthetic ? `<p class="en">Synthetic sample note.</p>` : ""}
    ${qs.map((q) => questionCard(q, n)).join("")}
    ${recs.filter((r) => r.status !== "unattributed" || (r.kind === "observation" && !n.questions.some((q) => q.mention_id === r.mention_id))).map(recCard).join("") || `<p class="muted">इस नोट में किसी बच्चे के बारे में बात नहीं मिली। <span class="en">No child-specific statements found.</span></p>`}
    ${n.follow_ups.length ? `<div class="card small"><b>अगली बार और साफ़ बताने के लिए</b> <span class="en">· to make it evidence next time</span>${n.follow_ups.map((f) => `<div style="margin-top:4px">• ${esc(f.question_hi)}</div>`).join("")}</div>` : ""}
    <details class="card"><summary>आपका नोट (लिखा हुआ) <span class="en">· your note as transcribed${n.seconds ? ` · ${n.seconds}s` : ""}</span></summary>
      <div style="margin-top:8px">${(n.sentences || []).map((s) => `<div class="sent"><span class="id">${s.sent_id}</span>${esc(s.text)}</div>`).join("")}</div></details>
    <button class="link" data-trace="${n.note_id}">SUNO ने कैसे तय किया (Claude + कोड) · how SUNO decided →</button>`;
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
      el.innerHTML = (el.id === "progress" ? `<h2>SUNO ने क्या समझा <span class="en">What SUNO understood</span></h2>` : noteHead(fresh)) + noteBody(fresh);
      wireNote(el, fresh); S.today = null; toast("धन्यवाद · thanks");
    } catch (e) { toast(e.message); }
  };
  el.querySelectorAll("button[data-q]").forEach((b) => (b.onclick = () => answer(b.dataset.q, b.dataset.a)));
  el.querySelectorAll("select[data-qsel]").forEach((s) => (s.onchange = () => s.value && answer(s.dataset.qsel, s.value)));
  el.querySelectorAll("button[data-trace]").forEach((b) => (b.onclick = () => openTrace(b.dataset.trace)));
}

// ---------- NOTES ----------
const noteHead = (n) => `<h2>${esc(fmtDay(n.day))} <span class="en">${n.source === "audio" ? "voice note" : "typed / sample note"}</span></h2>`;
async function renderNotes() {
  const v = $("#view");
  v.innerHTML = `<h2>नोट्स <span class="en">Notes</span></h2><div id="qcount"></div><div id="nl"><span class="spin"></span></div>`;
  renderQueueBadge();
  let notes;
  try { notes = await api("/api/notes"); } catch (e) { $("#nl").innerHTML = `<p class="muted">ऑफ़लाइन · offline</p>`; return; }
  if (S.tab !== "notes") return;
  $("#nl").innerHTML = notes.length ? notes.map((n) => `
    <div class="card note-row" data-n="${n.note_id}" style="cursor:pointer">
      <div class="t"><b>${esc(fmtDay(n.day))}</b><br><span class="muted">${esc((n.transcript || n.error || "…").slice(0, 80))}</span></div>
      <span class="status ${n.status}">${n.status === "done" ? "✓" : esc(n.status)}</span></div>`).join("")
    : `<p class="muted">अभी कोई नोट नहीं · no notes yet</p>`;
  document.querySelectorAll("[data-n]").forEach((r) => (r.onclick = () => openNote(r.dataset.n)));
}
async function openNote(id) {
  const sh = sheet(`<span class="spin"></span>`);
  const n = await api(`/api/notes/${id}`);
  sh.innerHTML = `<button class="close">×</button>` + noteHead(n) + noteBody(n) +
    `<div style="margin-top:18px"><button class="btn alt block" id="del-note">🗑️ यह नोट मिटाएँ <span class="en">· delete this note</span></button></div>`;
  $(".close", sh).onclick = closeSheet;
  wireNote(sh, n);
  $("#del-note").onclick = async () => {
    if (!confirm("यह नोट और इससे बनी सारी बातें मिट जाएँगी। मिटाएँ? · Delete this note and everything SUNO took from it?")) return;
    try { await api(`/api/notes/${id}`, { method: "DELETE" }); closeSheet(); S.today = null; toast("मिटा दिया · deleted"); renderNotes(); }
    catch (e) { toast(e.message); }
  };
}

async function openTrace(id) {
  const sh = sheet(`<span class="spin"></span>`);
  const t = await api(`/api/notes/${id}/trace`);
  const u = t.usage || {}, tm = t.timings || {};
  sh.innerHTML = `<button class="close">×</button>
    <h2>SUNO ने कैसे तय किया <span class="en">How SUNO decided</span></h2>
    <p class="en">1 · Speech-to-text (Sarvam saaras:v4) → 2 · numbered sentences → 3 · Claude (claude-opus-5-5, adaptive thinking, JSON schema <code>${esc(t.schema_file)}</code>, prompt <code>${esc(t.prompt_file)}</code>) → 4 · code checks: every claim must cite her real sentences, the child is resolved from the roster by code and must agree with Claude, items must be in her words, labels are masked → 5 · confidence computed in code; gate 0.75.</p>
    <div class="card small en">Time: speech-to-text ${tm.speech_to_text_s ?? "–"} s · Claude ${tm.claude_s ?? "–"} s · Claude cost $${u.usd ?? "–"} (${u.input_tokens ?? 0} in, ${u.cache_read_tokens ?? 0} cached, ${u.output_tokens ?? 0} out)</div>
    <h2 class="en">Sentences</h2><div class="card">${(t.sentences || []).map((s) => `<div class="sent"><span class="id">${s.sent_id}</span>${esc(s.text)}</div>`).join("")}</div>
    <h2 class="en">Code checks (what code changed or refused)</h2>
    <div class="card small en">${(t.code_checks || []).length ? t.code_checks.map((p) => `• ${esc(p[0])}: <b>${esc(p[1])}</b> · ${esc(p[2])}`).join("<br>") : "Claude's output passed every check unchanged."}
    ${t.questions.length ? "<br>" + t.questions.map((q) => `• “${esc(q.name_said)}”: ${q.candidates.length ? "matches " + q.candidates.map(nameOf).join(" / ") : "not on the roster"} → asked the teacher${q.answer ? " → " + (q.answer === "skip" ? "skipped" : nameOf(q.answer)) : ""}`).join("<br>") : ""}</div>
    <h2 class="en">Final records (after code)</h2>
    <pre class="json">${esc(JSON.stringify(t.records.map((r) => ({ child: r.child_id ? nameOf(r.child_id) : null, said: r.name_said, kind: r.kind, skill: r.skill_code, item: r.item, outcome: r.outcome, error: r.error_type, attribution: r.attribution, signals: r.signals, confidence: r.confidence, status: r.status })), null, 1))}</pre>
    <h2 class="en">Claude's raw output (before code)</h2>
    <pre class="json">${esc(JSON.stringify(t.claude_output, null, 1))}</pre>`;
  $(".close", sh).onclick = closeSheet;
}

// ---------- CLASS ----------
async function renderClass() {
  const v = $("#view");
  v.innerHTML = `<h2>कक्षा की तस्वीर <span class="en">Class picture</span></h2><div id="cg"><span class="spin"></span></div>`;
  let c;
  try { c = await api("/api/class"); localStorage.setItem("suno_class", JSON.stringify(c)); }
  catch (e) { c = JSON.parse(localStorage.getItem("suno_class") || "null"); if (!c) { $("#cg").textContent = "ऑफ़लाइन · offline"; return; } }
  if (S.tab !== "class") return;
  const areas = S.me.skills.areas;
  const skills = S.me.skills.skills.filter((s) => s.area === S.area);
  const areaDef = areas.find((a) => a.area === S.area);
  const levelOf = (cid) => { const l = (c.levels[cid] || {})[S.area]; return l && l.level !== null && l.level !== undefined ? areaDef.levels[l.level] : null; };
  const groups = {};
  S.me.roster.forEach((ch) => { const l = levelOf(ch.child_id); if (l) (groups[l.label_hi] = groups[l.label_hi] || []).push(ch.child_id); });
  const silent = new Set(c.silent), lang = new Set(c.language_flags.map((f) => f.child_id));
  let ns = 0, ok = 0;
  Object.values(c.grid).forEach((row) => skills.forEach((s) => { const st = row[s.code].status; if (st === "needs support") ns++; if (st === "on track") ok++; }));
  $("#cg").innerHTML = `
    <div class="areas">${areas.map((a) => `<button data-a="${a.area}" class="${a.area === S.area ? "on" : ""}">${esc(a.label_hi)}</button>`).join("")}</div>
    ${Object.keys(groups).length ? `<div class="card small"><b>स्तर के हिसाब से समूह</b> <span class="en">· groups by level (Teaching at the Right Level)</span>
      ${areaDef.levels.filter((l) => groups[l.label_hi]).map((l) => `<div style="margin-top:4px"><span class="cell lvl">${esc(l.label_hi)}</span> ${groups[l.label_hi].map(nameOf).map(esc).join(", ")}</div>`).join("")}</div>` : ""}
    <div class="legend"><span><span class="cell ns">मदद चाहिए</span> needs support · ${ns}</span><span><span class="cell ok">ठीक</span> on track · ${ok}</span><span><span class="cell ne">—</span> अभी पता नहीं · not enough evidence</span></div>
    <div class="grid-wrap"><table class="grid">
      <tr><th class="n">बच्चा</th><th class="skill">स्तर<div class="en" style="font-size:10.5px">level</div></th>${skills.map((s) => `<th class="skill">${esc(s.label_hi)}<div class="en" style="font-size:10.5px">${esc(s.label_en)}</div></th>`).join("")}</tr>
      ${S.me.roster.map((ch) => `<tr data-c="${ch.child_id}"><td class="n">${esc(nameOf(ch.child_id))}${silent.has(ch.child_id) ? ' <span title="not described for 5 school days">🔇</span>' : ""}${lang.has(ch.child_id) ? ' <span title="home language">🗣️</span>' : ""}</td>
        <td>${levelOf(ch.child_id) ? `<span class="cell lvl">${esc(levelOf(ch.child_id).label_hi)}</span>` : `<span class="cell ne">—</span>`}</td>
        ${skills.map((s) => { const cell = c.grid[ch.child_id][s.code]; const [w, cls] = CELL[cell.status]; return `<td><span class="cell ${cls}" title="${cell.moments} observations, ${cell.days} days">${w}</span></td>`; }).join("")}</tr>`).join("")}
    </table></div>
    <p class="en">Level = the child's rung on the ladder, stated only when SUNO is sure (one observation tells it about several skills: a child who reads a sentence knows her letters). A cell changes from “—” only after 3+ checked observations on 2+ days. 🔇 = Silence Ledger (not described for 5 school days). 🗣️ = understood once explained in the home language. Tap a child for the evidence.</p>`;
  document.querySelectorAll(".areas button").forEach((b) => (b.onclick = () => { S.area = b.dataset.a; renderClass(); }));
  document.querySelectorAll("tr[data-c]").forEach((r) => (r.onclick = () => openChild(r.dataset.c)));
}

async function openChild(id) {
  const sh = sheet(`<span class="spin"></span>`);
  const d = await api(`/api/children/${id}`);
  const rows = S.me.skills.skills.filter((s) => d.grid[s.code].moments > 0 && (d.grid[s.code].status !== "not enough evidence" || d.grid[s.code].p !== null));
  const lv = S.me.skills.areas.filter((a) => d.levels[a.area]).map((a) => {
    const l = d.levels[a.area]; const nx = d.next_steps[a.area];
    return `<div style="padding:6px 0;border-top:1px solid var(--line)"><b>${esc(a.label_hi)}</b>: ${l.level !== null ? `<span class="cell lvl">${esc(a.levels[l.level].label_hi)}</span>` : `<span class="cell ne">स्तर अभी पक्का नहीं</span>`}
      ${nx ? ` · अगला कदम <span class="en">next step</span>: <b>${esc(skillHi(nx))}</b>` : ""} <span class="en">${l.moments} obs · ${l.days} days</span></div>`; }).join("");
  sh.innerHTML = `<button class="close">×</button>
    <h2>${esc(nameOf(id))} <span class="en">roll ${d.child.roll_no}</span></h2>
    ${d.language_flag ? `<div class="card small">🗣️ ${d.language_flag.signal === "helped" ? "घर की भाषा में समझाने पर समझ जाता/जाती है: दिक्कत भाषा की हो सकती है, समझ की नहीं।" : "पढ़ाई की भाषा समझने में दिक्कत।"} <span class="en">${d.language_flag.signal === "helped" ? "Understands once explained in the home language: the gap may be the language, not the concept." : "Language of instruction is a barrier."}</span></div>` : ""}
    ${lv ? `<div class="card small">${lv}</div>` : ""}
    <div class="card">${rows.length ? rows.map((s) => { const g = d.grid[s.code]; const [w, cls] = CELL[g.status];
      return `<div style="display:flex;justify-content:space-between;padding:5px 0"><span>${esc(s.label_hi)} <span class="en">${esc(s.label_en)}</span></span><span><span class="cell ${cls}">${w}</span> <span class="en">${g.moments} obs · ${g.days} days</span></span></div>`; }).join("")
      : `<p class="muted small">अभी कोई पक्की बात नहीं <span class="en">· no checked observations yet</span></p>`}</div>
    <h2>आपने क्या बताया <span class="en">What you said, newest first</span></h2>
    ${d.records.map((r) => `<div class="small muted" style="margin-top:8px">${esc(fmtDay(r.day))}</div>` + recCard(r)).join("") || `<p class="muted">अभी कुछ नहीं · nothing yet</p>`}`;
  $(".close", sh).onclick = closeSheet;
  wireNote(sh, { note_id: null, records: d.records });
}

// ---------- roster editor (typed, or from a photo of the attendance register) ----------
function openRoster(draft) {
  const rows = draft || S.me.roster.map((c) => ({ child_id: c.child_id, first_name: c.first_name, roll_no: c.roll_no,
    aliases: (c.aliases || []).filter((a) => !/^[A-Za-z]/.test(a)) }));
  const sh = sheet(`
    <h2>बच्चों की सूची <span class="en">Children</span></h2>
    <p class="small muted">सिर्फ़ पहला नाम। उपनाम (जैसे गुड्डू) अलग खाने में। <span class="en">First names only. A nickname goes in the second box.</span></p>
    <label class="btn warn block" style="margin:8px 0">📷 रजिस्टर की फ़ोटो से भरें <span class="en" style="color:var(--ink2)">· fill from a photo of the register</span>
      <input type="file" id="reg-photo" accept="image/*" capture="environment" style="display:none"></label>
    <div id="reg-status" class="small"></div>
    <div id="rows">${rows.map(rosterRow).join("")}</div>
    <button class="btn alt block" id="add-row" style="margin-top:6px">+ बच्चा जोड़ें <span class="en">· add a child</span></button>
    <button class="btn block" id="save-roster" style="margin-top:10px">सूची सहेजें <span class="en" style="color:#c6cbe6">· save</span></button>
    <p class="en">The photo is read by Claude and not stored. Surnames and fathers' names are dropped; you check the list before saving.</p>`);
  const wire = () => sh.querySelectorAll("button[data-del]").forEach((b) => (b.onclick = () => b.closest(".roster-row").remove()));
  wire();
  $("#add-row", sh).onclick = () => { $("#rows", sh).insertAdjacentHTML("beforeend", rosterRow({})); wire(); };
  $("#reg-photo", sh).onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    $("#reg-status", sh).innerHTML = `<span class="spin"></span> फ़ोटो पढ़ रहे हैं… <span class="en">reading the photo (Claude)</span>`;
    const fd = new FormData(); fd.append("photo", await shrink(f), "register.jpg");
    try {
      const r = await api("/api/roster/photo", { method: "POST", body: fd });
      const have = [...sh.querySelectorAll(".roster-row")].map(readRow).filter((x) => x.first_name);
      const added = r.children.map((c) => ({ first_name: c.first_name, roll_no: c.roll_no }));
      $("#rows", sh).innerHTML = [...have, ...added].map(rosterRow).join(""); wire();
      $("#reg-status", sh).innerHTML = `✓ ${r.children.length} नाम मिले${r.unreadable ? `, ${r.unreadable} पढ़े नहीं जा सके` : ""}. जाँचकर सहेजें। <span class="en">${esc(r.note || "")}</span>`;
    } catch (err) { $("#reg-status", sh).textContent = "फ़ोटो नहीं पढ़ी जा सकी: " + err.message; }
  };
  $("#save-roster", sh).onclick = async () => {
    const children = [...sh.querySelectorAll(".roster-row")].map(readRow).filter((x) => x.first_name);
    if (!children.length) return toast("कम से कम एक नाम लिखें · add at least one name");
    try {
      await api("/api/roster", { method: "PUT", json: { children } });
      S.me = await api("/api/me"); localStorage.setItem("suno_me", JSON.stringify(S.me));
      closeSheet(); toast(`${S.me.roster.length} बच्चे सहेजे · saved`); S.today = null; go(S.tab);
    } catch (err) { toast(err.message); }
  };
}
function rosterRow(c) {
  return `<div class="roster-row" data-id="${esc(c.child_id || "")}">
    <input class="roll" type="number" min="1" value="${esc(c.roll_no ?? "")}" placeholder="रोल">
    <input class="name" type="text" value="${esc(c.first_name || "")}" placeholder="पहला नाम">
    <input class="nick" type="text" value="${esc((c.aliases || [])[0] || "")}" placeholder="उपनाम">
    <button data-del aria-label="remove">✕</button></div>`;
}
function readRow(el) {
  const nick = $(".nick", el).value.trim();
  return { child_id: el.dataset.id || null, first_name: $(".name", el).value.trim(),
           roll_no: parseInt($(".roll", el).value, 10) || null, aliases: nick ? [nick] : [] };
}
async function shrink(file, max = 1600) {
  // Phone photos are large; send a smaller JPEG so it uploads on a weak connection.
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
  const L = S.me.lesson, areas = S.me.skills.areas;
  const sh = sheet(`
    <h2>इस हफ़्ते का पाठ <span class="en">This week's lesson</span></h2>
    <p class="small muted">इस हफ़्ते की किताब के शब्द और सवाल। SUNO इन्हीं से बताएगा कि किस बच्चे से क्या पढ़वाएँ। ✓ = इस हफ़्ते का मुख्य हिस्सा। <span class="en">Words and sums from this week's pages. SUNO picks today's listening items from these. ✓ = this week's focus.</span></p>
    <input id="l-title" type="text" value="${esc(L.title || "")}" placeholder="पाठ का नाम, जैसे: पाठ 12, कमल का फूल">
    ${areas.map((a) => `<h2 style="font-size:16px">${esc(a.label_hi)}</h2>` + S.me.skills.skills.filter((sk) => sk.area === a.area).map((sk) => `
      <div class="lesson-skill"><label><input type="checkbox" data-focus="${sk.code}" ${(L.focus_skills || []).includes(sk.code) ? "checked" : ""}> ${esc(sk.label_hi)} <span class="en">${esc(sk.label_en)}</span></label>
      <input type="text" data-items="${sk.code}" value="${esc((L.items[sk.code] || []).join(", "))}" placeholder="जैसे: ${esc(sk.example)}"></div>`).join("")).join("")}
    <button class="btn block" id="save-lesson" style="margin-top:12px">सहेजें <span class="en" style="color:#c6cbe6">· save</span></button>`);
  $("#save-lesson", sh).onclick = async () => {
    const items = {}, focus = [];
    sh.querySelectorAll("[data-items]").forEach((i) => { items[i.dataset.items] = i.value.split(/[,،\n]/).map((x) => x.trim()).filter(Boolean); });
    sh.querySelectorAll("[data-focus]").forEach((c) => c.checked && focus.push(c.dataset.focus));
    try {
      await api("/api/lesson", { method: "PUT", json: { title: $("#l-title", sh).value, focus_skills: focus, items } });
      S.me = await api("/api/me"); localStorage.setItem("suno_me", JSON.stringify(S.me));
      closeSheet(); toast("पाठ सहेजा · saved"); S.today = null; go(S.tab);
    } catch (err) { toast(err.message); }
  };
}

boot();
