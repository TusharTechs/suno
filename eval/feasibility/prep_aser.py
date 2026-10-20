"""Unpack the Pratham ASER Hindi recordings into 16 kHz WAVs plus one manifest.

Each ASER zip is one reading-test session with one child: a paragraph or story,
some Hindi words and letters, and optional English items, all recorded on a
phone close to the child. We use the sessions as "one child = one speaker".

    uv run python eval/feasibility/prep_aser.py

Reads   data/external/aser/Data/Hindi {RJ,UP}/*.zip   (git-ignored, CC BY-NC-SA 4.0)
Writes  data/external/aser/wav/<region>/<session>/<que_id>.wav
        data/external/aser/manifest.csv
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
ASER = ROOT / "data/external/aser"
REGIONS = {"Hindi RJ": "RJ", "Hindi UP": "UP"}
SR = 16_000

# Level codes in que_id (HI_S2_WD_3 -> WD). Hindi: ST story, P paragraph,
# WD word, L letter. English: W word, S sentence, CL/SL capital/small letter.
HINDI_LEVELS = {"ST", "P", "WD", "L"}

FIELDS = [
    "session", "region", "device_id", "age_group", "stud_class", "que_id", "level",
    "lang", "que_text", "is_correct", "n_mistakes", "path", "dur_s", "speech_s",
]


def decode_mp3(data: bytes) -> np.ndarray:
    """Decode with ffmpeg; it tolerates the truncated frames some ASER files have."""
    out = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(SR), "pipe:1"],
        input=data, capture_output=True, check=True,
    ).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


def speech_seconds(x: np.ndarray, frame: int = 320) -> float:
    """Rough speech duration: 20 ms frames within 30 dB of the loudest frame."""
    n = len(x) // frame
    if n == 0:
        return 0.0
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    return float(np.sum(db > db.max() - 30) * frame / SR)


def process_zip(args: tuple[Path, str]) -> list[dict]:
    zpath, region = args
    session = f"{region}-{zpath.stem}"
    rows = []
    try:
        with zipfile.ZipFile(zpath) as z:
            meta_name = next(n for n in z.namelist() if n.endswith(".json"))
            meta = json.loads(z.read(meta_name))
            members = {Path(n).name: n for n in z.namelist()}
            out_dir = ASER / "wav" / region / session
            out_dir.mkdir(parents=True, exist_ok=True)
            for item in meta.get("sequenceList", []):
                name = item.get("recordingName")
                if not name or name not in members:
                    continue
                que_id = item.get("que_id", Path(name).stem)
                level = que_id.split("_")[2] if que_id.count("_") >= 3 else "?"
                try:
                    x = decode_mp3(z.read(members[name]))
                except subprocess.CalledProcessError:
                    continue
                if len(x) < SR // 4:
                    continue
                wav = out_dir / f"{que_id}.wav"
                sf.write(wav, x, SR, subtype="PCM_16")
                rows.append({
                    "session": session,
                    "region": region,
                    "device_id": meta.get("deviceID", ""),
                    "age_group": meta.get("ageGroup", ""),
                    "stud_class": meta.get("studClass", ""),
                    "que_id": que_id,
                    "level": level,
                    "lang": "hi" if level in HINDI_LEVELS else "en",
                    "que_text": item.get("que_text", ""),
                    "is_correct": item.get("isCorrect", ""),
                    "n_mistakes": item.get("noOfMistakes", ""),
                    "path": str(wav.relative_to(ROOT)),
                    "dur_s": round(len(x) / SR, 3),
                    "speech_s": round(speech_seconds(x), 3),
                })
    except (zipfile.BadZipFile, StopIteration, json.JSONDecodeError) as e:
        print(f"skip {zpath.name}: {e}", file=sys.stderr)
    return rows


def main() -> None:
    jobs = [
        (z, code)
        for folder, code in REGIONS.items()
        for z in sorted((ASER / "Data" / folder).glob("*.zip"))
    ]
    print(f"{len(jobs)} session zips")
    rows: list[dict] = []
    with ProcessPoolExecutor() as pool:
        for i, r in enumerate(pool.map(process_zip, jobs, chunksize=8)):
            rows.extend(r)
            if i % 200 == 0:
                print(f"  {i}/{len(jobs)} sessions, {len(rows)} clips")
    with open(ASER / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} clips from {len({r['session'] for r in rows})} sessions")


if __name__ == "__main__":
    main()
