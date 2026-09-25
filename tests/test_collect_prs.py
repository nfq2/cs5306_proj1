import csv
from datetime import date
from pathlib import Path
import tempfile
import unittest

from scripts.collect_prs import discover, pilot_sample, review_metrics, select_sample, write_csv


class CollectorTests(unittest.TestCase):
    def test_pilot_uses_one_small_search(self):
        from unittest.mock import Mock
        api = Mock()
        api.get.return_value = {"items": [
            {"number": n, "pull_request": {"merged_at": "2020-01-03T00:00:00Z"}}
            for n in (11, 60, 70)], "incomplete_results": False}
        result = pilot_sample(api, "microsoft/vscode", date(2020, 1, 1), date(2024, 12, 31), 10)
        self.assertEqual([item["number"] for item in result], [11, 60, 70])
        api.get.assert_called_once_with(
            "/search/issues", q="repo:microsoft/vscode is:pr is:merged merged:2020-01-01..2020-01-31",
            sort="created", order="asc", per_page=10, page=1)

    def test_sample_uses_positions_not_pr_numbers(self):
        items = [{"number": 11 + n * 73, "merged_at": "2021-01-01T00:00:00Z"}
                 for n in range(151)]
        sample, start = select_sample(list(reversed(items)), 50, 42)
        self.assertEqual(sample, items[start - 1::50])
        self.assertEqual(len(sample), 3)
        self.assertEqual(select_sample(items, 50, 42), (sample, start))

    def test_review_metrics_include_repeated_reviews_and_dismissals(self):
        def review(identifier, state, user, submitted="2021-02-01T00:00:00Z"):
            return dict(id=identifier, state=state, user={"id": user}, submitted_at=submitted)
        reviews = [review(1, "CHANGES_REQUESTED", 5), review(2, "DISMISSED", 5),
                   review(3, "APPROVED", 6), review(4, "PENDING", 6, None),
                   review(5, "CHANGES_REQUESTED", 7, "2021-04-01T00:00:00Z")]
        events = [{"event": "review_dismissed", "dismissed_review": {
            "review_id": "2", "state": "changes_requested"}}]
        metrics = review_metrics(reviews + [reviews[0]], "2021-03-01T00:00:00Z", events)
        self.assertEqual(metrics["review_count"], 3)
        self.assertEqual(metrics["reviewer_count"], 2)
        self.assertEqual(metrics["change_request_count"], 2)
        self.assertEqual(metrics["approval_count"], 1)
        with self.assertRaises(RuntimeError):
            review_metrics(reviews, "2021-03-01T00:00:00Z")
        self.assertEqual(review_metrics([], "2021-03-01T00:00:00Z")["review_count"], 0)

    def test_search_splits_dates_and_reuses_cache(self):
        class FakeAPI:
            def __init__(self):
                self.calls = 0

            def get(self, path, **params):
                self.calls += 1
                if "2021-01-01..2021-01-02" in params["q"]:
                    return {"total_count": 1001, "items": []}
                day = "2021-01-01" if "2021-01-01..2021-01-01" in params["q"] else "2021-01-02"
                return {"total_count": 1, "items": [{"number": int(day[-2:]),
                        "pull_request": {"merged_at": day + "T12:00:00Z"}}]}

        with tempfile.TemporaryDirectory() as directory:
            api = FakeAPI()
            args = api, "owner/repo", date(2021, 1, 1), date(2021, 1, 2), Path(directory)
            result = discover(*args)
            self.assertEqual(len(result), 2)
            self.assertEqual(api.calls, 3)
            self.assertEqual(discover(*args), result)
            self.assertEqual(api.calls, 3)

    def test_csv_preserves_missing_vs_zero_and_quotes_titles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prs.csv"
            write_csv(path, [{"pr_number": 1, "title": 'A, "title"\nwith newline',
                              "review_count": 0, "collection_status": "ok"},
                             {"pr_number": 2, "collection_status": "error"}])
            with path.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["review_count"], "0")
            self.assertEqual(rows[1]["review_count"], "")
            self.assertEqual(rows[0]["title"], 'A, "title"\nwith newline')


if __name__ == "__main__":
    unittest.main()
