# Descriptive PR analysis

microsoft/vscode: 2,000 successful sampled PRs.

| Merge year | n | Reviewed (%) | Change request (%) | Change request among reviewed (%) | Median merge hours | Median changed lines |
|---|---:|---:|---:|---:|---:|---:|
| 2017 | 200 | 32.5 | 12.5 | 38.5 | 18.67 | 24 |
| 2018 | 200 | 48.5 | 11.5 | 23.7 | 28.75 | 20 |
| 2019 | 200 | 57.5 | 14.0 | 24.3 | 20.76 | 22.5 |
| 2020 | 200 | 62.5 | 11.5 | 18.4 | 24.32 | 29.5 |
| 2021 | 200 | 62.0 | 13.0 | 21.0 | 13.65 | 28.5 |
| 2022 | 200 | 94.0 | 8.5 | 9.0 | 0.87 | 17.5 |
| 2023 | 200 | 100.0 | 6.5 | 6.5 | 1.07 | 14 |
| 2024 | 200 | 100.0 | 1.5 | 1.5 | 0.41 | 27.5 |
| 2025 | 200 | 100.0 | 2.0 | 2.0 | 0.60 | 19 |
| 2026* | 200 | 100.0 | 1.0 | 1.0 | 1.31 | 57 |

*Partial study year. Rates use all sampled PRs unless explicitly conditional on reviewed PRs.

Use yearly_subgroups.csv to compare size, account type, recorded association, review profile, reviewers, files, commits and merge-time categories within each year.

The user-account and matched-calendar-window cohorts are sensitivity checks. Every table includes denominators; groups below 30 PRs and change-request counts below 10 are flagged. These are reporting flags, not significance thresholds.

## Interpretation

- All summaries are unweighted descriptions of sampled merged PRs, not population totals or causal effects.
- Sampling manifest absent: selection/completeness and population weights cannot be verified.
- User accounts are not proof of human-only work; reviewer account types and AI use are unavailable.
- Review events are not revision rounds; profile labels do not establish the order of events.
- Associations and change-size fields are recorded at collection, not verified historical covariates.
- Repeated authors and a single repository limit generalization; no independence-based significance tests are reported.
