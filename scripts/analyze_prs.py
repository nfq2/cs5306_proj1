#!/usr/bin/env python3
"""Validate and label collected PRs; write descriptive tables (standard library only)."""

import argparse
from collections import defaultdict
import csv
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/prs_2017_2026_yearly_200.csv"
COUNTS = "additions deletions changed_files commits review_count reviewer_count approval_count change_request_count dismissed_review_count".split()
DIMENSIONS = ["size_band", "author_kind", "association_group", "author_association",
              "review_profile", "reviewer_band", "merge_time_band", "file_band", "commit_band"]
LABELS = {
    "size_band": {
        "zero": "0 changed lines", "xs": "1–10 changed lines", "small": "11–50 changed lines",
        "medium": "51–200 changed lines", "large": "201–1,000 changed lines", "xl": "1,001+ changed lines"},
    "author_kind": {"user": "User account", "bot": "Bot account", "other_unknown": "Other / unknown account"},
    "association_group": {"member_owner_collaborator": "Member / owner / collaborator",
                          "contributor_first_time": "Contributor / first-time contributor",
                          "none": "No recorded association", "other_unknown": "Other / unknown association"},
    "review_profile": {
        "no_submitted_review": "No submitted review",
        "review_without_decision": "Review(s), no approval or change request",
        "approval_without_change_request": "Approval(s), no change request",
        "change_request_without_approval": "Change request(s), no approval",
        "approval_and_change_request": "Both approval and change request"},
    "reviewer_band": {"zero": "0 identifiable reviewers", "one": "1 identifiable reviewer",
                      "two": "2 identifiable reviewers", "three_plus": "3+ identifiable reviewers"},
    "merge_time_band": {"under_hour": "Under 1 hour", "hour_to_day": "1 hour to under 1 day",
                        "day_to_week": "1 to under 7 days", "week_to_month": "7 to under 30 days",
                        "month_plus": "30+ days"},
    "file_band": {"zero": "0 files", "one": "1 file", "two_to_five": "2–5 files", "six_plus": "6+ files"},
    "commit_band": {"zero": "0 commits", "one": "1 commit", "two_to_five": "2–5 commits", "six_plus": "6+ commits"},
}


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must have a timezone")
    return parsed.astimezone(timezone.utc)


def quantile(values, fraction):
    """Linearly interpolated sample quantile; blank for an empty denominator."""
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def size_band(churn):
    for upper, label in [(0, "zero"), (10, "xs"), (50, "small"), (200, "medium"), (1000, "large")]:
        if churn <= upper:
            return label
    return "xl"


def breadth_band(count):
    return "zero" if count == 0 else "one" if count == 1 else "two_to_five" if count <= 5 else "six_plus"


def derive(row):
    result = dict(row)
    for column in COUNTS:
        result[column] = int(row[column])
        if result[column] < 0:
            raise ValueError(f"{column} cannot be negative")
    created, merged = parse_time(row["created_at"]), parse_time(row["merged_at"])
    days = (merged - created).total_seconds() / 86400
    if days < 0:
        raise ValueError("Merge predates creation")
    reviews, approvals, changes = (result[k] for k in ("review_count", "approval_count", "change_request_count"))
    if approvals + changes > reviews or result["reviewer_count"] > reviews or result["dismissed_review_count"] > reviews:
        raise ValueError("Review counts are inconsistent")
    for column, expected in [("has_review", reviews > 0), ("has_change_request", changes > 0)]:
        if str(row[column]).lower() not in (str(expected).lower(), str(int(expected))):
            raise ValueError(f"{column} disagrees with event count")
        result[column] = expected
    if not reviews:
        profile = "no_submitted_review"
    elif approvals and changes:
        profile = "approval_and_change_request"
    elif changes:
        profile = "change_request_without_approval"
    elif approvals:
        profile = "approval_without_change_request"
    else:
        profile = "review_without_decision"
    association = row["author_association"].upper()
    association_group = ("member_owner_collaborator" if association in {"MEMBER", "OWNER", "COLLABORATOR"}
                         else "contributor_first_time" if association in {"CONTRIBUTOR", "FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"}
                         else "none" if association == "NONE" else "other_unknown")
    reviewers = result["reviewer_count"]
    churn = result["additions"] + result["deletions"]
    result.update(merge_year=merged.year, merge_month=merged.strftime("%Y-%m"),
                  merge_month_day=merged.strftime("%m-%d"), created_year=created.year,
                  merge_days=days, churn=churn, size_band=size_band(churn),
                  author_kind={"User": "user", "Bot": "bot"}.get(row["author_type"], "other_unknown"),
                  association_group=association_group, review_profile=profile,
                  has_approval=approvals > 0,
                  reviewer_band="zero" if not reviewers else "one" if reviewers == 1 else "two" if reviewers == 2 else "three_plus",
                  merge_time_band="under_hour" if days < 1 / 24 else "hour_to_day" if days < 1 else "day_to_week" if days < 7 else "week_to_month" if days < 30 else "month_plus",
                  file_band=breadth_band(result["changed_files"]), commit_band=breadth_band(result["commits"]))
    return result


def load_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = set(COUNTS + "repo pr_number created_at merged_at author_login author_type author_association has_review has_change_request collection_status".split())
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        source = list(reader)
    keys = [(r["repo"], r["pr_number"]) for r in source]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate repo/PR identifiers; do not concatenate overlapping samples")
    if len({r["repo"] for r in source}) != 1:
        raise ValueError("Analyze one repository at a time")
    rows, excluded = [], []
    for row in source:
        if row["collection_status"] != "ok":
            excluded.append({"repo": row["repo"], "pr_number": row["pr_number"], "reason": "collection_status != ok"})
            continue
        try:
            rows.append(derive(row))
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Invalid successful PR #{row['pr_number']}: {exc}") from exc
    if not rows:
        raise ValueError("No successful rows to analyze")
    return rows, excluded, source


def summarize(rows):
    n = len(rows)
    reviewed = [r for r in rows if r["has_review"]]
    positive = [r for r in rows if r["has_change_request"]]
    def pct(numerator, denominator):
        return 100 * numerator / denominator if denominator else None
    result = dict(n=n, reviewed_n=len(reviewed), change_requested_n=len(positive),
                  approved_n=sum(r["has_approval"] for r in rows),
                  reviewed_pct=pct(len(reviewed), n), change_requested_pct=pct(len(positive), n),
                  approved_pct=pct(sum(r["has_approval"] for r in rows), n),
                  change_requested_among_reviewed_pct=pct(len(positive), len(reviewed)),
                  mean_change_events=mean(r["change_request_count"] for r in rows) if n else None,
                  mean_change_events_when_present=mean(r["change_request_count"] for r in positive) if positive else None,
                  mean_review_events=mean(r["review_count"] for r in rows) if n else None,
                  median_identifiable_reviewers=quantile([r["reviewer_count"] for r in rows], .5),
                  unique_identifiable_authors_n=len({r["author_login"] for r in rows if r["author_login"]}),
                  small_group=n < 30, sparse_change_requests=len(positive) < 10)
    for column in ("merge_days", "churn", "changed_files", "commits"):
        values = [r[column] for r in rows]
        for name, fraction in [("q25", .25), ("median", .5), ("q75", .75), ("p90", .9)]:
            result[f"{name}_{column}"] = quantile(values, fraction)
    return result


def grouped_summary(rows, dimensions):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[d] for d in dimensions)].append(row)
    return [dict(zip(dimensions, key), **summarize(group)) for key, group in sorted(groups.items())]


def write_csv(path, rows, fields=None):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def analyze(input_path, output, start, end):
    if start > end:
        raise ValueError("Study start must precede study end")
    rows, excluded, source = load_rows(input_path)
    for row in source:
        if row.get("merged_at") and not start <= parse_time(row["merged_at"]).date() <= end:
            raise ValueError("A merge date is outside --start/--end; specify the input's study window")
    manifest_path = input_path.with_suffix(".sample.json")
    warnings = ["All summaries are unweighted descriptions of sampled merged PRs, not population totals or causal effects."]
    manifest_verified = False
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        config = manifest["config"]
        if config["repo"] != rows[0]["repo"] or config["start"] != str(start) or config["end"] != str(end):
            raise ValueError("Manifest repository/date window disagrees with analysis arguments")
        selected = [str(p["number"]) for p in manifest["sample"]]
        if len(selected) != len(set(selected)) or set(selected) != {r["pr_number"] for r in source}:
            raise ValueError("CSV does not match the complete selected sample in the manifest")
        manifest_verified = not excluded
    else:
        warnings.append("Sampling manifest absent: selection/completeness and population weights cannot be verified.")
    if excluded:
        warnings.append(f"Excluded {len(excluded)} unsuccessful rows; missingness may bias summaries.")
    warnings.extend([
        "User accounts are not proof of human-only work; reviewer account types and AI use are unavailable.",
        "Review events are not revision rounds; profile labels do not establish the order of events.",
        "Associations and change-size fields are recorded at collection, not verified historical covariates.",
        "Repeated authors and a single repository limit generalization; no independence-based significance tests are reported.",
    ])
    years = sorted({r["merge_year"] for r in rows})
    partial_years = [y for y in years if start > date(y, 1, 1) or end < date(y, 12, 31)]
    lower_md, upper_md = start.strftime("%m-%d"), end.strftime("%m-%d")
    if lower_md > upper_md:
        raise ValueError("Partial-year boundaries have no common calendar window")
    cohorts = {
        "all": rows,
        "user_accounts_only": [r for r in rows if r["author_kind"] == "user"],
        "complete_years_only": [r for r in rows if r["merge_year"] not in partial_years],
        "matched_calendar_window": [r for r in rows if lower_md <= r["merge_month_day"] <= upper_md],
    }
    yearly, subgroups, overall = [], [], []
    for cohort, subset in cohorts.items():
        overall.append(dict(cohort=cohort, **summarize(subset)))
        for record in grouped_summary(subset, ["merge_year"]):
            yearly.append(dict(cohort=cohort, partial_year=record["merge_year"] in partial_years, **record))
        for dimension in DIMENSIONS:
            for record in grouped_summary(subset, ["merge_year", dimension]):
                value = record.pop(dimension)
                subgroups.append(dict(cohort=cohort, dimension=dimension, label=value,
                                      display_label=LABELS.get(dimension, {}).get(value, value), **record))
    metadata = dict(input=str(input_path.resolve()), input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
                    repo=rows[0]["repo"], study_start=str(start), study_end=str(end), partial_years=partial_years,
                    source_n=len(source), analyzed_n=len(rows), excluded_n=len(excluded),
                    manifest_verified=manifest_verified, warnings=warnings,
                    matched_calendar_window=[lower_md, upper_md],
                    estimand="Unweighted sampled merged PRs; pooled summaries reflect the sample's year mix",
                    quantiles="Linear interpolation at (n-1)*p", minimum_descriptive_group_n=30,
                    sparse_change_request_threshold=10)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "labeled_prs.csv", rows)
    write_csv(output / "yearly_summary.csv", yearly)
    write_csv(output / "yearly_subgroups.csv", subgroups)
    write_csv(output / "cohort_summary.csv", overall)
    write_csv(output / "excluded_rows.csv", excluded, ["repo", "pr_number", "reason"])
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (output / "label_dictionary.json").write_text(json.dumps(LABELS, indent=2, ensure_ascii=False) + "\n")
    report = ["# Descriptive PR analysis", "", f"{metadata['repo']}: {len(rows):,} successful sampled PRs.", "",
              "| Merge year | n | Reviewed (%) | Change request (%) | Change request among reviewed (%) | Median merge hours | Median changed lines |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for r in yearly:
        if r["cohort"] == "all":
            conditional = r['change_requested_among_reviewed_pct']
            report.append(f"| {r['merge_year']}{'*' if r['partial_year'] else ''} | {r['n']} | {r['reviewed_pct']:.1f} | {r['change_requested_pct']:.1f} | {f'{conditional:.1f}' if conditional is not None else 'NA'} | {r['median_merge_days'] * 24:.2f} | {r['median_churn']:g} |")
    report += ["", "*Partial study year. Rates use all sampled PRs unless explicitly conditional on reviewed PRs.", "",
               "Use yearly_subgroups.csv to compare size, account type, recorded association, review profile, reviewers, files, commits and merge-time categories within each year.", "",
               "The user-account and matched-calendar-window cohorts are sensitivity checks. Every table includes denominators; groups below 30 PRs and change-request counts below 10 are flagged. These are reporting flags, not significance thresholds.", "", "## Interpretation", ""]
    report += [f"- {warning}" for warning in warnings]
    (output / "report.md").write_text("\n".join(report) + "\n")
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2017, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2026, 9, 25))
    args = parser.parse_args()
    output = args.output or ROOT / "analysis" / args.input.stem
    try:
        metadata = analyze(args.input, output, args.start, args.end)
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    print(f"Analyzed {metadata['analyzed_n']:,} PRs; outputs: {output}")
    for warning in metadata["warnings"]:
        print(f"Note: {warning}")


if __name__ == "__main__":
    main()
