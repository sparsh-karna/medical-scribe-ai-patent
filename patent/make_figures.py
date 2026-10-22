"""\nGenerates the patent drawings (form section 12) in two sets:\n  figures/labeled/    -- fully labelled, with reference numerals\n  figures/unlabeled/  -- identical geometry, no text, legends or numbering\nEvery block corresponds to a module in prototype/src (named in the labelled set).\n"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

OUT = Path(__file__).resolve().parent / "figures"
INK = "#1a1a1a"


class Fig:
    def __init__(self, w, h, labeled):
        self.fig, self.ax = plt.subplots(figsize=(w, h), dpi=200)
        self.ax.set_xlim(0, w * 10)
        self.ax.set_ylim(0, h * 10)
        self.ax.axis("off")
        self.labeled = labeled

    def box(self, x, y, w, h, text="", num=None, style="round", dashed=False, fs=7.2):
        if style == "diamond":
            pts = [(x + w / 2, y + h), (x + w, y + h / 2), (x + w / 2, y), (x, y + h / 2)]
            self.ax.add_patch(Polygon(pts, closed=True, fill=False, ec=INK, lw=1.1))
        else:
            bs = "round,pad=0.02,rounding_size=1.2" if style == "round" else "square,pad=0.02"
            self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=bs, fill=False, ec=INK, lw=1.1,
                                             ls=(0, (4, 3)) if dashed else "-"))
        if self.labeled:
            if text:
                self.ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
                             color=INK, linespacing=1.25, family="DejaVu Sans")
            if num is not None:
                self.ax.text(x + w - 0.6, y + h + 0.6, str(num), ha="right", va="bottom",
                             fontsize=6.5, color=INK, family="DejaVu Sans", style="italic")
        return (x, y, w, h)

    def arrow(self, p, q, text="", curve=0.0, dashed=False, off=(0, 0)):
        self.ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=8, lw=0.9, color=INK,
                                          connectionstyle=f"arc3,rad={curve}",
                                          ls=(0, (4, 3)) if dashed else "-"))
        if self.labeled and text:
            self.ax.text((p[0] + q[0]) / 2 + off[0], (p[1] + q[1]) / 2 + off[1], text, fontsize=6.2,
                         ha="center", va="center", color=INK, style="italic",
                         bbox=dict(fc="white", ec="none", pad=0.6))

    def title(self, text):
        if self.labeled:
            self.ax.text(self.ax.get_xlim()[1] / 2, self.ax.get_ylim()[1] - 1.5, text, ha="center",
                         va="top", fontsize=9, weight="bold", color=INK)

    def save(self, name):
        sub = OUT / ("labeled" if self.labeled else "unlabeled")
        sub.mkdir(parents=True, exist_ok=True)
        self.fig.savefig(sub / f"{name}.png", bbox_inches="tight", facecolor="white")
        plt.close(self.fig)


def top(b): return (b[0] + b[2] / 2, b[1] + b[3])
def bot(b): return (b[0] + b[2] / 2, b[1])
def left(b): return (b[0], b[1] + b[3] / 2)
def right(b): return (b[0] + b[2], b[1] + b[3] / 2)


def fig1(labeled):
    """System architecture / pipeline."""
    f = Fig(10.5, 8.4, labeled)
    f.title("FIG. 1 - Confidence-gated clinical documentation system")
    vocab = f.box(25, 70, 19, 7, "Confidence-gated medical-term\ncorrection (+ optional biasing)", 115, dashed=True, fs=6.6)
    audio = f.box(2, 55, 17, 9, "Consultation audio\n(doctor + patient\nchannels, or mixed)", 100)
    asr = f.box(25, 55, 19, 9, "Local ASR (Whisper)\nper-word probability\n+ timestamps", 110)
    spk = f.box(50, 55, 19, 9, "Speaker-role\nattribution\n(channel or LLM)", 120)
    seg = f.box(75, 55, 25, 9, "Segmented transcript\n(speaker, text, words with\nprobability + offsets)", 130)
    g2 = f.box(2, 38, 20, 9, "Gate 2: semantic\nNLI entailment /\ncontradiction", 170)
    g1 = f.box(26, 38, 20, 9, "Gate 1: acoustic\nmean + weakest word\nprobability over quote", 160)
    g0 = f.box(50, 38, 21, 9, "Gate 0: citation\nintegrity (quote occurs\nin cited segment)", 150)
    ext = f.box(75, 38, 25, 9, "Fact extractor\n(rule-based or LLM):\nfact + citations +\nverbatim quotes", 140)
    comb = f.box(2, 21, 22, 9, "Floors + weighted\ncombination vs.\nper-field threshold", 180)
    g3 = f.box(40, 21, 22, 9, "Gate 3: clinical\nplausibility (allergy,\nindication, interaction)", 190)
    note = f.box(78, 21, 22, 9, "Structured note\n(auto-inserted,\nVERIFIED facts only)", 200)
    cal = f.box(2, 4, 22, 9, "Adaptive calibration\nstore (per clinician,\nper field)", 220)
    queue = f.box(40, 4, 22, 9, "Clinician review\nqueue (hard-blocked\nfacts + audio span)", 210)
    audit = f.box(78, 4, 22, 9, "Append-only\naudit log", 230, style="square")

    f.arrow(top(asr), bot(vocab), dashed=True)
    f.arrow(right(audio), left(asr))
    f.arrow(right(asr), left(spk))
    f.arrow(right(spk), left(seg))
    f.arrow(bot(seg), top(ext))
    f.arrow(left(ext), right(g0), "facts")
    f.arrow(left(g0), right(g1), "quote spans")
    f.arrow(left(g1), right(g2))
    f.arrow(bot(g2), top(comb))
    f.arrow(right(comb), left(g3), "passes")
    f.arrow(right(g3), left(note), "no conflict")
    f.arrow(bot(g3), top(queue), "conflict", off=(4, 0))
    f.arrow((20, 21), (44, 13), "blocked", off=(-2, 1.5))
    f.arrow(left(queue), right(cal), "approve /\nreject", off=(0, 3.5))
    f.arrow((8, 13), (8, 21), "threshold", off=(5, 0))
    f.arrow(right(queue), left(audit), "resolution", dashed=True, off=(0, 2))
    f.arrow(bot(note), top(audit), "gate record", dashed=True, off=(6, 0))
    f.save("fig1_system")


def fig2(labeled):
    """Per-fact gate decision flow."""
    f = Fig(8.2, 10.4, labeled)
    f.title("FIG. 2 - Per-fact gate decision (grounding.py, clinical_plausibility.py)")
    s = f.box(28, 92, 26, 6, "Drafted fact: field, value,\ncited segment ids, quotes", 300)
    d1 = f.box(29, 80, 24, 9, "Valid citation and\nevery quote aligns\n>= 90/100 ?", 310, style="diamond", fs=6.6)
    d2 = f.box(29, 67, 24, 9, "P(contradiction)\n< 0.50 ?", 320, style="diamond")
    d3 = f.box(29, 54, 24, 9, "P(entailment)\n>= 0.30 floor ?", 330, style="diamond")
    d4 = f.box(29, 41, 24, 9, "Audio present:\nacoustic >= 0.50\nfloor ?", 340, style="diamond", fs=6.6)
    c = f.box(28, 30, 26, 7, "combined = 0.6*entail + 0.4*acoustic\n(entailment only if no audio)", 350, fs=6.4)
    d5 = f.box(29, 17, 24, 9, "combined >= field\nthreshold and weakest\nword >= 0.35 ?", 360, style="diamond", fs=6.4)
    d6 = f.box(29, 4, 24, 9, "Plausibility\nconflict ?", 370, style="diamond")
    rej = f.box(62, 60, 18, 8, "REJECTED\n(hard block,\nreason logged)", 380)
    rev = f.box(62, 17, 18, 9, "NEEDS_REVIEW\n(blocked, queued\nfor clinician)", 390)
    ver = f.box(2, 4, 18, 9, "VERIFIED\nauto-inserted\ninto note", 400)
    f.arrow(bot(s), top(d1))
    f.arrow(bot(d1), top(d2), "yes", off=(3, 0))
    f.arrow(bot(d2), top(d3), "yes", off=(3, 0))
    f.arrow(bot(d3), top(d4), "yes", off=(3, 0))
    f.arrow(bot(d4), top(c), "yes / no audio", off=(6, 0))
    f.arrow(bot(c), top(d5))
    f.arrow(bot(d5), top(d6), "yes", off=(3, 0))
    f.arrow(left(d6), right(ver), "no", off=(0, 1.5))
    f.arrow(right(d6), (71, 17), "yes", curve=0.3, off=(5, 0))
    f.arrow(right(d5), left(rev), "no", off=(0, 1.5))
    for d in (d1, d2, d3, d4):
        f.arrow(right(d), left(rej) if d in (d2, d3) else (62, 64), "no", curve=0.0 if d in (d2, d3) else (-0.2 if d is d1 else 0.2), off=(0, 1.5))
    f.save("fig2_gate_flow")


def fig3(labeled):
    """Clinician resolution, calibration and audit loop."""
    f = Fig(10.2, 5.6, labeled)
    f.title("FIG. 3 - Clinician resolution, adaptive calibration and audit trail")
    q = f.box(2, 30, 20, 10, "Blocked fact in\nreview queue\n(evidence + audio span)", 500)
    dec = f.box(28, 30, 18, 10, "Named clinician\napproves / rejects", 510)
    upd = f.box(52, 30, 22, 10, "Threshold update\nt += 0.2 (target - t)\nclamped to [0.55, 0.95]", 520)
    store = f.box(80, 30, 18, 10, "Per-clinician,\nper-field\nthreshold store", 530)
    gate = f.box(80, 8, 18, 10, "Gate on next\ncase (FIG. 2,\nstep 360)", 540)
    log = f.box(28, 8, 46, 10, "Append-only audit log: auto_gate_decision, clinical_plausibility_flag,\nclinician_resolution (name, decision), calibration_update", 550,
                style="square", fs=6.6)
    f.arrow(right(q), left(dec))
    f.arrow(right(dec), left(upd), "NEEDS_REVIEW\nonly", off=(0, -9))
    f.arrow(right(upd), left(store))
    f.arrow(bot(store), top(gate))
    f.arrow(bot(dec), (37, 18))
    f.arrow(bot(upd), (63, 18))
    f.arrow(left(gate), right(log), dashed=True)
    if labeled:
        f.ax.text(63, 45, "approve: target = fact's combined score   reject: target = 0.95", fontsize=6.2,
                  ha="center", style="italic", color=INK)
    f.save("fig3_calibration")


if __name__ == "__main__":
    for labeled in (True, False):
        fig1(labeled)
        fig2(labeled)
        fig3(labeled)
    print("written to", OUT)
