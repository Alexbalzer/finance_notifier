from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Dict, List, Any

from zoneinfo import ZoneInfo

from src.app.market import get_open_and_last
from src.app.ntfy import notify_ntfy
from src.app.state import load_state, save_state
from src.app import news

# Optional (Fallbacks, falls nicht vorhanden)
try:
    from src.app.company import auto_keywords, news_query_for_ticker
except Exception:  # pragma: no cover
    auto_keywords = None
    news_query_for_ticker = None

logger = logging.getLogger("stock-alerts")


# ----------------------------- kleine Helfer -----------------------------
def _pct_change(open_price: float, last_price: float) -> float:
    if not open_price:
        return 0.0
    return (last_price - open_price) / open_price * 100.0


def _format_title(ticker: str) -> str:
    # ASCII-only -> Header sicher
    return f"Stock Alert: {ticker}"


def _format_body(ticker: str, open_price: float, last_price: float, pct: float) -> str:
    up = pct >= 0
    arrow = "📈" if up else "📉"
    dirsym = "↑" if up else "↓"
    return (
        f"{arrow} {ticker}: {pct:+.2f}% vs. Open\n"
        f"Aktuell: {last_price:.2f} | Open: {open_price:.2f}"
    )


def _ensure_https(u: str) -> str:
    if not u:
        return ""
    if u.startswith(("http://", "https://")):
        return u
    return "https://" + u.lstrip("/")


def _item_url(it: Dict[str, Any]) -> str:
    # akzeptiere sowohl 'url' (unsere news.py) als auch 'link' (Dozent)
    return _ensure_https((it.get("url") or it.get("link") or "").strip())


def _format_headlines(items: List[Dict[str, Any]]) -> str:
    """
    Kompakter Markdown-Block ohne Überschrift (die setzt run_once).
    Web rendert Markdown; Mobile bekommt darunter eine echte URL-Zeile.
    """
    if not items:
        return ""
    lines: List[str] = []
    seen = set()
    for it in items:
        title = (it.get("title") or "").strip()
        src = (it.get("source") or "").strip()
        url = _item_url(it)
        if not title or not url:
            continue

        # robuste Original-URL über news._extract_original_url
        try:
            from src.app.news import _extract_original_url as _news_extract
            orig = _news_extract(url, resolve_redirects=True)
        except Exception:
            orig = url

        # Duplikate vermeiden
        if orig in seen:
            continue
        seen.add(orig)

        # Domain (kurz) für die zweite Zeile
        try:
            from urllib.parse import urlparse
            dom = urlparse(orig).netloc
            dom = dom[4:] if dom.startswith("www.") else dom
        except Exception:
            dom = "link"

        src_part = f" — {src}" if src else ""
        lines.append(f"• [{title}]({orig}){src_part}")
        lines.append(f"   🔗 {orig}")  # immer volle, klickbare URL ausgeben

        #lines.append(f"   🔗 {orig if len(orig) <= 60 else 'https://' + dom}")
    return "\n".join(lines)


def now_tz(tz: str) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(tz))


def is_market_hours(cfg_mh: dict) -> bool:
    """
    Unterstützt zwei Schemas:
      A) {timezone, open, close, active_days, pause_on_closed}
      B) {enabled, tz, start_hour, end_hour, days_mon_to_fri_only}
    """
    # Schema A (deine ursprüngliche Struktur)
    if {"timezone", "open", "close"}.issubset(cfg_mh.keys()):
        tz = cfg_mh.get("timezone", "America/New_York")
        open_hh, open_mm = map(int, str(cfg_mh.get("open", "09:30")).split(":"))
        close_hh, close_mm = map(int, str(cfg_mh.get("close", "16:00")).split(":"))
        active_days = set(int(x) for x in cfg_mh.get("active_days", (1, 2, 3, 4, 5)))
        pause = bool(cfg_mh.get("pause_on_closed", True))
        if not pause:
            return True
        n = now_tz(tz)
        wk = n.weekday() + 1  # 1..7
        if active_days and wk not in active_days:
            return False
        start = n.replace(hour=open_hh, minute=open_mm, second=0, microsecond=0)
        end = n.replace(hour=close_hh, minute=close_mm, second=0, microsecond=0)
        return start <= n <= end

    # Schema B (Dozentenversion) :contentReference[oaicite:4]{index=4}
    if not cfg_mh.get("enabled", True):
        return True
    n = now_tz(cfg_mh.get("tz", "America/New_York"))
    if cfg_mh.get("days_mon_to_fri_only", True) and n.weekday() >= 5:
        return False
    return int(cfg_mh.get("start_hour", 9)) <= n.hour < int(cfg_mh.get("end_hour", 16))


# ------------------------------- Orchestrierung -------------------------------
def run_once(
    tickers: List[str],
    threshold_pct: float,
    ntfy_server: str,
    ntfy_topic: str,
    state_file: Path,
    market_hours_cfg: dict,
    test_cfg: dict,
    news_cfg: dict | None,
) -> None:
    """
    Ein Durchlauf:
      - Handelszeiten prüfen (mit Test-Bypass)
      - Je Ticker Δ% vs Open berechnen
      - Korridor-Logik (up/down/none) -> Push bei Richtungswechsel in/aus Korridor
      - Optional News anhängen (DE -> Fallback EN) und Click-URL setzen
    """
    tz = market_hours_cfg.get("timezone") or market_hours_cfg.get("tz") or "America/New_York"
    logger.info(
        "Run start (%s), Ticker=%s, Threshold=±%.2f%%",
        now_tz(tz).strftime("%Y-%m-%d %H:%M:%S"),
        ",".join(tickers),
        float(threshold_pct),
    )

    # Market-hours + Test-Bypass (Dozent) + Backwards-Compat (force_run_outside_hours)
    within = is_market_hours(market_hours_cfg)
    if test_cfg.get("enabled") and test_cfg.get("bypass_market_hours"):
        logger.info("Test: bypass_market_hours aktiv -> innerhalb.")
        within = True
    if test_cfg.get("force_run_outside_hours"):
        logger.info("Test: force_run_outside_hours aktiv -> innerhalb.")
        within = True

    if not within:
        logger.info("Außerhalb der Handelszeiten – nichts zu tun.")
        return

    state: Dict[str, str] = load_state(state_file)  # Korridor-State pro Ticker: up/down/none

    for tk in tickers:
        try:
            open_px, last_px = get_open_and_last(tk)
            if open_px == 0:
                raise RuntimeError(f"Open is 0 for {tk}")

            pct = _pct_change(open_px, last_px)

            # Test: erzwungene Delta (Dozent) :contentReference[oaicite:5]{index=5}
            if test_cfg.get("enabled") and test_cfg.get("force_delta_pct") is not None:
                forced = float(test_cfg["force_delta_pct"])
                logger.info("Test: force Δ%% = %.2f%% für %s (war %.2f%%).", forced, tk, pct)
                pct = forced
                last_px = open_px * (1.0 + pct / 100.0)

            logger.info("%s | Last=%.4f Open=%.4f Δ=%+.2f%%", tk, last_px, open_px, pct)

            prev = state.get(tk, "none")
            direction = "up" if pct >= threshold_pct else "down" if pct <= -threshold_pct else "none"

            if direction != "none" and direction != prev:
                # -> neuer Ausbruch: Push
                title = _format_title(tk)
                body = _format_body(tk, open_px, last_px, pct)

                headlines_block = ""
                click_url = None

                if news_cfg and news_cfg.get("enabled", False):
                    # Query bauen (Name + Ticker), Keywords für Filter
                    if news_query_for_ticker:
                        q = news_query_for_ticker(tk)  # nutzt CompanyMeta intern
                        # Keywords
                        try:
                            name, req_kw = auto_keywords(tk) if auto_keywords else ("", [])
                        except Exception:
                            req_kw = []
                    else:
                        # Build-Query direkt aus news-Modul
                        try:
                            name, req_kw = auto_keywords(tk) if auto_keywords else ("", [])
                            q = news.build_query(name, tk)
                        except Exception:
                            q = news.build_query("", tk)
                            req_kw = []

                    # DE zuerst …
                    items = news.fetch_headlines(
                        query=q,
                        limit=int(news_cfg.get("max_items", news_cfg.get("limit", 3))),
                        lookback_hours=int(news_cfg.get("lookback_hours", 12)),
                        lang=news_cfg.get("lang", "de"),
                        country=news_cfg.get("country", "DE"),
                    )
                    if req_kw:
                        items = news.filter_titles(items, required_keywords=req_kw)

                    # Click-URL vorbereiten
                    if items:
                        try:
                            from src.app.news import _extract_original_url as _news_extract
                            click_url = _news_extract(_item_url(items[0]), resolve_redirects=True)
                        except Exception:
                            click_url = _item_url(items[0])

                    text = _format_headlines(items)

                    # … Fallback EN/US, wenn leer oder schwach :contentReference[oaicite:6]{index=6}
                    if not text:
                        items = news.fetch_headlines(
                            query=q,
                            limit=int(news_cfg.get("max_items", news_cfg.get("limit", 3))),
                            lookback_hours=max(12, int(news_cfg.get("lookback_hours", 12))),
                            lang=news_cfg.get("fallback_lang", "en"),
                            country=news_cfg.get("fallback_country", "US"),
                        )
                        if req_kw:
                            items = news.filter_titles(items, required_keywords=req_kw)
                        if items and not click_url:
                            try:
                                from src.app.news import _extract_original_url as _news_extract
                                click_url = _news_extract(_item_url(items[0]), resolve_redirects=True)
                            except Exception:
                                click_url = _item_url(items[0])
                        text = _format_headlines(items)

                    if text:
                        headlines_block = "\n\n📰 News:\n" + text

                msg = body + headlines_block

                notify_ntfy(
                    ntfy_server,
                    ntfy_topic,
                    title,
                    msg,
                    dry_run=bool(test_cfg.get("dry_run", False)),
                    markdown=True,
                    click_url=click_url,
                )

                state[tk] = direction
                save_state(state_file, state)

            elif direction == "none":
                # zurück im Korridor -> Reset, damit der nächste Ausbruch wieder alertet :contentReference[oaicite:7]{index=7}
                if prev != "none":
                    logger.info("Back in corridor (%s): reset state %s → none", tk, prev)
                    state[tk] = "none"
                    save_state(state_file, state)
                else:
                    logger.info("%s | No alert (< ±%.2f%%).", tk, float(threshold_pct))

            else:
                logger.info("%s | Already alerted (%s). Waiting to re-enter corridor.", tk, prev)

        except Exception as e:
            logger.error("Error while processing %s: %s", tk, e)


# # import datetime as dt
# # from zoneinfo import ZoneInfo
# # import logging
# # from pathlib import Path
# # from typing import Dict, List, Any
# # from urllib.parse import urlparse, parse_qs
# # import requests

# # from .market import get_open_and_last
# # from .ntfy import notify_ntfy
# # from .state import load_state, save_state
# # from .company import auto_keywords
# # from .news import fetch_headlines, build_query, filter_titles

# # logger = logging.getLogger("stock-alerts")


# # def _ticker_to_query(ticker: str, override_name: str | None = None) -> str:
# #     """
# #     Return a human-friendly query term for a ticker.

# #     Args:
# #         ticker: Raw ticker symbol (e.g., "AAPL").
# #         override_name: Optional override (e.g., "Apple").

# #     Returns:
# #         A display/query string; override_name if provided, else the ticker.
# #     """
# #     # : Return override_name if provided; otherwise return ticker
# #     pass


# # def _ensure_https(u: str) -> str:
# #     """
# #     Ensure the given URL has a scheme. If missing, prefix with https://

# #     This helps when feeds provide bare domains or schemeless URLs.
# #     """
# #     # : Handle empty strings
# #     # : If u starts with http:// or https://, return u unchanged
# #     # : Otherwise, prefix u with "https://"
# #     pass


# # def _extract_original_url(link: str, *, resolve_redirects: bool = True, timeout: float = 3.0) -> str:
# #     """
# #     Try to extract the original article URL from Google News redirect links.

# #     Strategy:
# #         1) If it's a news.google.com link and contains ?url=..., use that.
# #         2) Optionally resolve redirects via HEAD (fallback GET) to obtain the final URL.
# #         3) If all fails, return the input link.

# #     Args:
# #         link: Possibly a Google News RSS link.
# #         resolve_redirects: Whether to follow redirects to the final URL.
# #         timeout: Per-request timeout in seconds.

# #     Returns:
# #         A best-effort "clean" URL pointing to the original source.
# #     """
# #     # : Normalize link via _ensure_https
# #     # : If link is a news.google.com URL, attempt to extract ?url= parameter
# #     # : Optionally resolve redirects via HEAD or GET
# #     # : Return cleaned URL or fallback to original link
# #     pass


# # def _domain(url: str) -> str:
# #     """
# #     Extract a pretty domain (strip leading 'www.') from a URL for compact display.
# #     """
# #     # : Parse the domain with urlparse
# #     # : Strip leading "www." if present
# #     # : Return cleaned domain or original url on error
# #     pass


# # def _format_headlines(items: List[Dict[str, Any]]) -> str:
# #     """
# #     Build a compact Markdown block for headlines.

# #     - Web (ntfy web app): Markdown will be rendered (nice links)
# #     - Mobile (ntfy apps): Markdown shows as plain text, so we also include
# #       a short, real URL line that remains clickable on phones.

# #     Returns:
# #         A multi-line string ready to embed into the notification body.
# #     """
# #     # : Handle empty list case
# #     # TDO: Build Markdown lines with titles, sources and cleaned links
# #     # : Join lines with newline characters and return the result
# #     pass


# # def now_tz(tz: str) -> dt.datetime:
# #     """
# #     Get current date/time in a specific timezone (e.g., 'Europe/Berlin').

# #     Using timezone-aware datetimes avoids DST pitfalls and makes logging consistent.
# #     """
# #     # : Use dt.datetime.now with ZoneInfo to return timezone-aware datetime
# #     pass


# # def is_market_hours(cfg_mh: dict) -> bool:
# #     """
# #     Heuristic market-hours check (simple window, no holidays).

# #     Args:
# #         cfg_mh: Market hours config with keys:
# #             - enabled (bool)
# #             - tz (str)
# #             - start_hour (int)
# #             - end_hour (int)
# #             - days_mon_to_fri_only (bool)

# #     Returns:
# #         True if within the configured hours, else False.
# #     """
# #     # : If checking is disabled, return True
# #     # : Obtain current time via now_tz(cfg_mh["tz"])
# #     # : Optionally limit to Monday–Friday
# #     # : Compare current hour with start_hour/end_hour
# #     pass


# # def run_once(
# #     tickers: List[str],
# #     threshold_pct: float,
# #     ntfy_server: str,
# #     ntfy_topic: str,
# #     state_file: Path,
# #     market_hours_cfg: dict,
# #     test_cfg: dict,
# #     news_cfg: dict,
# # ) -> None:
# #     """
# #     Execute one monitoring cycle:
# #       - Check market hours (with optional test bypass)
# #       - For each ticker:
# #           * Fetch open & last price (intraday preferred)
# #           * Compute Δ% vs. open
# #           * Trigger ntfy push if |Δ%| ≥ threshold (with de-bounce via state file)
# #           * Optionally attach compact news headlines (with cleaned source URLs)

# #     Side effects:
# #       - Sends an HTTP POST to ntfy (unless dry_run)
# #       - Reads/writes the alert state JSON (anti-spam)
# #       - Writes logs according to logging setup
# #     """
# #     # : Log job start and determine market-hours eligibility
# #     # : Load alert state from state_file
# #     # : Iterate over tickers and fetch open/last prices
# #     # : Compute Δ% and apply test overrides if needed
# #     # : Decide whether to send alerts and prepare notification body
# #     # : Optionally fetch and format news headlines
# #     # : Send notification via notify_ntfy and persist state via save_state
# #     pass

