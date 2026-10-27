// Screenshot the SUNO web app at phone size with headless Chrome (CDP, no dependencies).
// usage: node scripts/shoot.mjs <base_url> <outdir> [steps.json]
// Default steps: demo login, then each tab. A step is {eval?: "js", wait?: ms, shot?: "name", full?: bool}.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { resolve } from "node:path";

const [, , base = "http://localhost:8765", outdir = ".cache/shots", stepsFile] = process.argv;
mkdirSync(outdir, { recursive: true });
const PORT = 9334, prof = resolve(".cache/cdp-profile");
rmSync(prof, { recursive: true, force: true });
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ["--headless=new", "--disable-gpu", "--hide-scrollbars", `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let targets;
for (let i = 0; i < 50; i++) { try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json(); if (targets.length) break; } catch {} await sleep(200); }
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0; const pending = new Map();
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const W = 390, H = 844;
await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 2, mobile: true });
await send("Page.enable");
await send("Page.navigate", { url: base });
await sleep(1500);

const steps = stepsFile ? JSON.parse(readFileSync(stepsFile, "utf8")) : [
  { shot: "01-login" },
  { eval: "document.querySelector('#code').value='SUNO-DEMO'; document.querySelector('#go').click()", wait: 3000, shot: "02-today", full: true },
  { eval: "document.querySelector('[data-t=speak]').click()", wait: 1200, shot: "03-speak" },
  { eval: "document.querySelector('[data-t=class]').click()", wait: 1500, shot: "04-class", full: true },
  { eval: "document.querySelector('[data-t=notes]').click()", wait: 1500, shot: "05-notes" },
  { eval: "document.querySelector('[data-n]').click()", wait: 1500, shot: "06-note", full: true },
];
for (const s of steps) {
  if (s.eval) { const r = await send("Runtime.evaluate", { expression: s.eval, awaitPromise: true }); if (r.result?.exceptionDetails) console.error("eval failed:", s.eval, r.result.exceptionDetails.text); }
  await sleep(s.wait ?? 600);
  if (s.shot) {
    let clip;
    if (s.full) {
      const r = await send("Runtime.evaluate", { expression: "Math.max(document.documentElement.scrollHeight, (document.querySelector('.sheet')||{}).scrollHeight||0)", returnByValue: true });
      const h = Math.min(r.result.result.value || H, 4000);
      await send("Emulation.setDeviceMetricsOverride", { width: W, height: h, deviceScaleFactor: 2, mobile: true });
      await sleep(400);
    }
    const shot = await send("Page.captureScreenshot", { format: "png" });
    writeFileSync(`${outdir}/${s.shot}.png`, Buffer.from(shot.result.data, "base64"));
    if (s.full) await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 2, mobile: true });
    console.log("shot", s.shot);
  }
}
ws.close(); chrome.kill();
