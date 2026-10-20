"""Chart for F1: how often voice matching picks the right child, by distance.

Reads eval/results/f1_voice_id.json, writes eval/results/f1_voice_id.png.
Small multiples: one panel per class size; one line per model; calm room,
single-word answers. Colours: reference categorical slots 1-2 (validated).
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "eval/results"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
SERIES = {"ecapa": ("#2a78d6", "SpeechBrain ECAPA"), "wavlm": ("#eb6834", "Microsoft WavLM-SV")}
CONDS = ["close", "calm@1m", "calm@2m", "calm@4m", "calm@6m"]
XLABELS = ["into the\nphone", "1 m", "2 m", "4 m", "6 m"]


def main() -> None:
    data = json.loads((RES / "f1_voice_id.json").read_text())
    rows = [r for r in data["results"] if r["answer"] == "1 word"]
    sizes = [5, 35]
    plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 11})
    fig, axes = plt.subplots(1, len(sizes), figsize=(10, 4.2), sharey=True, facecolor=SURFACE)
    for ax, n in zip(axes, sizes):
        ax.set_facecolor(SURFACE)
        for model, (color, label) in SERIES.items():
            ys = []
            for c in CONDS:
                r = next((r for r in rows if r["model"] == model and r["class_size"] == n and r["condition"] == c), None)
                ys.append(None if r is None else r["accuracy"] * 100)
            if all(y is None for y in ys):
                continue
            ax.plot(range(len(CONDS)), ys, color=color, linewidth=2, marker="o", markersize=7,
                    markeredgecolor=SURFACE, markeredgewidth=2, label=label, zorder=3)
            ax.annotate(f"{ys[0]:.0f}%", (0, ys[0]), textcoords="offset points", xytext=(-10, 8),
                        ha="right", color=INK2, fontsize=10)
        ax.axhline(100 / n, color=INK2, linewidth=1, linestyle=(0, (4, 3)), zorder=2,
                   label="Random guess" if n == sizes[0] else None)
        ax.axhline(90, color=INK2, linewidth=1, linestyle=(0, (1, 2)), zorder=2)
        ax.text(len(CONDS) - 1, 92, "needed to name a child (90%)", ha="right", color=INK2, fontsize=10)
        ax.set_title(f"Class of {n} (random guess: {100 / n:.0f}%)", color=INK, loc="left", fontsize=12, fontweight="bold")
        ax.set_xticks(range(len(CONDS)), XLABELS, color=INK2)
        ax.set_ylim(0, 100)
        ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"], color=INK2)
        ax.grid(axis="y", color=GRID, linewidth=1)
        ax.tick_params(length=0)
        for s in ax.spines.values():
            s.set_visible(False)
    axes[0].set_ylabel("Answers matched to the right child", color=INK2)
    axes[0].legend(frameon=False, loc="upper right", bbox_to_anchor=(1.0, 0.86), labelcolor=INK)
    fig.suptitle("Voice matching can't tell which child answered (one-word answers, calm room)",
                 x=0.06, y=0.97, ha="left", color=INK, fontsize=13, fontweight="bold")
    fig.text(0.06, 0.005, f"SIMULATED classroom, REAL child voices (Pratham ASER, ages 5-10). "
             f"{data['meta']['children_in_pool']} children, {data['meta']['classrooms_per_size']} random classes per size. "
             "eval/feasibility/voice_id.py", color=INK2, fontsize=9)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    fig.savefig(RES / "f1_voice_id.png", dpi=200, facecolor=SURFACE)
    print(f"wrote {(RES / 'f1_voice_id.png').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
