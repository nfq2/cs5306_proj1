#!/usr/bin/env python3
"""Create descriptive figures from successfully collected PRs."""

import argparse
import csv
from datetime import datetime
import json
import os
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".mplconfig"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, PercentFormatter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/prs_2017_2026_yearly_200.csv")
    parser.add_argument("--output", type=Path, help="Default: graphs/<input filename without extension>")
    args = parser.parse_args()
    if args.output is None:
        args.output = ROOT / "graphs" / args.input.stem
    with args.input.open(newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["collection_status"] == "ok"]
    if not rows:
        parser.error("No successfully collected PRs to plot.")
    manifest = json.loads(args.input.with_suffix(".sample.json").read_text())
    config = manifest["config"]
    expected = {str(item["number"]) for item in manifest["sample"]}
    if len(rows) != len(expected) or {r["pr_number"] for r in rows} != expected:
        parser.error("Collection is incomplete or has duplicate/failed rows; finish collection before plotting.")
    years = sorted({int(row["merged_at"][:4]) for row in rows})
    grouped = [[row for row in rows if int(row["merged_at"][:4]) == year] for year in years]
    counts = [len(group) for group in grouped]
    review_share = [100 * mean(int(r["review_count"]) > 0 for r in group) for group in grouped]
    change_share = [100 * mean(int(r["change_request_count"]) > 0 for r in group) for group in grouped]
    changes = [mean(int(r["change_request_count"]) for r in group) for group in grouped]
    def parse(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    days = [median((parse(r["merged_at"]) - parse(r["created_at"])).total_seconds() / 86400
                   for r in group) for group in grouped]
    partial = int(config["end"][:4]) if config["end"][5:] != "12-31" else None
    labels = [f"{year}{'*' if year == partial else ''}" for year in years]
    sampling_note = (f"Random sample: up to {config['per_year']} PRs/year"
                     if config.get("mode") == "stratified_yearly"
                     else f"Systematic sample: every {config['every']}th PR")
    note = (f"{config['repo']} | {len(rows):,} sampled merged PRs | "
            f"{config['start']} to {config['end']}\n"
            f"{sampling_note}; seed {config['seed']}. Human and bot authors included.\n"
            "Reviews counted through merge; change requests are events, not revision rounds. "
            + (f"*{partial} is a partial year." if partial else ""))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.titlesize": 14, "axes.titleweight": "bold",
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": "#B4BEC8", "text.color": "#213547",
                         "axes.labelcolor": "#213547", "xtick.color": "#435363",
                         "ytick.color": "#435363", "savefig.facecolor": "white"})
    blue, orange = "#2375A8", "#BA521F"

    def draw(ax, kind):
        ax.set_xticks(years, labels, rotation=30 if len(years) > 8 else 0)
        ax.set_xlabel("Merge year")
        ax.grid(axis="y", color="#E6EBEF", linewidth=0.8)
        ax.set_axisbelow(True)
        ax.set_xlim(min(years) - .55, max(years) + .55)
        if kind == 0:
            bars = ax.bar(years, counts, color=blue, width=.62)
            ax.bar_label(bars, padding=5, fontsize=10)
            ax.set(title="Sampled pull requests", ylabel="Sampled PRs (count)", ylim=(0, max(counts)*1.2))
            ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        elif kind == 1:
            ax.plot(years, review_share, color=blue, marker="o", label="Any submitted review")
            ax.plot(years, change_share, color=orange, marker="s", label="Any change request")
            for series in (review_share, change_share):
                for year, value in zip(years, series):
                    ax.annotate(f"{value:.1f}%", (year, value), xytext=(0, 9),
                                textcoords="offset points", ha="center", fontsize=9)
            ax.set(title="How often do PRs receive review?", ylabel="Share of sampled PRs (%)", ylim=(0, 112))
            ax.set_yticks(range(0, 101, 20))
            ax.yaxis.set_major_formatter(PercentFormatter(100))
            ax.legend(loc="upper left", frameon=False, fontsize=9)
        elif kind == 2:
            bars = ax.bar(years, changes, color=orange, width=.62)
            ax.bar_label(bars, labels=[f"{v:.3f}" for v in changes], padding=5, fontsize=10)
            ax.set(title="Change-request events per PR", ylabel="Mean events per sampled PR",
                   ylim=(0, max(max(changes)*1.25, .05)))
            ax.text(.02, .95, "Includes PRs with zero events", transform=ax.transAxes,
                    va="top", fontsize=9, color="#435363")
        else:
            ax.plot(years, days, color=blue, marker="o", linewidth=2)
            for year, value in zip(years, days):
                ax.annotate(f"{value:.2f}", (year, value), xytext=(0, 10),
                            textcoords="offset points", ha="center", fontsize=10)
            ax.set(title="Typical time from opening to merge", ylabel="Median elapsed days",
                   ylim=(0, max(days)*1.3))

    args.output.mkdir(parents=True, exist_ok=True)
    names = ["sample_size_by_year", "review_share_by_year", "change_requests_by_year", "merge_time_by_year"]
    for kind, name in enumerate(names):
        fig, ax = plt.subplots(figsize=(11, 6.3))
        draw(ax, kind)
        fig.subplots_adjust(left=.12, right=.97, bottom=.25, top=.89)
        fig.text(.04, .045, note, fontsize=8, linespacing=1.7)
        for suffix in ("png", "svg"):
            fig.savefig(args.output / f"{name}.{suffix}", dpi=180)
        plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    for kind, ax in enumerate(axes.flat):
        draw(ax, kind)
    fig.suptitle(f"{config['repo']}: review activity, {years[0]}–{years[-1]}", x=.065, ha="left",
                 fontsize=21, fontweight="bold", y=.97)
    fig.subplots_adjust(left=.075, right=.97, top=.88, bottom=.19, hspace=.48, wspace=.24)
    fig.text(.065, .035, note + "\nDescriptive trends; these graphs do not identify the effect of AI use.",
             fontsize=10, linespacing=1.7)
    for suffix in ("png", "svg"):
        fig.savefig(args.output / f"overview.{suffix}", dpi=180)
    plt.close(fig)
    print("year, sample_n, reviewed_pct, change_requested_pct, mean_change_events, median_days_to_merge")
    for values in zip(years, counts, review_share, change_share, changes, days):
        print(values)
    print(f"Saved four figures and an overview (PNG and SVG) to {args.output}")


if __name__ == "__main__":
    main()
