# cs5306_proj1

Collect a reproducible sample of merged GitHub pull requests into one pandas-friendly CSV.
Python 3.9+ is required; the collector uses only the standard library.

## Current study design

**2017–2026, 200 random PRs per merge year**, seed 42, from `microsoft/vscode`.
The cutoff is September 25, 2026, so 2026 is a partial year. Target: 2,000 PRs.
If a year contains fewer than 200 eligible PRs, all are selected.

We exclude 2015–2016 because GitHub introduced formal PR Reviews in September
2016; 2017 is the first full calendar year after that introduction.
See [STUDY_DESIGN.md](STUDY_DESIGN.md) for the rationale, sources, sampling weights,
and interpretation limits. The earlier 2020–2026 systematic dataset is preserved.

## Run

Store `GITHUB_TOKEN=your_token` in the project's `.env` (already ignored by Git),
or set the environment variable. The token needs read access to the public repository.

```bash
# Collect or resume the current stratified random sample.
python3 scripts/collect_prs.py --start 2017-01-01 --end 2026-09-25 \
  --per-year 200 --seed 42 \
  --population-from data/prs_2020_2026.sample.json \
  --output data/prs_2017_2026_yearly_200.csv

# Same default dates and sample size; discover afresh if no manifest exists.
python3 scripts/collect_prs.py

# Quick pipeline pilot (first 31 days only).
python3 scripts/collect_prs.py --pilot 10
```

`--population-from` reuses the previous complete population cache for its date
range, then discovers the missing earlier/later dates. It never uses the previous
selected sample as the population. Omit it if the previous manifest/cache is absent.

Search windows split recursively to respect GitHub's 1,000-result search limit.
Incomplete searches fail rather than silently producing a biased sample.
Within each merge year, PRs are selected uniformly at random without replacement.
The fixed seed gives reproducible selections; each year uses its own generator.
Both human and bot authors/reviewers are included. The sample manifest stores
per-year population counts, sample sizes, inclusion probabilities, and design weights.

Legacy systematic sampling is available explicitly:

```bash
python3 scripts/collect_prs.py --start 2020-01-01 --end 2026-09-25 \
  --every 50 --seed 42 --output data/prs_2020_2026.csv
```

`--pilot N` makes one search in the first 31 days beginning at `--start` (bounded
by `--end`). It takes up to N results, ordered by creation date, with N from 1–100.
It writes `data/prs_2017_2026_pilot.csv` and its own manifest, and skips population indexing.
This convenience sample tests the pipeline; it does not implement the research sampling design.
If fewer PRs match, the pilot returns fewer rows. Change `--start` to try another window.

`--limit` still limits detailed collection, not population discovery, and cannot be
combined with `--pilot`. Initial discovery
can take several minutes. The script prints progress and honors rate limits.

## Output and resuming

`data/prs_2017_2026_yearly_200.csv` contains one row per attempted sampled PR, including:

- Repository, PR number, URL, title and author information.
- Creation, merge, close, update and collection timestamps in ISO 8601 UTC.
- Additions, deletions, changed files and commits (as returned at collection time).
- Review event count, unique identifiable reviewer count, approval event count,
  change-request event count, review/change-request flags, and dismissed review count.
- `collection_status` (`ok` or `error`) and a sanitized error message.

Review metrics include only submitted reviews at or before merge. Repeated reviews
by the same person count separately; these are **events, not revision rounds**.
Dismissed reviews are matched to timeline dismissal events to recover their original
state. Failure to recover a state marks collection as failed. Approval count means
approval events ever submitted before merge, not effective approvals at merge.
Deleted/unavailable reviewer identities are excluded from unique-reviewer counts.

Errors leave metrics blank; a confirmed absence of reviews is zero. CSV is rewritten
atomically after each PR. Rerunning skips successful rows and retries failed rows.
Exit code 1 means collection failed or some rows have errors; code 130 means interruption.

Two supporting local files/directories preserve reproducibility and progress:
`data/prs_2017_2026_yearly_200.sample.json` stores settings and the frozen selected PR list;
`data/.pr_cache/` caches completed search windows. These are not additional analysis
CSVs. Keep the manifest with the CSV. Use a different output path when changing the
sample settings or starting a fresh collection; successful rows are not refreshed.
No full raw review dataset is stored.

## Pandas

Install pandas separately if you want to analyze the output:

```python
import pandas as pd

df = pd.read_csv("data/prs_2017_2026_yearly_200.csv")
df = df.loc[df["collection_status"].eq("ok")].copy()
for column in ["created_at", "merged_at", "closed_at", "updated_at", "fetched_at"]:
    df[column] = pd.to_datetime(df[column], utc=True)
df["merge_year"] = df["merged_at"].dt.year
```

## Graphs

Plotting defaults use the completed 2017–2026 stratified sample (200 PRs per year).
Earlier plots in the root `graphs/` directory describe the old systematic sample.

Generate four yearly charts and a combined overview, each in PNG and SVG format:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install matplotlib
.venv/bin/python scripts/plot_prs.py
```

Figures are saved in `graphs/prs_2017_2026_yearly_200/`. They show sample counts, review and change-request
shares, mean change-request events per PR (including zeros), and median time to
merge. Only successful rows are included. The charts label 2026 as a partial year;
they describe trends and do not establish an effect of AI use. Change-request
events are not distinct revision rounds.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

API references: [search](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests),
[PR details](https://docs.github.com/en/rest/pulls/pulls#get-a-pull-request),
[reviews](https://docs.github.com/en/rest/pulls/reviews#list-reviews-for-a-pull-request),
[timeline](https://docs.github.com/en/rest/issues/timeline#list-timeline-events-for-an-issue).
