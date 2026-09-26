import csv
from datetime import date
from pathlib import Path
import tempfile
import unittest

from scripts.collect_prs import (discover, discover_with_previous, pilot_sample, review_metrics,
                                 select_sample, select_yearly_sample, write_csv, save_json)


class CollectorTests(unittest.TestCase):
    def test_yearly_sampling_is_balanced_unique_and_reproducible(self):
        items = [{"number": year * 1000 + n, "merged_at": f"{year}-06-01T00:00:00Z"}
                 for year in (2020, 2021) for n in range(300)]
        args = 200, 42, date(2020, 1, 1), date(2021, 12, 31)
        sample, strata = select_yearly_sample(items, *args)
        self.assertEqual(len(sample), 400)
        self.assertEqual(len({p["number"] for p in sample}), 400)
        self.assertEqual([s["sampled_count"] for s in strata], [200, 200])
        self.assertEqual([s["design_weight"] for s in strata], [1.5, 1.5])
        self.assertEqual(select_yearly_sample(list(reversed(items)) + items[:1], *args), (sample, strata))
        self.assertNotEqual(select_yearly_sample(items, 200, 43, args[2], args[3])[0], sample)
        only_2021, _ = select_yearly_sample(items[300:], 200, 42, date(2021, 1, 1), args[3])
        self.assertEqual(only_2021, sample[200:])

    def test_yearly_sampling_handles_small_empty_and_partial_years(self):
        items = [{"number": 1, "merged_at": "2015-12-31T23:59:59Z"},
                 {"number": 2, "merged_at": "2017-09-25T23:59:59Z"}]
        sample, strata = select_yearly_sample(items, 200, 42, date(2015, 1, 1), date(2017, 9, 25))
        self.assertEqual(sample, items)
        self.assertEqual([s["sampled_count"] for s in strata], [1, 0, 1])
        self.assertEqual(strata[0]["design_weight"], 1)
        self.assertIsNone(strata[1]["design_weight"])
        self.assertEqual(strata[2]["end"], "2017-09-25")
        with self.assertRaises(ValueError):
            select_yearly_sample(items, 200, 42, date(2015, 1, 1), date(2017, 9, 24))

    def test_reuses_full_population_not_old_sample(self):
        import hashlib
        import json
        from unittest.mock import Mock, patch
        config = dict(repo="owner/repo", start="2020-01-01", end="2020-12-31")
        fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
        population = [{"number": n, "merged_at": "2020-06-01T00:00:00Z"} for n in (1, 2)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "old.sample.json"
            save_json(source, dict(config=config, eligible_count=2, sample=population[:1]))
            save_json(root / ".pr_cache" / fingerprint / "search_2020-01-01_2020-12-31.json", population)
            api = Mock()
            with patch("scripts.collect_prs.discover", return_value=[]) as fetch:
                result = discover_with_previous(api, "owner/repo", date(2015, 1, 1),
                                                date(2020, 12, 31), root / "new", source)
                self.assertEqual(result, population)
                fetch.assert_called_once_with(api, "owner/repo", date(2015, 1, 1),
                                              date(2019, 12, 31), root / "new")
            with self.assertRaises(ValueError):
                discover_with_previous(api, "different/repo", date(2015, 1, 1),
                                       date(2020, 12, 31), root / "new", source)

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
