# Analysis dimensions and labels

Use **merge year as the primary comparison dimension**, with review coverage,
change-request frequency, review participation and elapsed merge time as outcomes.
Then check whether the patterns persist within PR-size and author groups.
The unit of analysis is one sampled, merged PR in `microsoft/vscode`.

The current CSV contains 2,000 successful records, exactly 200 per merge year
from 2017 through 2026. The study cutoff recorded in the README is September 25,
2026. The older 992-row systematic sample is a separate sampling design; do not
append it to the current sample.

## Recommended dimensions

| Dimension | Field / labels | Purpose and interpretation |
|---|---|---|
| Calendar time | `merge_year`; retain `merge_month` for exploration | Primary yearly trend. Display `2026*` as partial. Do not label years as observed AI exposure. |
| Review coverage | `has_review`, `has_approval`, `has_change_request` | Three separate binary outcomes based on submitted events through merge. Approval means an approval event occurred, not effective approval at merge. |
| Review profile | `no_submitted_review`, `review_without_decision`, `approval_without_change_request`, `change_request_without_approval`, `approval_and_change_request` | Five mutually exclusive descriptive labels. Both types of event can occur on one PR; their order is unavailable. |
| Change-request intensity | `change_request_count`; any vs none | Report share with ≥1 event, mean events including zeros, and mean events among PRs with ≥1. These are events, not revision rounds. |
| Review participation | `review_count`, `reviewer_count`; `zero`, `one`, `two`, `three_plus` reviewers | Separate event volume from unique identifiable reviewer accounts. Zero identifiable reviewers can coexist with reviews if identities are unavailable. |
| Change size | `churn = additions + deletions`; `zero`, `xs` (1–10), `small` (11–50), `medium` (51–200), `large` (201–1,000), `xl` (1,001+) | Transparent, fixed reporting bands, not validated complexity categories. Retain continuous size and its quantiles. |
| Change breadth | `changed_files`, `commits`; `zero`, `one`, `two_to_five`, `six_plus` | Complement line counts. These are recorded change attributes, not direct measures of effort or quality. |
| Author account | `user`, `bot`, `other_unknown` | Preserve GitHub account type; `User` is not evidence of human-only authorship or absence of automation. |
| Recorded author association | Raw `author_association`; grouped `member_owner_collaborator`, `contributor_first_time`, `none`, `other_unknown` | Inspect sample composition. These fields are collected later and do not verify role at submission or employment status. |
| Merge time | Continuous `merge_days`; `under_hour`, `hour_to_day`, `day_to_week`, `week_to_month`, `month_plus` | Use median, interquartile range and 90th percentile. Bands are [0,1 hour), [1 hour,1 day), [1,7 days), [7,30 days), [30 days,∞). Elapsed time is not active labor time. |

If a downstream task requires a **target label**, the cleanest observed binary
target is `has_change_request`. A secondary target is continuous `merge_days`;
`review_profile` is suitable for descriptive multiclass comparisons. Do not feed
review counts, approval counts or the derived profile into a model predicting
change requests: they encode the outcome. Predicting at PR creation would require
new snapshots of size and author attributes as they existed at creation. This
pipeline is descriptive and does not train a predictive model.

## Questions and report labels

1. **How did review coverage change?** Plot “Share of sampled PRs with any submitted
   review (%)” and “Share with any approval event (%)” by merge year.
2. **How did requests for changes change?** Plot “PRs with ≥1 change-request event
   (%)” both among all sampled PRs and among reviewed PRs. Explicitly show the two
   denominators. Add event counts per PR as a table.
3. **How did review participation change?** Summarize event count and identifiable
   reviewer count separately, including the 0/1/2/3+ reviewer distribution.
4. **How did elapsed merge time change?** Plot median hours with 25th–75th percentile
   bands; report the 90th percentile in tables. The percentile band describes
   dispersion, **not a confidence interval**.
5. **Could sample composition explain part of the trend?** Compare within each
   size and recorded-association group by year; show group sample sizes and
   composition alongside outcomes. Do not interpret changes in raw averages as
   adjusted effects.

In the current sample, reviewed PRs rise from 65/200 (32.5%) in 2017 to 200/200
in every year from 2023 onward. PRs with change requests decline from 25/200
(12.5%) in 2017 to 2/200 (1.0%) in partial-year 2026. Median elapsed merge time
is about 18.67 hours in 2017 and 1.31 hours in partial-year 2026. These endpoints
motivate the analysis, but do not identify its cause. In particular, review
coverage alone has no variation within the sampled 2023–2026 years.

## Sensitivity checks and limits

- **Primary:** all sampled PRs, separately by merge year.
- **User accounts only:** exclude Bot and other account types. This checks author
  composition; reviewer bot status cannot be separated with the current CSV.
- **Complete years only:** exclude any partial boundary year.
- **Matched calendar window:** keep January 1–September 25 in each year for the
  default study window. This reduces the mismatch in calendar coverage and also
  reduces each earlier year's sample size; it does not eliminate all bias.
- **Within-year subgroups:** size, association, account type, review profile,
  reviewers, file count, commit count and merge-time band. Comparisons stratified
  on outcomes (review profile, reviewer count, merge-time band) are descriptive,
  not causal adjustment sets.

Always show denominators. The output flags groups with fewer than 30 PRs and
groups with fewer than 10 change-request-positive PRs. These are practical
reporting flags, not statistical cutoffs. Recent years have only 2–4 positive
PRs each in 2024–2026; detailed subgroup comparisons will be unstable. Repeated
authors also make an independence assumption questionable. No significance
tests or confidence intervals are produced by this pipeline.

Do not label the data `AI-generated`/`human-written`, `high-quality`/`low-quality`,
`productive`/`unproductive`, `accepted`/`rejected`, or revision-round counts.
The CSV has no observed AI-use field, defects, effort, rejected PRs or complete
revision histories. Formal review absence does not mean no discussion or review
outside submitted PR Review events. Faster merging and fewer change requests
do not establish improved quality. Restriction to merged PRs prevents estimating
acceptance probabilities, and long-running PRs merged after the cutoff are absent.

Calendar periods can be added for an explicitly defined exploratory comparison,
but choose boundaries before comparing results and call them calendar periods.
AI-effect claims require measured exposure and a design addressing other changes
in policy, automation, contributors and PR composition.

## Sampling and reproducibility

The collector implements seeded random sampling within merge years. Its manifest
normally records yearly eligible counts, sample counts and design weights
`N_year / n_year`. That manifest is absent from this checkout. Therefore the
pipeline verifies CSV quality but cannot independently verify the selected sample,
population completeness or inclusion weights. If a manifest is restored, it
checks the repository, date range and exact selected PR membership.

Yearly sample summaries are the primary outputs. Pooled summaries are explicitly
**unweighted sample descriptions**: with 200 observations in each year, the all-PR
summary gives equal representation to years, not representation proportional to
yearly repository activity. Subgroup and sensitivity filtering changes that mix.
No population weights are invented. Population-wide pooled estimates would
require the manifest and an explicit weighted analysis. Even with a manifest,
these scripts keep sample summaries unweighted.

Failed rows are excluded and listed separately; missing metrics never become
zero. Duplicate PR identifiers and malformed successful rows cause errors.
Inputs remain unchanged. `metadata.json` records the input SHA-256, study window,
counts, manifest status and interpretation notes. Quantiles use linear interpolation.

## Run and outputs

```bash
python3 scripts/analyze_prs.py
python3 scripts/plot_analysis.py
python3 -m unittest discover -s tests -v
```

The analysis script uses the Python standard library; plots require `matplotlib`
(the existing plotting dependency). There are no API calls or new data collection.
Use `--input`, `--output`, `--start` and `--end` to analyze a different CSV/window;
pass the generated analysis directory to `plot_analysis.py --input`.

Files in `analysis/prs_2017_2026_yearly_200/`:

- `labeled_prs.csv`: original successful rows with derived numeric fields and labels.
- `yearly_summary.csv`: yearly outcomes for each sensitivity cohort.
- `yearly_subgroups.csv`: yearly outcomes within each dimension and cohort.
- `cohort_summary.csv`: pooled sample descriptions, with explicit cohort labels.
- `excluded_rows.csv`: unsuccessful rows and exclusion reasons (header-only if none).
- `label_dictionary.json`: machine labels and reader-facing labels.
- `metadata.json`: input provenance, analysis settings and warnings.
- `report.md`: readable yearly results and interpretation notes.

Percent fields use 0–100; event means include zero-event PRs unless named
`when_present`. `change_requested_among_reviewed_pct` uses `reviewed_n` as its
denominator. An undefined statistic is blank, not zero. Quartile/median/p90 fields
include the source unit in their name; merge time is stored in days and plotted
in hours. `unique_identifiable_authors_n` excludes missing author logins.

Figures in `graphs/prs_2017_2026_yearly_200/analysis/` include a six-panel overview
and three-panel sensitivity comparison, each in PNG and SVG.
