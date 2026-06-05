#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse, urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

try:
    import yfinance as yf
except Exception:  # pragma: no cover - optional dependency for local dev/builds
    yf = None

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
HOST = "0.0.0.0"
PORT = 8787
YFINANCE_CACHE_TTL_SECONDS = int(os.environ.get("YFINANCE_CACHE_TTL_SECONDS", "21600"))
YFINANCE_SEARCH_CACHE_TTL_SECONDS = int(os.environ.get("YFINANCE_SEARCH_CACHE_TTL_SECONDS", "86400"))
USER_AGENT = "Mozilla/5.0 (Hermes Dashboard)"
DEFAULT_SYMBOLS = ["SPGI", "SPFF", "BCBC", "BTM"]
DEFAULT_RANGE = "1d"
RANGE_CONFIG = {
    "1d": {"range": "1d", "interval": "1m"},
    "5d": {"range": "5d", "interval": "15m"},
    "1m": {"range": "1mo", "interval": "1d"},
    "6m": {"range": "6mo", "interval": "1d"},
    "ytd": {"range": "ytd", "interval": "1d"},
    "1y": {"range": "1y", "interval": "1d"},
    "5y": {"range": "5y", "interval": "1wk"},
}


@dataclass
class Quote:
    symbol: str
    name: str
    date: str
    time: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    change: float | None
    change_pct: float | None
    source: str = "yfinance"


cache: dict[str, dict] = {"quotes": {}, "history": {DEFAULT_RANGE: {s: [] for s in DEFAULT_SYMBOLS}}, "search": {}}
cache_timestamps: dict[str, dict] = {"quotes": {}, "history": {}, "search": {}}
cache_lock = threading.Lock()
state_lock = threading.Lock()
APP_TITLE = "Meridian Markets"
APP_SLUG = "MeridianMarkets"
APP_VERSION = "1.0"
BUILD_INFO_FILENAME = "build-info.json"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900


def _launch_command(extra_args: list[str] | None = None) -> list[str]:
    extra_args = extra_args or []
    script_path = Path(sys.argv[0]).resolve()
    if getattr(sys, "frozen", False):
        base = [str(Path(sys.executable).resolve())]
    else:
        base = [sys.executable, str(script_path)]
    return base + extra_args


class DesktopBridge:
    def open_market_overview_popout(self) -> dict[str, str]:
        command = _launch_command([
            "--overview-popout",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ])
        try:
            subprocess.Popen(
                command,
                cwd=str(Path(sys.argv[0]).resolve().parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            return {"status": "started"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}


def _default_dashboard_state() -> dict:
    return {
        "version": 1,
        "stockview": {"symbols": list(DEFAULT_SYMBOLS), "names": {}},
        "watchlist": {"symbols": [], "names": {}},
        "sidebarCollapsed": False,
    }


def _state_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / APP_SLUG / "state.json"
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / APP_SLUG / "state.json"
    return Path.home() / ".local" / "state" / APP_SLUG / "state.json"


def _legacy_state_path() -> Path | None:
    if os.name == "nt":
        return None
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / "stock-dashboard" / "state.json"
    return Path.home() / ".local" / "state" / "stock-dashboard" / "state.json"


def _default_build_info() -> dict:
    return {
        "version": APP_VERSION,
        "build_id": "dev",
        "built_at": "",
    }


def _build_info_path() -> Path:
    return Path(ROOT) / BUILD_INFO_FILENAME


def _read_build_info() -> dict:
    info = _default_build_info()
    path = _build_info_path()
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return info
    except Exception:
        return info

    if isinstance(raw, dict):
        info["version"] = str(raw.get("version", APP_VERSION))
        info["build_id"] = str(raw.get("build_id", "dev")) or "dev"
        info["built_at"] = str(raw.get("built_at", ""))
    return info


BUILD_INFO = _read_build_info()


def _config_path() -> Path:
    return _state_path().with_name("config.json")


def _read_local_config() -> dict:
    path = _config_path()
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _require_yfinance():
    if yf is None:
        raise RuntimeError("yfinance is not installed. Install yfinance to fetch Yahoo Finance data.")
    return yf


def _is_cache_fresh(fetched_at: float | None, ttl_seconds: int) -> bool:
    return fetched_at is not None and (time.time() - fetched_at) < ttl_seconds


def _series_window_start(range_key: str, latest_dt: datetime) -> datetime:
    if range_key == "1d":
        return latest_dt - timedelta(days=1)
    if range_key == "5d":
        return latest_dt - timedelta(days=5)
    if range_key == "1m":
        return latest_dt - timedelta(days=31)
    if range_key == "6m":
        return latest_dt - timedelta(days=183)
    if range_key == "ytd":
        return latest_dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if range_key == "1y":
        return latest_dt - timedelta(days=365)
    if range_key == "5y":
        return latest_dt - timedelta(days=365 * 5 + 2)
    return latest_dt - timedelta(days=31)


def _parse_series_timestamp(label: str) -> datetime:
    tz = ZoneInfo("America/New_York")
    try:
        if " " in label:
            dt = datetime.strptime(label, "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.strptime(label, "%Y-%m-%d").replace(hour=16, minute=0, second=0, microsecond=0)
        return dt.replace(tzinfo=tz)
    except ValueError:
        return datetime.fromtimestamp(0, tz=tz)


def _is_intraday_interval(interval: str) -> bool:
    return interval in {"1m", "2m", "5m", "15m", "30m", "60m", "90m"}


def _yfinance_quote_for_symbol(symbol: str, range_key: str) -> tuple[Quote, list[list[float]]]:
    cfg = RANGE_CONFIG[_normalize_range(range_key)]
    ticker = _require_yfinance().Ticker(symbol.upper())
    history = ticker.history(
        period=cfg["range"],
        interval=cfg["interval"],
        auto_adjust=False,
        actions=False,
        prepost=False,
    )
    if history is None or getattr(history, "empty", True):
        raise ValueError(f"empty chart data for {symbol}")

    tz = ZoneInfo("America/New_York")
    series: list[list[float]] = []
    ordered: list[tuple[datetime, object]] = []

    for idx, row in history.iterrows():
        dt = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=tz)
        else:
            dt = dt.astimezone(tz)
        ordered.append((dt, row))
        close_f = _to_float(getattr(row, "get", lambda key, default=None: default)("Close"))
        if close_f is not None:
            series.append([float(dt.timestamp()), close_f])

    if not ordered:
        raise ValueError(f"empty chart data for {symbol}")

    latest_dt, latest_row = ordered[-1]
    current_price = _to_float(getattr(latest_row, "get", lambda key, default=None: default)("Close"))
    open_ = _to_float(getattr(latest_row, "get", lambda key, default=None: default)("Open"))
    high = _to_float(getattr(latest_row, "get", lambda key, default=None: default)("High"))
    low = _to_float(getattr(latest_row, "get", lambda key, default=None: default)("Low"))
    volume = _to_int(getattr(latest_row, "get", lambda key, default=None: default)("Volume"))

    previous_close = None
    if len(ordered) > 1:
        previous_close = _to_float(getattr(ordered[-2][1], "get", lambda key, default=None: default)("Close"))

    info = getattr(ticker, "info", {}) or {}
    fast_info = getattr(ticker, "fast_info", {}) or {}
    if previous_close is None and isinstance(fast_info, dict):
        previous_close = _to_float(fast_info.get("previousClose") or fast_info.get("regularMarketPreviousClose"))
    if previous_close is None and isinstance(info, dict):
        previous_close = _to_float(info.get("previousClose") or info.get("regularMarketPreviousClose"))

    if current_price is None and series:
        current_price = series[-1][1]

    change = None
    change_pct = None
    if current_price is not None and previous_close not in (None, 0):
        change = current_price - previous_close
        change_pct = (change / previous_close) * 100

    date = latest_dt.strftime("%Y-%m-%d")
    time_str = latest_dt.strftime("%H:%M:%S") if _is_intraday_interval(cfg["interval"]) else ""
    name = str((info or {}).get("shortName") or (info or {}).get("longName") or symbol.upper())

    return (
        Quote(
            symbol=symbol.upper(),
            name=name,
            date=date,
            time=time_str,
            open=open_,
            high=high,
            low=low,
            close=current_price,
            volume=volume,
            change=change,
            change_pct=change_pct,
        ),
        series,
    )


def _search_symbols(query: str, limit: int = 8) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    cache_key = f"{query.lower()}::{limit}"
    with cache_lock:
        cached = cache.get("search", {}).get(cache_key)
        cached_at = cache_timestamps.get("search", {}).get(cache_key)
        if cached is not None and _is_cache_fresh(cached_at, YFINANCE_SEARCH_CACHE_TTL_SECONDS):
            return copy.deepcopy(cached)
    search_cls = getattr(_require_yfinance(), "Search", None)
    if search_cls is None:
        raise RuntimeError("yfinance Search API is unavailable in this version of the library")
    payload = search_cls(query, max_results=limit, news_count=0, lists_count=0)
    raw_quotes = getattr(payload, "quotes", None)
    if raw_quotes is None and isinstance(payload, dict):
        raw_quotes = payload.get("quotes")
    results = []
    for item in list(raw_quotes or [])[:limit]:
        if not isinstance(item, dict):
            continue
        symbol = (item.get("symbol") or item.get("ticker") or "").strip().upper()
        name = item.get("shortname") or item.get("longname") or item.get("name") or symbol
        if not symbol:
            continue
        results.append({
            "symbol": symbol,
            "name": name,
            "exchange": item.get("exchange") or item.get("exchDisp") or "",
            "type": item.get("quoteType") or item.get("typeDisp") or "",
        })
    with cache_lock:
        cache.setdefault("search", {})[cache_key] = copy.deepcopy(results)
        cache_timestamps.setdefault("search", {})[cache_key] = time.time()
    return results


def _normalize_saved_symbols(symbols) -> list[str]:
    cleaned: list[str] = []
    if not isinstance(symbols, list):
        return cleaned
    for symbol in symbols:
        sym = (symbol or "").strip().upper()
        if sym and sym not in cleaned:
            cleaned.append(sym)
    return cleaned


def _normalize_saved_names(names) -> dict[str, str]:
    if not isinstance(names, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in names.items():
        sym = (key or "").strip().upper()
        if sym:
            result[sym] = str(value)
    return result


def _read_dashboard_state() -> dict:
    state = _default_dashboard_state()
    for path in (_state_path(), _legacy_state_path()):
        if path is None:
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except FileNotFoundError:
            continue
        except Exception:
            continue

        if isinstance(raw, dict):
            stockview = raw.get("stockview", {})
            watchlist = raw.get("watchlist", {})
            stockview_symbols = stockview.get("symbols", []) if isinstance(stockview, dict) else []
            stockview_names = stockview.get("names", {}) if isinstance(stockview, dict) else {}
            watchlist_symbols = watchlist.get("symbols", []) if isinstance(watchlist, dict) else []
            watchlist_names = watchlist.get("names", {}) if isinstance(watchlist, dict) else {}
            state["stockview"]["symbols"] = _normalize_saved_symbols(stockview_symbols) or list(DEFAULT_SYMBOLS)
            state["stockview"]["names"] = _normalize_saved_names(stockview_names)
            state["watchlist"]["symbols"] = _normalize_saved_symbols(watchlist_symbols)
            state["watchlist"]["names"] = _normalize_saved_names(watchlist_names)
            state["sidebarCollapsed"] = bool(raw.get("sidebarCollapsed", False))
            return state
    return state


def _write_dashboard_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _merge_dashboard_state(current: dict, payload: dict) -> dict:
    state = copy.deepcopy(current if isinstance(current, dict) else _default_dashboard_state())
    if not isinstance(payload, dict):
        return state
    if "stockview" in payload and isinstance(payload["stockview"], dict):
        stockview = payload["stockview"]
        state["stockview"]["symbols"] = _normalize_saved_symbols(stockview.get("symbols")) or list(DEFAULT_SYMBOLS)
        state["stockview"]["names"] = _normalize_saved_names(stockview.get("names"))
    if "watchlist" in payload and isinstance(payload["watchlist"], dict):
        watchlist = payload["watchlist"]
        state["watchlist"]["symbols"] = _normalize_saved_symbols(watchlist.get("symbols"))
        state["watchlist"]["names"] = _normalize_saved_names(watchlist.get("names"))
    if "sidebarCollapsed" in payload:
        state["sidebarCollapsed"] = bool(payload["sidebarCollapsed"])
    state["version"] = 1
    return state


def build_health_payload() -> dict:
    return {
        "status": "ok",
        "app": APP_TITLE,
        "version": BUILD_INFO.get("version", APP_VERSION),
        "build_id": BUILD_INFO.get("build_id", "dev"),
        "built_at": BUILD_INFO.get("built_at", ""),
        "host": HOST,
        "port": PORT,
    }


def build_meta_payload() -> dict:
    return {
        "app": APP_TITLE,
        "version": BUILD_INFO.get("version", APP_VERSION),
        "build_id": BUILD_INFO.get("build_id", "dev"),
        "built_at": BUILD_INFO.get("built_at", ""),
        "default_symbols": DEFAULT_SYMBOLS,
        "default_range": DEFAULT_RANGE,
        "ranges": list(RANGE_CONFIG.keys()),
        "data_source": "yahoo finance via yfinance",
        "refresh_interval_seconds": 30,
        "cache_ttl_seconds": YFINANCE_CACHE_TTL_SECONDS,
        "search_cache_ttl_seconds": YFINANCE_SEARCH_CACHE_TTL_SECONDS,
        "yfinance_available": yf is not None,
    }


def _to_float(value):
    if value in (None, "", "N/A"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    if value in (None, "", "N/A"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _normalize_range(range_key: str | None) -> str:
    key = (range_key or DEFAULT_RANGE).strip().lower()
    return key if key in RANGE_CONFIG else DEFAULT_RANGE


def get_quotes(symbols: List[str], range_key: str = DEFAULT_RANGE):
    results = []
    errors = {}
    series_map = {}
    range_key = _normalize_range(range_key)
    now = time.time()

    with cache_lock:
        range_cache = cache.setdefault("history", {}).setdefault(range_key, {})
        range_cache_timestamps = cache_timestamps.setdefault("history", {}).setdefault(range_key, {})

    for symbol in symbols:
        sym = symbol.upper()
        cached_quote = None
        cached_series = None
        with cache_lock:
            quote_data = cache.get("quotes", {}).get(sym)
            quote_at = cache_timestamps.get("quotes", {}).get(sym)
            cached_series = cache.get("history", {}).get(range_key, {}).get(sym)
            history_at = cache_timestamps.get("history", {}).get(range_key, {}).get(sym)
            if quote_data and cached_series is not None and _is_cache_fresh(quote_at, YFINANCE_CACHE_TTL_SECONDS) and _is_cache_fresh(history_at, YFINANCE_CACHE_TTL_SECONDS):
                cached_quote = Quote(**{k: v for k, v in quote_data.items() if k != "fetched_at"})
        if cached_quote is not None and cached_series is not None:
            results.append(cached_quote)
            series_map[sym] = cached_series
            continue
        try:
            quote, series = _yfinance_quote_for_symbol(sym, range_key)
            results.append(quote)
            series_map[quote.symbol] = series
            with cache_lock:
                cache.setdefault("quotes", {})[quote.symbol] = {**asdict(quote), "fetched_at": now}
                cache_timestamps.setdefault("quotes", {})[quote.symbol] = now
                range_cache[quote.symbol] = series[-2000:]
                range_cache_timestamps[quote.symbol] = now
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as exc:
            errors[sym] = str(exc)
    return {
        "quotes": [asdict(q) | {"fetched_at": now} for q in results],
        "errors": errors,
        "fetched_at": now,
        "range": range_key,
        "history": {sym: cache["history"].get(range_key, {}).get(sym, []) for sym in symbols},
        "source": "yahoo finance via yfinance",
        "cache_ttl_seconds": YFINANCE_CACHE_TTL_SECONDS,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        return

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            body = json.dumps(build_health_payload()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/meta":
            body = json.dumps(build_meta_payload()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/state":
            with state_lock:
                body = json.dumps(_read_dashboard_state()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/search":
            params = parse_qs(parsed.query)
            query = params.get("q", [""])[0]
            limit = params.get("limit", ["8"])[0]
            try:
                limit_n = max(1, min(int(limit), 20))
            except ValueError:
                limit_n = 8
            try:
                results = _search_symbols(query, limit_n)
                payload = {"query": query, "results": results, "source": "yahoo finance via yfinance"}
                status = 200
            except Exception as exc:
                payload = {"query": query, "results": [], "source": "yahoo finance via yfinance", "error": str(exc)}
                status = 200
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/quotes":
            params = parse_qs(parsed.query)
            symbols = params.get("symbols", [",".join(DEFAULT_SYMBOLS)])[0]
            range_key = _normalize_range(params.get("range", [DEFAULT_RANGE])[0])
            symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
            payload = get_quotes(symbol_list, range_key)
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/state":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception:
            payload = {}
        with state_lock:
            current = _read_dashboard_state()
            updated = _merge_dashboard_state(current, payload)
            _write_dashboard_state(updated)
        body = json.dumps(updated).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _open_desktop_window(url: str, width: int = WINDOW_WIDTH, height: int = WINDOW_HEIGHT, js_api: object | None = None) -> None:
    os.environ.setdefault("PYWEBVIEW_GUI", "qt")
    try:
        import webview  # type: ignore
    except Exception:
        import webbrowser

        webbrowser.open(url, new=1, autoraise=True)
        return

    try:
        webview.create_window(APP_TITLE, url, width=width, height=height, js_api=js_api or DesktopBridge())
        webview.start()
    except Exception:
        import webbrowser

        webbrowser.open(url, new=1, autoraise=True)

def main(argv: list[str] | None = None):
    global HOST, PORT
    parser = argparse.ArgumentParser(description="Meridian Markets backend and desktop launcher")
    parser.add_argument("--host", default=HOST, help="Host interface for the local API server")
    parser.add_argument("--port", type=int, default=PORT, help="Port for the local API server")
    parser.add_argument("--server-only", action="store_true", help="Run the backend API without opening a desktop window")
    parser.add_argument("--browser", action="store_true", help="Open the dashboard in the default browser instead of a native window")
    parser.add_argument("--overview-popout", action="store_true", help="Open the market overview in a separate native window")
    parser.add_argument("--window-width", type=int, default=WINDOW_WIDTH, help="Desktop window width")
    parser.add_argument("--window-height", type=int, default=WINDOW_HEIGHT, help="Desktop window height")
    args = parser.parse_args(argv)

    HOST = args.host
    PORT = args.port

    # Prime the cache on startup so the UI loads populated.
    if yf is not None:
        try:
            get_quotes(DEFAULT_SYMBOLS)
        except Exception:
            pass
    url = f"http://127.0.0.1:{PORT}"
    try:
        import urllib.request

        urllib.request.urlopen(f"{url}/api/health", timeout=1)
        server_ready = True
    except Exception:
        server_ready = False

    if server_ready:
        print(f"Dashboard already running on {url}")
        if args.server_only:
            return
    else:
        server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
        print(f"Serving on {url}")
        threading.Thread(target=server.serve_forever, daemon=True).start()
    if args.server_only:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    if args.browser:
        import webbrowser

        webbrowser.open(url, new=1, autoraise=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    if args.overview_popout:
        _open_desktop_window(f"{url}/?popout=overview", width=args.window_width, height=args.window_height)
        return
    _open_desktop_window(url, width=args.window_width, height=args.window_height)


if __name__ == "__main__":
    main()
