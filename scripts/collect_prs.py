#!/usr/bin/env python3
"""Collect a reproducible systematic sample of merged GitHub PRs (stdlib only)."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FIELDS = """repo pr_number url title created_at merged_at closed_at updated_at fetched_at
author_login author_type author_association additions deletions changed_files commits
review_count reviewer_count approval_count change_request_count has_review
has_change_request dismissed_review_count collection_status error""".split()


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def load_token(path):
    token = os.environ.get("GITHUB_TOKEN")
    if not token and path.exists():
        for line in path.read_text().splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key == "GITHUB_TOKEN":
                token = value.strip().strip("\"'")
                break
    if not token:
        raise RuntimeError("Set GITHUB_TOKEN or add it to the project .env file.")
    return token


class GitHub:
    def __init__(self, token):
        self.token = token
        self.last_request = 0

    def get(self, path, **params):
        url = "https://api.github.com" + path
        if params:
            url += "?" + urlencode(params)
        for attempt in range(6):
            # Search has a separate quota; keep all requests sequential.
            gap = 2.1 if path == "/search/issues" else 0.15
            time.sleep(max(0, gap - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            request = Request(url, headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
                "User-Agent": "cs5306-pr-study",
            })
            try:
                with urlopen(request, timeout=60) as response:
                    return json.load(response)
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace").lower()
                rate_limited = exc.code == 429 or (
                    exc.code == 403 and ("rate limit" in body or
                                        exc.headers.get("X-RateLimit-Remaining") == "0"))
                if not rate_limited and exc.code not in (500, 502, 503, 504):
                    # Do not include response bodies or authentication headers in errors.
                    raise RuntimeError(f"GitHub HTTP {exc.code} for {path}") from None
                delay = 2 ** (attempt + 1)
                if rate_limited:
                    delay = max(60, float(exc.headers.get("Retry-After", "0")))
                    if exc.headers.get("X-RateLimit-Remaining") == "0":
                        delay = max(delay, float(exc.headers.get(
                            "X-RateLimit-Reset", "0")) - time.time() + 2)
            except (URLError, TimeoutError):
                delay = 2 ** (attempt + 1)
            if attempt == 5:
                raise RuntimeError(f"GitHub request failed after retries: {path}")
            print(f"Retrying {path} in {delay:.0f}s", flush=True)
            while delay > 0:
                chunk = min(delay, 30)
                time.sleep(chunk)
                delay -= chunk

    def pages(self, path):
        results = []
        page = 1
        while True:
            batch = self.get(path, per_page=100, page=page)
            if not isinstance(batch, list):
                raise RuntimeError(f"Expected a list from {path}")
            results.extend(batch)
            if len(batch) < 100:
                return results
            page += 1


def discover(api, repo, start, end, cache):
    """Split inclusive date windows until each complete search fits under 1,000."""
    path = cache / f"search_{start}_{end}.json"
    if path.exists():
        return json.loads(path.read_text())
    query = f"repo:{repo} is:pr is:merged merged:{start}..{end}"
    first = api.get("/search/issues", q=query, sort="created", order="asc",
                    per_page=100, page=1)
    if first["total_count"] > 1000 or first.get("incomplete_results"):
        if start == end:
            raise RuntimeError(f"Search too large/incomplete for {start}; use narrower time windows.")
        midpoint = start + (end - start) // 2
        items = discover(api, repo, start, midpoint, cache) + discover(
            api, repo, midpoint + timedelta(days=1), end, cache)
    else:
        items = first["items"]
        for page in range(2, (first["total_count"] + 99) // 100 + 1):
            result = api.get("/search/issues", q=query, sort="created", order="asc",
                             per_page=100, page=page)
            if result.get("incomplete_results") or result["total_count"] != first["total_count"]:
                raise RuntimeError("Search changed or was incomplete; retry collection.")
            items.extend(result["items"])
        if len({item["number"] for item in items}) != first["total_count"]:
            raise RuntimeError("Search count mismatch; refusing to sample incomplete results.")
    compact = []
    for item in items:
        merged_at = item.get("merged_at") or item.get("pull_request", {}).get("merged_at")
        if not merged_at:
            merged_at = api.get(f"/repos/{repo}/pulls/{item['number']}")["merged_at"]
        if not merged_at or not start <= parse_time(merged_at).date() <= end:
            raise RuntimeError("Search returned a PR outside the requested merge dates.")
        compact.append({"number": item["number"], "merged_at": merged_at})
    save_json(path, compact)
    print(f"Indexed {start} through {end}: {len(compact)} PRs", flush=True)
    return compact


def select_sample(items, every, seed):
    ordered = sorted({item["number"]: item for item in items}.values(),
                     key=lambda item: (parse_time(item["merged_at"]), item["number"]))
    offset = random.Random(seed).randrange(every)
    return ordered[offset::every], offset + 1


def pilot_sample(api, repo, start, end, count):
    """One search request in the first 31 days; this is a convenience sample."""
    pilot_end = min(end, start + timedelta(days=30))
    result = api.get("/search/issues",
                     q=f"repo:{repo} is:pr is:merged merged:{start}..{pilot_end}",
                     sort="created", order="asc", per_page=count, page=1)
    if result.get("incomplete_results"):
        raise RuntimeError("Pilot search was incomplete; retry or choose another --start.")
    sample = [{"number": item["number"],
               "merged_at": item.get("pull_request", {}).get("merged_at", "")}
              for item in result["items"][:count]]
    print(f"Pilot window: {start} through {pilot_end}; selected {len(sample)} PRs "
          "without full indexing (not the systematic research sample).", flush=True)
    return sample


def review_metrics(reviews, merged_at, events=()):
    cutoff = parse_time(merged_at)
    submitted = {r["id"]: r for r in reviews if r.get("submitted_at") and
                 parse_time(r["submitted_at"]) <= cutoff and r["state"] != "PENDING"}
    original = {}
    for event in events:
        if event.get("event") == "review_dismissed":
            dismissal = event.get("dismissed_review", {})
            if dismissal.get("review_id") is not None:
                original[str(dismissal["review_id"])] = dismissal.get("state", "").upper()
    states = []
    for review in submitted.values():
        state = review["state"]
        if state == "DISMISSED":
            state = original.get(str(review["id"]))
            if state not in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED"):
                raise RuntimeError("Could not recover original state of a dismissed review.")
        states.append(state)
    changes = states.count("CHANGES_REQUESTED")
    return dict(review_count=len(submitted),
                reviewer_count=len({r["user"]["id"] for r in submitted.values() if r.get("user")}),
                approval_count=states.count("APPROVED"), change_request_count=changes,
                has_review=bool(submitted), has_change_request=changes > 0,
                dismissed_review_count=sum(r["state"] == "DISMISSED" for r in submitted.values()))


def collect(api, repo, number):
    pr = api.get(f"/repos/{repo}/pulls/{number}")
    if not pr.get("merged_at"):
        raise RuntimeError("Selected PR is not merged.")
    row = {key: pr.get(key) for key in (
        "title", "created_at", "merged_at", "closed_at", "updated_at", "author_association",
        "additions", "deletions", "changed_files", "commits")}
    author = pr.get("user") or {}
    row.update(repo=repo, pr_number=number, url=pr["html_url"],
               author_login=author.get("login"), author_type=author.get("type"))
    reviews = api.pages(f"/repos/{repo}/pulls/{number}/reviews")
    needs_events = any(r["state"] == "DISMISSED" and r.get("submitted_at") and
                       parse_time(r["submitted_at"]) <= parse_time(pr["merged_at"]) for r in reviews)
    events = api.pages(f"/repos/{repo}/issues/{number}/timeline") if needs_events else []
    row.update(review_metrics(reviews, pr["merged_at"], events))
    row.update(fetched_at=timestamp(), collection_status="ok", error="")
    return row


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="microsoft/vscode")
    parser.add_argument("--start", type=date.fromisoformat, default=date(2020, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2024, 12, 31))
    parser.add_argument("--every", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--limit", type=int, help="Collect first N systematic sample entries; still indexes full range")
    mode.add_argument("--pilot", type=int, help="Fetch up to N PRs (1–100) in the first 31 days; no full indexing")
    parser.add_argument("--output", type=Path, help="Default: data/prs.csv, or data/prs_pilot.csv for --pilot")
    args = parser.parse_args()
    if args.start > args.end or args.every < 1 or (args.limit is not None and args.limit < 1):
        parser.error("Dates must be ordered; --every and --limit must be positive.")
    if args.pilot is not None and not 1 <= args.pilot <= 100:
        parser.error("--pilot must be between 1 and 100.")
    if args.output is None:
        args.output = ROOT / "data" / ("prs_pilot.csv" if args.pilot else "prs.csv")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repo):
        parser.error("--repo must be owner/repository")
    config = dict(repo=args.repo, start=str(args.start), end=str(args.end),
                  every=args.every, seed=args.seed, schema_version=1)
    if args.pilot:
        config.update(mode="pilot", pilot_count=args.pilot)
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    cache = args.output.parent / ".pr_cache" / fingerprint
    manifest_path = args.output.with_suffix(".sample.json")
    api = GitHub(load_token(ROOT / ".env"))
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest["config"] != config:
            raise RuntimeError("Output belongs to different sampling settings; choose another --output.")
    else:
        if args.output.exists():
            raise RuntimeError("Existing CSV has no sample manifest; choose another --output.")
        if args.pilot:
            sample = pilot_sample(api, args.repo, args.start, args.end, args.pilot)
            manifest = dict(config=config, indexed_at=timestamp(), sample=sample)
        else:
            items = discover(api, args.repo, args.start, args.end, cache)
            sample, start_position = select_sample(items, args.every, args.seed)
            manifest = dict(config=config, indexed_at=timestamp(), eligible_count=len(items),
                            start_position=start_position, sample=sample)
        save_json(manifest_path, manifest)
    if args.pilot:
        print(f"Pilot: {len(manifest['sample'])} PRs", flush=True)
    else:
        print(f"Eligible: {manifest['eligible_count']}; sampled: {len(manifest['sample'])}; "
              f"starting position: {manifest['start_position']}", flush=True)
    rows = {}
    if args.output.exists():
        with args.output.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != FIELDS:
                raise RuntimeError("CSV schema differs from this collector.")
            rows = {int(row["pr_number"]): row for row in reader}
    selected = manifest["sample"][:args.limit]
    for index, item in enumerate(selected, 1):
        number = item["number"]
        if rows.get(number, {}).get("collection_status") == "ok":
            continue
        print(f"[{index}/{len(selected)}] Fetching PR #{number}", flush=True)
        try:
            rows[number] = collect(api, args.repo, number)
        except RuntimeError as exc:
            rows[number] = dict(repo=args.repo, pr_number=number,
                                url=f"https://github.com/{args.repo}/pull/{number}",
                                merged_at=item["merged_at"], fetched_at=timestamp(),
                                collection_status="error", error=str(exc))
            print(f"PR #{number}: {exc}", file=sys.stderr)
        write_csv(args.output, [rows[p["number"]] for p in manifest["sample"] if p["number"] in rows])
    if not selected:
        write_csv(args.output, [])
    failures = sum(row.get("collection_status") != "ok" for row in rows.values())
    print(f"Saved {len(rows)} rows to {args.output}; {failures} failed (rerun to retry).")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted. Rerun the same command to resume.", file=sys.stderr)
        sys.exit(130)
