import csv
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_prs import analyze, derive, load_rows, quantile, size_band, summarize


def example(**updates):
    row = dict(repo="test/repo", pr_number="1", created_at="2025-01-01T00:00:00Z",
               merged_at="2025-01-02T00:00:00Z", author_login="person", author_type="User",
               author_association="CONTRIBUTOR", additions="10", deletions="0", changed_files="1",
               commits="1", review_count="0", reviewer_count="0", approval_count="0",
               change_request_count="0", dismissed_review_count="0", has_review="False",
               has_change_request="False", collection_status="ok")
    row.update(updates)
    return row


def write(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


class AnalysisTests(unittest.TestCase):
    def test_size_and_duration_boundaries(self):
        self.assertEqual([size_band(n) for n in [0, 1, 10, 11, 50, 51, 200, 201, 1000, 1001]],
                         ["zero", "xs", "xs", "small", "small", "medium", "medium", "large", "large", "xl"])
        self.assertEqual(derive(example())["merge_time_band"], "day_to_week")
        self.assertEqual(derive(example(merged_at="2025-01-01T01:00:00Z"))["merge_time_band"], "hour_to_day")

    def test_profiles_do_not_infer_review_order(self):
        for reviews, approvals, changes, label in [
            (0, 0, 0, "no_submitted_review"), (1, 0, 0, "review_without_decision"),
            (2, 2, 0, "approval_without_change_request"), (2, 0, 2, "change_request_without_approval"),
            (3, 1, 2, "approval_and_change_request")]:
            row = derive(example(review_count=str(reviews), approval_count=str(approvals),
                                 change_request_count=str(changes), has_review=str(bool(reviews)),
                                 has_change_request=str(bool(changes))))
            self.assertEqual(row["review_profile"], label)

    def test_invalid_successful_rows_fail(self):
        for updates in [dict(review_count=""), dict(additions="-1"), dict(has_review="True"),
                        dict(approval_count="1"), dict(merged_at="2024-01-01T00:00:00Z"),
                        dict(created_at="2025-01-01T00:00:00")]:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                derive(example(**updates))

    def test_conditional_denominators_and_quantiles(self):
        rows = [derive(example()), derive(example(pr_number="2", review_count="2", change_request_count="2",
                                                 has_review="True", has_change_request="True"))]
        stats = summarize(rows)
        self.assertEqual(stats["change_requested_pct"], 50)
        self.assertEqual(stats["change_requested_among_reviewed_pct"], 100)
        self.assertEqual(stats["mean_change_events"], 1)
        self.assertEqual(stats["mean_change_events_when_present"], 2)
        self.assertIsNone(summarize(rows[:1])["change_requested_among_reviewed_pct"])
        self.assertIsNone(summarize([])["median_merge_days"])
        self.assertEqual(quantile([0, 10, 20, 30], .25), 7.5)

    def test_failed_rows_are_not_zero_reviews_and_duplicates_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.csv"
            write(path, [example(), example(pr_number="2", collection_status="error", review_count="")])
            rows, excluded, _ = load_rows(path)
            self.assertEqual((len(rows), len(excluded)), (1, 1))
            write(path, [example(), example()])
            with self.assertRaises(ValueError):
                load_rows(path)

    def test_missing_manifest_and_calendar_sensitivity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path, output = root / "input.csv", root / "output"
            write(path, [example(), example(pr_number="2", merged_at="2025-12-01T00:00:00Z"),
                         example(pr_number="3", merged_at="2026-09-25T00:00:00Z")])
            metadata = analyze(path, output, date(2025, 1, 1), date(2026, 9, 25))
            self.assertFalse(metadata["manifest_verified"])
            self.assertEqual(metadata["partial_years"], [2026])
            with (output / "cohort_summary.csv").open() as handle:
                counts = {r["cohort"]: int(r["n"]) for r in csv.DictReader(handle)}
            self.assertEqual(counts["matched_calendar_window"], 2)
            self.assertEqual(counts["complete_years_only"], 2)
            manifest = dict(config=dict(repo="test/repo", start="2025-01-01", end="2026-09-25"),
                            sample=[dict(number=n) for n in [1, 2]])
            path.with_suffix(".sample.json").write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                analyze(path, output, date(2025, 1, 1), date(2026, 9, 25))
            manifest["sample"].append(dict(number=3))
            path.with_suffix(".sample.json").write_text(json.dumps(manifest))
            self.assertTrue(analyze(path, output, date(2025, 1, 1), date(2026, 9, 25))["manifest_verified"])


if __name__ == "__main__":
    unittest.main()
