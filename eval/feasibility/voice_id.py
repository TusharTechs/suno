"""Feasibility test F1: can SUNO tell which child answered, from voice alone?

The idea from the 20 Oct mentor call: each child records a short voice sample
once, and every later answer is matched against those samples. This script
measures how often that matching picks the right child.

How (SIMULATED classroom, REAL child voices):
- Voices: Pratham ASER recordings of real Hindi-speaking children (6-14), one
  session per child, ages 5-10. Enrolment = ~20 s of the child's other
  readings (paragraph first).
  Test answers = the same child's single-word and letter readings.
- Room: a 9 x 7 x 3.2 m classroom (RT60 0.8 s) simulated with
  pyroomacoustics. The phone is worn by the teacher at the front.
  The answering child sits 1, 2, 4 or 6 m away. Ten other children murmur
  around the room and a ceiling fan runs.
- Noise: "calm" = the answer is 12 dB above the room noise at 1 m;
  "noisy" = 3 dB. The level then falls naturally with distance.
- Matching: two pretrained speaker-embedding models (SpeechBrain ECAPA,
  Microsoft WavLM-SV), cosine similarity to each enrolled child.
- Classes of 5, 15 and 35 children, drawn from sessions recorded on the
  same device where possible.

Every number in the output comes from this script. The room is simulated,
so results are labelled SIMULATED wherever they appear.

    uv run --group speech python eval/feasibility/voice_id.py
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pyroomacoustics as pra
import soundfile as sf
import torch
from scipy.signal import fftconvolve

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/external/aser/manifest.csv"
OUT = ROOT / "eval/results"
CACHE = ROOT / ".cache"
SR = 16_000

ROOM_DIM = [9.0, 7.0, 3.2]
RT60 = 0.8                     # measured echo time we aim for (typical bare classroom)
RT60_SABINE = 0.5              # inverse_sabine target that gives a measured RT60 of ~0.8 s in this room
MIC = [4.5, 0.6, 1.3]          # phone on the teacher's chest, front of the room
CHILD_Z = 0.9                  # seated child's mouth height
DISTANCES = [1.0, 2.0, 4.0, 6.0]
ANGLES_DEG = [-20.0, 0.0, 20.0]
NOISE_SNR_AT_1M = {"calm": 12.0, "noisy": 3.0}
N_BABBLE = 10
BABBLE_REL_DB = -6.0           # murmuring children are softer than the one answering
FAN_REL_DB = -10.0             # fan relative to the murmur
CLASS_SIZES = [5, 15, 35]
WORD_LEVELS = {"WD", "L", "W", "CL", "SL"}
ENROL_LEVELS = ["ST", "P"]
PRECISION_TARGET = 0.90


# --------------------------------------------------------------------------- audio

def load(path: str) -> np.ndarray:
    x, sr = sf.read(ROOT / path, dtype="float32")
    assert sr == SR, path
    return x


def frame_db(x: np.ndarray, frame: int = 320) -> np.ndarray:
    n = max(len(x) // frame, 1)
    x = np.pad(x, (0, max(0, n * frame - len(x))))[: n * frame]
    return 10 * np.log10(np.mean(x.reshape(n, frame) ** 2, axis=1) + 1e-12)


def active_power(x: np.ndarray, frame: int = 320) -> float:
    """Mean power over frames within 30 dB of the loudest frame (speech-active)."""
    db = frame_db(x, frame)
    return float(np.mean(10 ** (db[db > db.max() - 30] / 10)))


def trim_active(x: np.ndarray, pad_s: float = 0.15, frame: int = 320) -> np.ndarray:
    """Keep the span from the first to the last speech-active frame (a clean VAD)."""
    db = frame_db(x, frame)
    idx = np.flatnonzero(db > db.max() - 30)
    pad = int(pad_s * SR)
    return x[max(0, idx[0] * frame - pad): min(len(x), (idx[-1] + 1) * frame + pad)]


def norm_active(x: np.ndarray) -> np.ndarray:
    return x / math.sqrt(active_power(x) + 1e-12)


def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.arange(len(spec)); f[0] = 1
    x = np.fft.irfft(spec / np.sqrt(f), n)
    return x / x.std()


# --------------------------------------------------------------------------- room

def build_rirs(rng: np.random.Generator) -> dict:
    absorption, max_order = pra.inverse_sabine(RT60_SABINE, ROOM_DIM)
    room = pra.ShoeBox(ROOM_DIM, fs=SR, materials=pra.Material(absorption), max_order=max_order)
    room.add_microphone(MIC)
    keys = []

    def child_at(d: float, ang: float) -> list[float]:
        a = math.radians(ang)
        return [MIC[0] + d * math.sin(a), MIC[1] + d * math.cos(a), CHILD_Z]

    for d in DISTANCES:
        for ang in ANGLES_DEG:
            room.add_source(child_at(d, ang)); keys.append(("target", d, ang))
    placed = 0
    while placed < N_BABBLE:
        p = [rng.uniform(0.5, ROOM_DIM[0] - 0.5), rng.uniform(1.5, ROOM_DIM[1] - 0.4), CHILD_Z]
        if math.dist(p[:2], MIC[:2]) > 1.2:
            room.add_source(p); keys.append(("babble", placed, 0.0)); placed += 1
    room.add_source([ROOM_DIM[0] / 2, ROOM_DIM[1] / 2, ROOM_DIM[2] - 0.3]); keys.append(("fan", 0, 0.0))
    t = time.time()
    room.compute_rir()
    rirs = {k: np.asarray(room.rir[0][i], dtype=np.float32) for i, k in enumerate(keys)}
    measured = pra.experimental.measure_rt60(rirs[("target", 4.0, 0.0)], fs=SR)
    print(f"RIRs for {len(keys)} sources in {time.time() - t:.0f}s; measured RT60 {measured:.2f}s")
    return rirs


def make_noise_bed(rirs: dict, babble_paths: list[str], rng: np.random.Generator, dur_s: float = 240.0) -> np.ndarray:
    """Intermittent murmur from N_BABBLE children around the room, plus a fan."""
    n = int(dur_s * SR)
    babble = np.zeros(n, dtype=np.float32)
    for b in range(N_BABBLE):
        track = np.zeros(n, dtype=np.float32)
        t = int(rng.uniform(0, 3) * SR)
        while t < n:
            clip = norm_active(trim_active(load(babble_paths[rng.integers(len(babble_paths))])))
            seg = clip[: n - t]
            track[t: t + len(seg)] += seg
            t += len(clip) + int(rng.uniform(0.5, 4.0) * SR)
        babble += fftconvolve(track, rirs[("babble", b, 0.0)])[:n].astype(np.float32)
    babble *= 10 ** (BABBLE_REL_DB / 20)
    fan = fftconvolve(pink_noise(n, rng), rirs[("fan", 0, 0.0)])[:n].astype(np.float32)
    fan *= math.sqrt(np.mean(babble ** 2) / np.mean(fan ** 2)) * 10 ** (FAN_REL_DB / 20)
    return babble + fan


def render(x: np.ndarray, rir: np.ndarray, bed: np.ndarray, gain: float, rng: np.random.Generator):
    y = fftconvolve(x, rir)[: len(x) + int(0.3 * SR)].astype(np.float32)
    off = rng.integers(0, len(bed) - len(y))
    noise = bed[off: off + len(y)] * gain
    snr = 10 * math.log10(active_power(y) / (np.mean(noise ** 2) + 1e-12))
    z = y + noise
    return z / (np.abs(z).max() + 1e-9) * 0.9, snr


# --------------------------------------------------------------------------- models

class Embedder:
    def __init__(self, name: str):
        self.name = name
        torch.backends.nnpack.set_flags(False)  # NNPACK conv is ~60x slower on Apple silicon
        if name == "ecapa":
            from speechbrain.inference.speaker import EncoderClassifier
            self.m = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb", savedir=str(CACHE / "ecapa"),
                run_opts={"device": "cpu"})
        else:
            from transformers import AutoFeatureExtractor, WavLMForXVector
            self.dev = "mps" if torch.backends.mps.is_available() else "cpu"
            self.fe = AutoFeatureExtractor.from_pretrained("microsoft/wavlm-base-plus-sv")
            self.m = WavLMForXVector.from_pretrained("microsoft/wavlm-base-plus-sv").to(self.dev).eval()

    def enrol(self, wavs: list[np.ndarray], chunk_s: float = 5.0) -> np.ndarray:
        """Long voice samples: embed 5 s pieces and average (keeps memory flat)."""
        n = int(chunk_s * SR)
        pieces, owner = [], []
        for i, w in enumerate(wavs):
            for a in range(0, max(len(w) - n // 2, 1), n):
                pieces.append(w[a: a + n]); owner.append(i)
        emb = self(pieces)
        owner = np.array(owner)
        out = np.stack([emb[owner == i].mean(0) for i in range(len(wavs))])
        return out / np.linalg.norm(out, axis=1, keepdims=True)

    @torch.no_grad()
    def __call__(self, wavs: list[np.ndarray], batch: int = 16) -> np.ndarray:
        out = []
        order = np.argsort([len(w) for w in wavs])  # similar lengths per batch, less padding
        for i in range(0, len(wavs), batch):
            chunk = [wavs[j] for j in order[i: i + batch]]
            if self.name == "ecapa":
                L = max(len(w) for w in chunk)
                x = torch.zeros(len(chunk), L)
                for k, w in enumerate(chunk):
                    x[k, : len(w)] = torch.from_numpy(w)
                lens = torch.tensor([len(w) / L for w in chunk])
                e = self.m.encode_batch(x, lens).squeeze(1)
            else:
                inp = self.fe(chunk, sampling_rate=SR, return_tensors="pt", padding=True)
                e = self.m(**{k: v.to(self.dev) for k, v in inp.items()}).embeddings.cpu()
            out.append(torch.nn.functional.normalize(e, dim=-1).numpy())
        emb = np.concatenate(out)
        res = np.empty_like(emb)
        res[order] = emb
        return res


# --------------------------------------------------------------------------- data

YOUNG = {"5-7 years", "7-10 years"}
ENROL_MIN_S, ENROL_TARGET_S = 10.0, 20.0


def select_pool(df: pd.DataFrame, n_pool: int, max_tests: int, rng: np.random.Generator):
    """Children aged 5-10 with >= 3 single-word answers and >= 10 s of other speech to enrol on.

    Enrolment = the paragraph/story reading, topped up with the child's other
    clips (never the test answers) to ~20 s, like a one-time voice sample.
    The pool is filled from the devices with the most children first, so
    classes can be drawn from one phone, as in a real classroom.
    """
    children = []
    for session, g in df[df.age_group.isin(YOUNG)].groupby("session"):
        g = g.sample(frac=1.0, random_state=int(rng.integers(1 << 30)))
        words = g[g.level.isin(WORD_LEVELS) & (g.speech_s >= 0.3)]
        if len(words) < 3:
            continue
        tests = words.iloc[:max_tests]
        rest = g.drop(tests.index)
        rest = pd.concat([rest[rest.level.isin(ENROL_LEVELS)], rest[~rest.level.isin(ENROL_LEVELS)]])
        enrol, total = [], 0.0
        for path, sp in zip(rest.path, rest.speech_s):
            if total >= ENROL_TARGET_S:
                break
            enrol.append(path); total += sp
        if total < ENROL_MIN_S:
            continue
        children.append({"session": session, "device": str(g.device_id.iloc[0]),
                         "enrol": enrol, "enrol_s": total, "words": list(tests.path)})
    by_device = defaultdict(list)
    for c in children:
        by_device[c["device"]].append(c)
    pool, rest = [], []
    for dev in sorted(by_device, key=lambda d: -len(by_device[d])):
        (pool if len(pool) < n_pool else rest).extend(by_device[dev])
    pool, rest = pool[:n_pool], rest + pool[n_pool:]
    babble_paths = [p for c in rest for p in c["words"] + c["enrol"]]
    return pool, babble_paths


def classrooms(pool: list[dict], n: int, reps: int, rng: np.random.Generator):
    by_device = defaultdict(list)
    for i, c in enumerate(pool):
        by_device[c["device"]].append(i)
    groups = [g for g in by_device.values() if len(g) >= n]
    out = []
    for _ in range(reps):
        if groups:
            sizes = np.array([len(g) for g in groups], dtype=float)
            g = groups[rng.choice(len(groups), p=sizes / sizes.sum())]
            out.append((list(rng.choice(g, n, replace=False)), "same-device"))
        else:
            out.append((list(rng.choice(len(pool), n, replace=False)), "mixed-device"))
    return out


# --------------------------------------------------------------------------- run

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", type=int, default=300)
    ap.add_argument("--max-tests", type=int, default=5)
    ap.add_argument("--classrooms", type=int, default=60)
    ap.add_argument("--models", default="ecapa,wavlm")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    df = pd.read_csv(MANIFEST, dtype={"device_id": str})
    df = df[df.region.isin(["RJ", "UP"])]
    pool, babble_paths = select_pool(df, args.pool, args.max_tests, rng)
    print(f"pool: {len(pool)} children, {len(babble_paths)} murmur clips from other children", flush=True)

    rirs = build_rirs(rng)
    bed = make_noise_bed(rirs, babble_paths, rng)

    # Reference level: a single-word answer heard from 1 m, straight ahead.
    ref = [fftconvolve(norm_active(trim_active(load(c["words"][0]))), rirs[("target", 1.0, 0.0)])
           for c in pool[:100]]
    p_ref = float(np.mean([active_power(r) for r in ref]))
    p_bed = float(np.mean(bed ** 2))
    gains = {s: math.sqrt(p_ref / (p_bed * 10 ** (snr / 10))) for s, snr in NOISE_SNR_AT_1M.items()}

    # Render each child's audio once per condition and keep only the embeddings,
    # 25 children at a time, so memory stays flat.
    conditions = ["close"] + [f"{s}@{d:g}m" for s in NOISE_SNR_AT_1M for d in DISTANCES]
    models = args.models.split(",")
    embedders = {m: Embedder(m) for m in models}
    E = {m: [] for m in models}
    T = {m: [] for m in models}
    meta = []   # (child index, answer kind, condition) per test embedding row
    snr_by_cond = defaultdict(list)
    pause = np.zeros(int(0.2 * SR), dtype=np.float32)
    gap = np.zeros(int(0.25 * SR), dtype=np.float32)
    t = time.time()
    for start in range(0, len(pool), 25):
        enrol_wavs, test_wavs = [], []
        for ci in range(start, min(start + 25, len(pool))):
            c = pool[ci]
            e = np.concatenate([np.concatenate([norm_active(trim_active(load(p))), pause]) for p in c["enrol"]])
            e = norm_active(e[: 30 * SR])
            enrol_wavs.append(e / (np.abs(e).max() + 1e-9) * 0.9)  # recorded close to the phone, as ASER was
            singles = [norm_active(trim_active(load(p))) for p in c["words"]]
            triple = norm_active(np.concatenate([singles[0], gap, singles[1], gap, singles[2]]))
            for kind, wavs in (("1 word", singles), ("3 words", [triple])):
                for w in wavs:
                    test_wavs.append(w / (np.abs(w).max() + 1e-9) * 0.9)
                    meta.append((ci, kind, "close"))
                    for sc in NOISE_SNR_AT_1M:
                        for d in DISTANCES:
                            ang = ANGLES_DEG[rng.integers(len(ANGLES_DEG))]
                            z, snr = render(w, rirs[("target", d, ang)], bed, gains[sc], rng)
                            test_wavs.append(z)
                            meta.append((ci, kind, f"{sc}@{d:g}m"))
                            if kind == "1 word":
                                snr_by_cond[f"{sc}@{d:g}m"].append(snr)
        for m, emb in embedders.items():
            E[m].append(emb.enrol(enrol_wavs))
            T[m].append(emb(test_wavs))
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        print(f"  {min(start + 25, len(pool))}/{len(pool)} children embedded ({time.time() - t:.0f}s)", flush=True)

    idx = defaultdict(list)
    for k, (ci, kind, cond) in enumerate(meta):
        idx[(kind, cond)].append((ci, k))
    groups = {key: (np.array([c for c, _ in v]), np.array([k for _, k in v])) for key, v in idx.items()}
    trials = []
    for model in models:
        Em, Tm = np.concatenate(E[model]), np.concatenate(T[model])
        for n in CLASS_SIZES:
            for room_id, (members, grouping) in enumerate(classrooms(pool, n, args.classrooms, rng)):
                pos = np.full(len(pool), -1)
                pos[members] = np.arange(n)
                En = Em[members]
                for (kind, cond), (cis, ks) in groups.items():
                    m = pos[cis] >= 0
                    S = Tm[ks[m]] @ En.T
                    srt = np.sort(S, axis=1)
                    trials.append(pd.DataFrame({
                        "model": model, "n": n, "room": room_id, "grouping": grouping, "kind": kind, "cond": cond,
                        "correct": (S.argmax(1) == pos[cis[m]]).astype(int), "margin": srt[:, -1] - srt[:, -2],
                    }))
    tr = pd.concat(trials, ignore_index=True)
    summarise(tr, snr_by_cond, conditions, pool, args)


def precision_at_gate(g: pd.DataFrame) -> tuple[float, float, float]:
    """Pick the margin gate on even classrooms (>= 90% precision), score it on odd ones."""
    cal, test = g[g.room % 2 == 0], g[g.room % 2 == 1]
    gate = None
    for tau in np.quantile(cal.margin, np.linspace(0, 0.995, 200)):
        kept = cal[cal.margin >= tau]
        if len(kept) >= 20 and kept.correct.mean() >= PRECISION_TARGET:
            gate = float(tau)
            break
    if gate is None:
        return float("nan"), float("nan"), float("nan")
    kept = test[test.margin >= gate]
    prec = kept.correct.mean() if len(kept) else float("nan")
    return gate, float(prec), len(kept) / max(len(test), 1)


def ci95(g: pd.DataFrame, rng: np.random.Generator, reps: int = 400) -> tuple[float, float]:
    by_room = g.groupby("room").correct.agg(["sum", "count"]).to_numpy()
    stats = []
    for _ in range(reps):
        s = by_room[rng.integers(len(by_room), size=len(by_room))]
        stats.append(s[:, 0].sum() / s[:, 1].sum())
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def summarise(tr: pd.DataFrame, snr_by_cond: dict, conditions: list[str], pool: list[dict], args) -> None:
    rng = np.random.default_rng(0)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for (model, n, kind, cond), g in tr.groupby(["model", "n", "kind", "cond"]):
        lo, hi = ci95(g, rng)
        gate, prec, cov = precision_at_gate(g)
        rows.append({
            "model": model, "class_size": n, "answer": kind, "condition": cond,
            "attempts": len(g), "accuracy": round(g.correct.mean(), 4),
            "ci95": [round(lo, 4), round(hi, 4)], "chance": round(1 / n, 4),
            "gate_margin": None if math.isnan(gate) else round(gate, 4),
            "precision_at_gate": None if math.isnan(prec) else round(prec, 4),
            "coverage_at_gate": None if math.isnan(cov) else round(cov, 4),
            "same_device_share": round((g.grouping == "same-device").mean(), 3),
        })
    snr = {c: round(float(np.median(v)), 1) for c, v in snr_by_cond.items()}
    meta = {
        "label": "SIMULATED classroom acoustics; REAL child voices (Pratham ASER, CC BY-NC-SA 4.0)",
        "children_in_pool": len(pool), "classrooms_per_size": args.classrooms, "seed": args.seed,
        "room_m": ROOM_DIM, "rt60_s": RT60, "distances_m": DISTANCES, "noise_snr_at_1m_db": NOISE_SNR_AT_1M,
        "median_snr_db_by_condition": snr, "precision_target": PRECISION_TARGET,
    }
    (OUT / "f1_voice_id.json").write_text(json.dumps({"meta": meta, "results": rows}, ensure_ascii=False, indent=1))

    res = pd.DataFrame(rows)
    lines = [
        "# F1: matching an answer to a child by voice (SIMULATED classroom, real child voices)",
        "",
        f"Generated by `eval/feasibility/voice_id.py` (seed {args.seed}). {len(pool)} children from Pratham ASER (Hindi, RJ and UP); "
        f"{args.classrooms} random classes per size. Room {ROOM_DIM[0]:g} x {ROOM_DIM[1]:g} m, RT60 {RT60} s, phone worn by the teacher, "
        f"{N_BABBLE} murmuring children and a fan.",
        "",
        "Accuracy = share of answers matched to the right child (chance = 1 / class size). "
        f"'Kept at {PRECISION_TARGET:.0%}' = share of answers SUNO could still attribute if it only names a child when the "
        f"match is clear enough to be right {PRECISION_TARGET:.0%} of the time (gate set on half the classes, checked on the other half).",
        "",
    ]
    for model in res.model.unique():
        for kind in ["1 word", "3 words"]:
            sub = res[(res.model == model) & (res.answer == kind)]
            lines += [f"## {model}, answer = {kind}", "",
                      "| Condition | Median SNR | " + " | ".join(f"Acc, class of {n}" for n in CLASS_SIZES)
                      + f" | Kept at {PRECISION_TARGET:.0%}, class of 5 | Kept at {PRECISION_TARGET:.0%}, class of 35 |",
                      "|---|---|" + "---|" * len(CLASS_SIZES) + "---|---|"]
            for cond in conditions:
                cells = []
                for n in CLASS_SIZES:
                    r = sub[(sub.condition == cond) & (sub.class_size == n)]
                    cells.append("–" if r.empty else f"{r.accuracy.iloc[0]:.0%} ({r.ci95.iloc[0][0]:.0%}–{r.ci95.iloc[0][1]:.0%})")
                for n in (5, 35):
                    r = sub[(sub.condition == cond) & (sub.class_size == n)]
                    if r.empty:
                        cells.append("–")
                    elif r.gate_margin.isna().iloc[0]:
                        cells.append("not reachable")
                    else:
                        cells.append(f"{r.coverage_at_gate.iloc[0]:.0%} (precision {r.precision_at_gate.iloc[0]:.0%})")
                s = snr.get(cond)
                lines.append(f"| {cond} | {'–' if s is None else f'{s:+.0f} dB'} | " + " | ".join(cells) + " |")
            lines.append("")
    (OUT / "f1_voice_id.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
