#!/usr/bin/env python3
"""Plot the tables produced by analyze_prs.py; requires matplotlib."""

import argparse
import csv
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "analysis/prs_2017_2026_yearly_200")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "graphs" / args.input.name / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    yearly = read_csv(args.input / "yearly_summary.csv")
    groups = read_csv(args.input / "yearly_subgroups.csv")
    labels = json.loads((args.input / "label_dictionary.json").read_text())
    metadata = json.loads((args.input / "metadata.json").read_text())
    primary = [r for r in yearly if r["cohort"] == "all"]
    years = [int(r["merge_year"]) for r in primary]
    ticks = [f"{year}{'*' if year in metadata['partial_years'] else ''}" for year in years]
    colors = ["#2677a7", "#d17932", "#419b86", "#9273b5", "#cf687b", "#667580"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "axes.labelcolor": "#263d4b",
                         "text.color": "#263d4b", "savefig.facecolor": "white"})
    note = (f"{metadata['repo']} | {metadata['analyzed_n']:,} sampled merged PRs | "
            f"{metadata['study_start']} through {metadata['study_end']}\n"
            "Unweighted descriptive summaries. Reviews through merge; events are not revision rounds. "
            + ("*Partial year. " if metadata["partial_years"] else "")
            + ("Sampling manifest unavailable." if not metadata["manifest_verified"] else ""))

    def values(key, records=primary):
        return [float(r[key]) if r[key] else float("nan") for r in records]

    def finish_axis(ax, title, ylabel, percent=False):
        ax.set(title=title, xlabel="Merge year", ylabel=ylabel)
        ax.set_xticks(years, ticks, rotation=35)
        ax.grid(axis="y", color="#e4eaee", linewidth=.8)
        ax.set_axisbelow(True)
        if percent:
            ax.set_ylim(0, 105)
            ax.yaxis.set_major_formatter(PercentFormatter(100))

    def save(fig, name, bottom=.16):
        fig.subplots_adjust(left=.065, right=.985, top=.84, bottom=bottom,
                            hspace=.72, wspace=.38)
        fig.text(.025, .025, note, fontsize=8, linespacing=1.6)
        for extension in ("png", "svg"):
            fig.savefig(output / f"{name}.{extension}", dpi=160)
        plt.close(fig)

    def composition(ax, dimension, title):
        lookup = {(int(r["merge_year"]), r["label"]): int(r["n"]) for r in groups
                  if r["cohort"] == "all" and r["dimension"] == dimension}
        totals = {int(r["merge_year"]): int(r["n"]) for r in primary}
        bottom = [0.] * len(years)
        for index, (key, display) in enumerate(labels[dimension].items()):
            heights = [100 * lookup.get((year, key), 0) / totals[year] for year in years]
            if not any(heights):
                continue
            ax.bar(years, heights, bottom=bottom, color=colors[index % len(colors)], label=display, width=.7)
            bottom = [a + b for a, b in zip(bottom, heights)]
        finish_axis(ax, title, "Share of sampled PRs (%)", percent=True)
        ax.legend(loc="upper center", bbox_to_anchor=(.5, -.42), frameon=False, fontsize=8, ncol=2)

    fig, axes = plt.subplots(2, 3, figsize=(19, 11))
    fig.suptitle("Review activity, merge time and sample composition", fontsize=20, x=.03, ha="left")
    ax = axes[0, 0]
    for key, display, color in [("reviewed_pct", "Any submitted review", colors[0]),
                                ("approved_pct", "Any approval event", colors[2])]:
        ax.plot(years, values(key), "o-", label=display, color=color)
    finish_axis(ax, "Review and approval coverage", "Share of sampled PRs (%)", percent=True)
    ax.legend(frameon=False, fontsize=9)
    ax = axes[0, 1]
    ax.plot(years, values("change_requested_pct"), "o-", label="Among all sampled PRs", color=colors[1])
    ax.plot(years, values("change_requested_among_reviewed_pct"), "s--", label="Among reviewed PRs", color=colors[3])
    finish_axis(ax, "PRs with a change request", "PRs with ≥1 event (%)")
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(PercentFormatter(100))
    ax.legend(frameon=False, fontsize=9)
    ax = axes[0, 2]
    ax.plot(years, [24 * v for v in values("median_merge_days")], "o-", color=colors[0], label="Median")
    ax.fill_between(years, [24 * v for v in values("q25_merge_days")],
                    [24 * v for v in values("q75_merge_days")], color=colors[0], alpha=.15, label="25th–75th percentiles")
    ax.set_yscale("symlog", linthresh=1)
    finish_axis(ax, "Elapsed time from opening to merge", "Hours (linear to 1 h, then log)")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, fontsize=9)
    composition(axes[1, 0], "size_band", "Changed-line distribution")
    composition(axes[1, 1], "review_profile", "Review event profiles (no ordering implied)")
    composition(axes[1, 2], "association_group", "Recorded author association")
    save(fig, "dimensions_overview", bottom=.25)

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle("Sensitivity checks by merge year", fontsize=20, x=.03, ha="left")
    for i, (cohort, display) in enumerate([
        ("all", "All sampled PRs"), ("user_accounts_only", "User accounts only"),
        ("matched_calendar_window", "Same calendar window each year")]):
        records = [r for r in yearly if r["cohort"] == cohort]
        xs = [int(r["merge_year"]) for r in records]
        for ax, key in zip(axes, ["reviewed_pct", "change_requested_pct", "median_merge_days"]):
            ys = values(key, records)
            if key == "median_merge_days":
                ys = [24 * value for value in ys]
            ax.plot(xs, ys, marker=["o", "s", "^"][i], linestyle=["-", "--", ":"][i],
                    color=colors[i], label=display)
    finish_axis(axes[0], "Any submitted review", "Share of cohort PRs (%)", percent=True)
    finish_axis(axes[1], "Any change request", "Share of cohort PRs (%)")
    axes[1].set_ylim(bottom=0)
    axes[1].yaxis.set_major_formatter(PercentFormatter(100))
    finish_axis(axes[2], "Median merge time", "Hours (linear to 1 h, then log)")
    axes[2].set_yscale("symlog", linthresh=1)
    axes[2].set_ylim(bottom=0)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="lower center", bbox_to_anchor=(.5, .15),
               frameon=False, fontsize=10, ncol=3)
    save(fig, "sensitivity_checks", bottom=.34)
    print(f"Saved overview and sensitivity figures (PNG/SVG): {output}")


if __name__ == "__main__":
    main()
