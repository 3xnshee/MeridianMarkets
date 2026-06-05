import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import server


class FakeHistoryFrame:
    def __init__(self, rows):
        self._rows = rows
        self.empty = not bool(rows)

    def iterrows(self):
        yield from self._rows


class FakeTicker:
    def __init__(self, rows, info=None, fast_info=None):
        self._rows = rows
        self.info = info or {}
        self.fast_info = fast_info or {}

    def history(self, *args, **kwargs):
        return FakeHistoryFrame(self._rows)


class FakeYFinance:
    def __init__(self, rows=None, info=None, fast_info=None, search_quotes=None):
        self._ticker = FakeTicker(rows or [], info=info, fast_info=fast_info)
        self._search_quotes = search_quotes or []

    def Ticker(self, symbol):
        return self._ticker

    def Search(self, query, max_results=10, news_count=0, lists_count=0):
        return type("SearchResult", (), {"quotes": self._search_quotes})()


class DashboardApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_port = server.PORT
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.DashboardHandler)
        server.PORT = cls.httpd.server_address[1]
        cls.base_url = f"http://127.0.0.1:{server.PORT}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    def setUp(self):
        server.cache["quotes"].clear()
        server.cache["search"].clear()
        server.cache["history"] = {server.DEFAULT_RANGE: {s: [] for s in server.DEFAULT_SYMBOLS}}
        server.cache_timestamps["quotes"].clear()
        server.cache_timestamps["search"].clear()
        server.cache_timestamps["history"].clear()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.PORT = cls._original_port

    def test_health_endpoint_reports_ok_and_metadata(self):
        with urlopen(f"{self.base_url}/api/health") as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["app"], "Meridian Markets")
        self.assertEqual(payload["port"], server.PORT)

    def test_meta_endpoint_lists_default_symbols(self):
        with urlopen(f"{self.base_url}/api/meta") as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["app"], "Meridian Markets")
        self.assertEqual(payload["default_range"], server.DEFAULT_RANGE)
        self.assertEqual(payload["default_symbols"], server.DEFAULT_SYMBOLS)
        self.assertIn("1d", payload["ranges"])
        self.assertIn("build_id", payload)
        self.assertIn("built_at", payload)
        self.assertEqual(payload["data_source"], "yahoo finance via yfinance")
        self.assertIn("yfinance_available", payload)
        self.assertIn("cache_ttl_seconds", payload)
        self.assertIn("search_cache_ttl_seconds", payload)

    def test_yfinance_quote_parses_series_and_uses_previous_close(self):
        rows = [
            (
                __import__("datetime").datetime(2024, 3, 9, 15, 57, tzinfo=ZoneInfo("America/New_York")),
                {"Open": 100.0, "High": 100.5, "Low": 99.8, "Close": 100.2, "Volume": 1000},
            ),
            (
                __import__("datetime").datetime(2024, 3, 9, 15, 58, tzinfo=ZoneInfo("America/New_York")),
                {"Open": 100.2, "High": 101.2, "Low": 100.0, "Close": 100.8, "Volume": 2000},
            ),
            (
                __import__("datetime").datetime(2024, 3, 9, 15, 59, tzinfo=ZoneInfo("America/New_York")),
                {"Open": 100.8, "High": 101.5, "Low": 100.6, "Close": 101.3, "Volume": 3000},
            ),
        ]
        fake_yf = FakeYFinance(
            rows=rows,
            info={"shortName": "Apple Inc."},
            fast_info={"previousClose": 100.8},
        )

        with patch.object(server, "yf", fake_yf):
            quote, series = server._yfinance_quote_for_symbol("AAPL", server.DEFAULT_RANGE)

        self.assertEqual(quote.symbol, "AAPL")
        self.assertEqual(quote.name, "Apple Inc.")
        self.assertEqual(quote.close, 101.3)
        self.assertEqual(quote.high, 101.5)
        self.assertEqual(quote.low, 100.6)
        self.assertEqual(quote.volume, 3000)
        self.assertEqual(quote.date, "2024-03-09")
        self.assertEqual(quote.time, "15:59:00")
        self.assertEqual(len(series), 3)
        self.assertGreater(quote.change, 0)
        self.assertEqual(quote.source, "yfinance")

    def test_search_endpoint_uses_yfinance_search_results(self):
        fake_yf = FakeYFinance(
            search_quotes=[
                {
                    "symbol": "AAPL",
                    "shortname": "Apple Inc.",
                    "exchange": "NMS",
                    "quoteType": "EQUITY",
                }
            ]
        )

        with patch.object(server, "yf", fake_yf):
            with urlopen(f"{self.base_url}/api/search?q=Apple") as response:
                data = json.loads(response.read().decode("utf-8"))
        self.assertEqual(data["query"], "Apple")
        self.assertEqual(data["source"], "yahoo finance via yfinance")
        self.assertEqual(data["results"][0]["symbol"], "AAPL")
        self.assertEqual(data["results"][0]["name"], "Apple Inc.")
        self.assertEqual(data["results"][0]["exchange"], "NMS")

    def test_state_endpoint_persists_dashboard_state(self):
        old_state_home = os.environ.get("XDG_STATE_HOME")
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["XDG_STATE_HOME"] = tmpdir
            payload = {
                "stockview": {
                    "symbols": ["SPGI", "AAPL"],
                    "names": {"SPGI": "S&P Global Inc.", "AAPL": "Apple Inc."},
                },
                "watchlist": {
                    "symbols": ["TSLA"],
                    "names": {"TSLA": "Tesla, Inc."},
                },
                "sidebarCollapsed": True,
            }
            request = Request(
                f"{self.base_url}/api/state",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request) as response:
                saved = json.loads(response.read().decode("utf-8"))
            self.assertEqual(saved["stockview"]["symbols"], ["SPGI", "AAPL"])
            self.assertEqual(saved["watchlist"]["symbols"], ["TSLA"])
            self.assertTrue(saved["sidebarCollapsed"])

            with urlopen(f"{self.base_url}/api/state") as response:
                loaded = json.loads(response.read().decode("utf-8"))
            self.assertEqual(loaded["stockview"]["symbols"], ["SPGI", "AAPL"])
            self.assertEqual(loaded["watchlist"]["symbols"], ["TSLA"])
            self.assertTrue(loaded["sidebarCollapsed"])

            state_file = Path(tmpdir) / "MeridianMarkets" / "state.json"
            self.assertTrue(state_file.exists())
        if old_state_home is None:
            os.environ.pop("XDG_STATE_HOME", None)
        else:
            os.environ["XDG_STATE_HOME"] = old_state_home


if __name__ == "__main__":
    unittest.main()
