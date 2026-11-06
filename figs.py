"""Figure functions for analyse.py. Static matplotlib, PNG (300 dpi) + SVG.

Palette: the dataviz skill's validated reference palette, unchanged.
- Sequential (magnitude, e.g. ASR 0-1): one hue (blue), light -> dark, fixed 0-1 scale.
- Categorical (identity): fixed slot order, never cycled; every series also gets a marker
  shape or a direct label, so identity never rests on colour alone (print, greyscale, CVD).
- Chrome: recessive grey grid and axes; text in ink tokens, never in series colours.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from stats import wilson  # noqa: E402

INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE, SURFACE = "#e1e0d9", "#c3c2b7", "#ffffff"
SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf",
       "#1c5cab", "#184f95", "#104281", "#0d366b"]
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
CMAP = LinearSegmentedColormap.from_list("asr_blue", SEQ)
DEF_STYLE = {d: (CAT[i], MARKERS[i]) for i, d in enumerate(["D0", "D1", "D2", "D3", "D0+M", "D1fix", "D3-R1", "D0+M-R1"])}
GROUPS = [("A1 Outsider", ["A1g", "A1r"]), ("A2 Replay", ["A2f", "A2s"]), ("A3 Relay", ["A3"]),
          ("A4 Stolen key", ["A4d", "A4l"]), ("A5 Injected insider", ["A5b", "A5p", "A5d"])]
COL_LABEL = {"A1g": "guess", "A1r": "reflect", "A2f": "fast", "A2s": "slow", "A3": "tamper", "A4d": "direct",
             "A4l": "lie", "A5b": "blunt", "A5p": "polite", "A5d": "disguised", "A5*": "pooled"}
COLS = [c for _, cs in GROUPS for c in cs]


def setup_style() -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "DejaVu Sans", "Arial", "Liberation Sans", "sans-serif"],
        "font.size": 8, "axes.titlesize": 9, "axes.labelsize": 8, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
        "legend.fontsize": 7.5, "axes.edgecolor": BASELINE, "axes.labelcolor": INK2, "xtick.color": INK2,
        "ytick.color": INK2, "text.color": INK, "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "svg.hashsalt": "sign-countersign",
        "lines.linewidth": 1.5, "legend.frameon": False,
    })


def save(fig, out_dir: Path, stem: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{stem}.png", out_dir / f"{stem}.svg"]
    fig.savefig(paths[0], dpi=300, bbox_inches="tight", metadata={"Software": None})
    fig.savefig(paths[1], bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)
    return paths


def _cell_text(k: int, n: int) -> tuple[str, float]:
    return (f"{k}/{n}\n{100 * k / n:.0f}%", k / n) if n else ("·", np.nan)


def heatmap(ax, cells: dict, rows: list[str], cols: list[str], title: str = "", binary_labels: bool = False) -> None:
    data = np.full((len(rows), len(cols)), np.nan)
    for i, d in enumerate(rows):
        for j, c in enumerate(cols):
            k, n = cells.get((d, c), (0, 0))
            if n:
                data[i, j] = k / n
    masked = np.ma.masked_invalid(data)
    ax.imshow(masked, cmap=CMAP, vmin=0, vmax=1, aspect="auto")
    for i, d in enumerate(rows):
        for j, c in enumerate(cols):
            k, n = cells.get((d, c), (0, 0))
            txt, v = _cell_text(k, n)
            if binary_labels and n:
                txt = "through" if k else "stopped"
            colour = SURFACE if (n and v >= 0.55) else INK
            ax.text(j, i, txt, ha="center", va="center", fontsize=6.8, color=colour if n else MUTED, linespacing=1.15)
    ax.set_xticks(range(len(cols)), [COL_LABEL.get(c, c) for c in cols])
    ax.set_yticks(range(len(rows)), rows)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    # 2px surface gaps between cells
    ax.set_xticks(np.arange(-0.5, len(cols), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(rows), 1), minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)
    # group headers above the columns
    start = 0
    for name, cs in GROUPS:
        present = [c for c in cs if c in cols]
        if not present:
            continue
        j0, j1 = cols.index(present[0]), cols.index(present[-1])
        ax.annotate(name, xy=((j0 + j1) / 2, -0.62), xycoords="data", ha="center", va="bottom", fontsize=7.5,
                    color=INK2, annotation_clip=False)
        ax.plot([j0 - 0.42, j1 + 0.42], [-0.58, -0.58], color=BASELINE, lw=0.8, clip_on=False)
        start = j1 + 1
    if title:
        ax.set_title(title, loc="left", pad=22, color=INK)


def fig_asr_heatmap(cells: dict, rows: list[str], out_dir: Path, stem: str, title: str, cols=None) -> list[Path]:
    setup_style()
    cols = cols or COLS
    fig, ax = plt.subplots(figsize=(7.0, 0.45 * len(rows) + 1.1))
    heatmap(ax, cells, rows, cols, title)
    cbar = fig.colorbar(plt.cm.ScalarMappable(cmap=CMAP, norm=plt.Normalize(0, 1)), ax=ax, fraction=0.025, pad=0.015)
    cbar.set_label("attack success rate", color=INK2)
    cbar.outline.set_visible(False)
    cbar.ax.tick_params(length=0)
    return save(fig, out_dir, stem)


def fig_forest(cells: dict, rows: list[str], out_dir: Path, stem: str = "fig4_asr_forest") -> list[Path]:
    setup_style()
    cols = [c for c in COLS if any((d, c) in cells for d in rows)]
    fig, ax = plt.subplots(figsize=(7.0, 0.42 * len(cols) * max(1, len(rows) / 4) + 0.9))
    offsets = np.linspace(-0.3, 0.3, len(rows))
    for i, d in enumerate(rows):
        colour, marker = DEF_STYLE[d]
        ys, xs, lo, hi = [], [], [], []
        for j, c in enumerate(cols):
            k, n = cells.get((d, c), (0, 0))
            if not n:
                continue
            a, b = wilson(k, n)
            ys.append(j + offsets[i]), xs.append(k / n), lo.append(k / n - a), hi.append(b - k / n)
        ax.errorbar(xs, ys, xerr=[lo, hi], fmt=marker, color=colour, ms=4.5, elinewidth=1.2, capsize=0,
                    label=d, markeredgecolor=SURFACE, markeredgewidth=0.6)
    ax.set_yticks(range(len(cols)), [f"{c}  {COL_LABEL[c]}" for c in cols])
    ax.invert_yaxis()
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("attack success rate (95% Wilson interval)")
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    for j in range(len(cols) - 1):
        ax.axhline(j + 0.5, color=GRID, lw=0.5)
    ax.legend(ncol=len(rows), loc="lower center", bbox_to_anchor=(0.5, 1.0), handletextpad=0.3, columnspacing=1.2)
    return save(fig, out_dir, stem)


def fig_cost_tradeoff(points: list[dict], out_dir: Path, stem: str = "fig5_cost_tradeoff") -> list[Path]:
    """Small multiples (one measure per panel, each with its own axis): protection vs the three costs."""
    setup_style()
    panels = [("mean_asr", "Mean attack success\n(10 attack columns)", "{:.0%}", (0, 1.08)),
              ("frr", "False rejections on honest\ntasks (95% Wilson interval)", "{:.0%}", None),
              ("ms_per_msg", "Added processing per\nmessage (median, ms)", "{:.2f}", None),
              ("tokens", "LLM tokens per honest\ntask (median)", "{:,.0f}", None)]
    fig, axes = plt.subplots(1, 4, figsize=(7.0, 2.3))
    names = [p["defence"] for p in points]
    for ax, (key, title, fmt, ylim) in zip(axes, panels):
        vals = [p[key] for p in points]
        colours = [DEF_STYLE[d][0] for d in names]
        if key == "frr":
            for i, p in enumerate(points):
                colour, marker = DEF_STYLE[p["defence"]]
                ax.errorbar([i], [p["frr"]], yerr=[[p["frr"] - p["frr_lo"]], [p["frr_hi"] - p["frr"]]], fmt=marker,
                            color=colour, ms=6, elinewidth=1.2, capsize=0, markeredgecolor=SURFACE)
                ax.annotate(fmt.format(p["frr"]), (i, p["frr"]), xytext=(5, -2), textcoords="offset points",
                            fontsize=6.5, color=INK)
            ax.set_ylim(-0.02, max(0.15, max(p["frr_hi"] for p in points) * 1.15))
        else:
            ax.bar(range(len(vals)), vals, 0.6, color=colours, edgecolor=SURFACE, linewidth=1)
            top = max(vals) if vals else 1
            for i, v in enumerate(vals):
                ax.annotate(fmt.format(v), (i, v), xytext=(0, 2), textcoords="offset points", ha="center",
                            fontsize=6.3, color=INK)
            ax.set_ylim(*(ylim or (0, top * 1.22 if top > 0 else 1)))
        ax.set_xticks(range(len(names)), names)
        ax.set_title(title, loc="left", fontsize=7.5)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", labelsize=6.5)
    fig.tight_layout(w_pad=1.2)
    return save(fig, out_dir, stem)


def fig_a5_variants(data: dict, families: list[str], out_dir: Path, stem: str = "fig6_a5_variants",
                    labels: dict | None = None) -> list[Path]:
    setup_style()
    variants = ["A5b", "A5p", "A5d"]
    defs = ["D0", "D1", "D2", "D3"]
    fig, axes = plt.subplots(1, len(families), figsize=(3.4 * len(families), 2.5), sharey=True, squeeze=False)
    for ax, fam in zip(axes[0], families):
        width = 0.18
        for i, d in enumerate(defs):
            colour, marker = DEF_STYLE[d]
            xs = np.arange(len(variants)) + (i - 1.5) * (width + 0.02)
            vals, lo, hi, ks = [], [], [], []
            for v in variants:
                k, n = data.get(fam, {}).get((d, v), (0, 0))
                p = k / n if n else 0
                a, b = wilson(k, n) if n else (0, 0)
                vals.append(p), lo.append(p - a), hi.append(b - p), ks.append((k, n))
            ax.bar(xs, vals, width, color=colour, label=d, edgecolor=SURFACE, linewidth=0.8)
            ax.errorbar(xs, vals, yerr=[lo, hi], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=0)
            # Marker at every value, so a zero-height bar is still visible (and identity is not colour alone).
            ax.scatter(xs, vals, marker=marker, s=14, color=colour, edgecolor=SURFACE, linewidth=0.5, zorder=3)
            for x, p, h, (k, n) in zip(xs, vals, hi, ks):
                if n:
                    ax.annotate(f"{k}", (x, p + h), xytext=(0, 1.5), textcoords="offset points", ha="center",
                                fontsize=5.6, color=INK2)
        ax.set_xticks(range(len(variants)), [COL_LABEL[v] for v in variants])
        ax.set_title((labels or {}).get(fam, fam), loc="left", fontsize=7.5)
        ax.set_ylim(0, 1.12)
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
    axes[0][0].set_ylabel("attack success rate\n(successes of 30 above each bar)")
    axes[0][0].legend(ncol=4, loc="lower left", bbox_to_anchor=(0, 1.12))
    return save(fig, out_dir, stem)


def fig_attribution(d2: dict, mon: dict, out_dir: Path, stem: str = "fig7_attribution") -> list[Path]:
    setup_style()
    checks = ["K1_known_sender", "K2_signature", "K3_recipient", "K4_fresh_nonce", "K5_timestamp", "K6_authorised"]
    rules = ["R1_account_on_file", "R2_amount_le_invoice", "R3_not_already_paid", "R4_provenance"]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6))
    for ax, data, cats, title in ((axes[0], d2, checks, "D2/D3: transport checks that failed"),
                                  (axes[1], mon, rules, "Monitor: first rule that blocked")):
        cols = [c for c in COLS if c in data and sum(data[c].values())]
        bottom = np.zeros(len(cols))
        for i, cat in enumerate(cats):
            vals = np.array([data[c].get(cat, 0) for c in cols], dtype=float)
            if not vals.any():
                continue
            ax.bar(range(len(cols)), vals, 0.6, bottom=bottom, color=CAT[i], label=cat.split("_", 1)[0] + " " +
                   cat.split("_", 1)[1].replace("_", " "), edgecolor=SURFACE, linewidth=1)
            bottom += vals
        ax.set_xticks(range(len(cols)), cols, rotation=0)
        ax.set_title(title, loc="left")
        ax.set_ylabel("count (trials)")
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.legend(fontsize=6.5, loc="upper left", bbox_to_anchor=(0, -0.14), ncol=2)
    return save(fig, out_dir, stem)


def fig_funnel(funnel: dict, out_dir: Path, stem: str = "fig8_a5_funnel", label: str = "") -> list[Path]:
    """funnel[(defence, variant)] = (shares f1, f2, f3, f4_executed), n"""
    setup_style()
    stages = ["records relayed\nMallory's account", "orchestrator\ninstructed it", "finance tried\nto pay it",
              "payment\nexecuted"]
    defs = [d for d in ("D2", "D3") if any(k[0] == d for k in funnel)]
    fig, axes = plt.subplots(1, max(1, len(defs)), figsize=(3.5 * max(1, len(defs)), 2.5), sharey=True, squeeze=False)
    for ax, d in zip(axes[0], defs):
        for i, v in enumerate(["A5b", "A5p", "A5d"]):
            if (d, v) not in funnel:
                continue
            shares, n = funnel[(d, v)]
            # Nested widths and sizes (thick to thin): identical series stay visible without moving any value.
            ax.plot(range(4), shares, marker=MARKERS[i], color=CAT[i], lw=3.2 - 1.0 * i, ms=8 - 2 * i,
                    label=f"{COL_LABEL[v]} (n={n})", zorder=2 + i)
        ax.set_xticks(range(4), stages, fontsize=6.5)
        ax.set_ylim(-0.05, 1.08)
        ax.set_title(f"A5 under {d}{label}", loc="left")
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)
        ax.legend(loc="lower left", fontsize=6.5)
    axes[0][0].set_ylabel("share of trials")
    return save(fig, out_dir, stem)


def fig_oracle_vs_llm(oracle: dict, llm: dict, rows: list[str], out_dir: Path, stem: str = "fig9_oracle_vs_llm") -> list[Path]:
    setup_style()
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 0.9 * len(rows) + 1.8))
    heatmap(axes[0], oracle, rows, COLS, "Protocol level: deterministic agent that believes everything",
            binary_labels=True)
    heatmap(axes[1], llm, rows, COLS, "Model level: LLM agents (family 1)")
    fig.subplots_adjust(hspace=0.75)
    return save(fig, out_dir, stem)


def fig_architecture(out_dir: Path, stem: str = "fig1_architecture") -> list[Path]:
    setup_style()
    fig, ax = plt.subplots(figsize=(7.0, 3.7))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 54)
    ax.axis("off")

    def box(x, y, w, h, title, sub="", fc="#f0efec", ec=BASELINE):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc=fc, ec=ec, lw=0.9))
        lines = sub.count("\n") + 1 if sub else 0
        ax.text(x + w / 2, y + h / 2 + 1.4 * lines, title, ha="center", va="center", fontsize=7.8, color=INK,
                weight="bold")
        if sub:
            ax.text(x + w / 2, y + h / 2 - 1.6, sub, ha="center", va="center", fontsize=6.3, color=INK2,
                    linespacing=1.25)

    def arrow(x0, y0, x1, y1, colour=INK2, style="-|>", ls="-"):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=8, color=colour, lw=1,
                                     linestyle=ls, shrinkA=0, shrinkB=0))

    # Top: world data read by Records' tool (A5's target)
    box(40, 44, 18, 7, "Supplier records", "world data", fc="#ffffff")
    # Agents
    box(4, 29, 11, 9, "User", "task T")
    box(18, 29, 18, 9, "Orchestrator", "LLM, no tools")
    box(40, 29, 18, 9, "Records", "LLM +\nlookup_supplier")
    box(62, 29, 18, 9, "Finance", "LLM +\nsend_payment")
    box(84, 29, 15, 9, "Monitor (D3)", "R1-R4 vs\nground truth", fc="#ffffff", ec=CAT[3])
    box(84, 14, 15, 8, "Ledger", "decides success", fc="#ffffff")
    # Bus
    ax.add_patch(FancyBboxPatch((18, 17), 62, 5, boxstyle="round,pad=0.3,rounding_size=1", fc="#ffffff", ec=CAT[0], lw=1))
    ax.text(49, 19.5, "Agent bus: D1 handshake · D2 signature + nonce + timestamp (checked outside the LLM)",
            ha="center", va="center", fontsize=6.2, color=INK)
    box(4, 2, 34, 9, "Mallory (attack code, not a model)", "A1-A4 act on the bus:\ninject · replay · tamper · stolen key",
        fc="#ffffff", ec=CAT[7])
    # Arrows
    arrow(15.4, 33.5, 17.6, 33.5)
    for x in (27, 49, 71):
        arrow(x, 28.6, x, 22.4, style="<|-|>")
    arrow(49, 43.6, 49, 38.4)            # lookup_supplier reads the record
    arrow(80.4, 33.5, 83.6, 33.5)        # finance -> monitor (payment request)
    arrow(91.5, 28.6, 91.5, 22.4)        # monitor -> ledger
    arrow(30, 11.4, 34, 16.6, colour=CAT[7], ls="--")
    ax.plot([3.6, 1.2, 1.2, 39.6], [6.5, 6.5, 47.5, 47.5], color=CAT[7], lw=1, ls=":")
    arrow(37.5, 47.5, 39.6, 47.5, colour=CAT[7])
    ax.text(20, 49.2, "A5: poisons one supplier record; never touches the bus", ha="center", fontsize=6.3, color=INK2)
    return save(fig, out_dir, stem)


def fig_lines(series: dict, xlabel: str, ylabel: str, out_dir: Path, stem: str, logx: bool = False,
              ylim=(-0.03, 1.05)) -> list[Path]:
    """series[label] = (xs, ys). Up to 6 series, each with its own marker and a legend."""
    setup_style()
    fig, ax = plt.subplots(figsize=(3.6, 2.6))
    for i, (label, (xs, ys)) in enumerate(series.items()):
        ax.plot(xs, ys, marker=MARKERS[i], color=CAT[i], ms=4, label=label)
    if logx:
        ax.set_xscale("log")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_ylim(*ylim)
    ax.yaxis.grid(True)
    ax.set_axisbelow(True)
    ax.legend(fontsize=6.5)
    return save(fig, out_dir, stem)
