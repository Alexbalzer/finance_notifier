from __future__ import annotations

import datetime as dt
import logging
import re
from typing import List, Tuple, Dict, Iterable
from urllib.parse import (
    urlparse, parse_qs, unquote, urlunparse, quote_plus
)

import requests
import xml.etree.ElementTree as ET

logger = logging.getLogger("stock-alerts")

# Versuche feedparser; wenn nicht vorhanden, wird automatisch der Fallback genutzt
try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover
    feedparser = None  # type: ignore

_GOOGLE_NEWS_SEARCH = "https://news.google.com/rss/search"


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def _ensure_https(u: str) -> str:
    if not u:
        return ""
    if u.startswith(("http://", "https://")):
        return u
    return "https://" + u.lstrip("/")


def _clean_tracking_params(url: str) -> str:
    """Entfernt gängige Google/UTM-Tracking-Parameter (kosmetisch)."""
    try:
        p = urlparse(url)
        clean_q = re.sub(
            r"(?:^|&)(ved|usg|utm_[^=]+|si|sca_esv|gws_[^=]+|opi)=[^&]*",
            "",
            p.query or "",
        )
        if clean_q != (p.query or ""):
            p = p._replace(query=clean_q)
            return urlunparse(p)
        return url
    except Exception:
        return url

def _extract_original_url(url: str, *, resolve_redirects: bool = True, timeout: float = 5.0) -> str:
    """
    Liefert bestmöglich die Original-Artikel-URL.
    Behandelt:
      - news.google.* mit ?url=
      - consent.google.* mit ?continue=
      - /rss/articles -> /articles + HTML-Parsing
      - Redirect-Kette + canonical/meta/JS
      - Brute-Force: erste absolute Nicht-Google-URL im HTML
    """
    import re, requests
    from urllib.parse import urlparse, parse_qs, unquote, urlunparse

    def ensure_https(u: str) -> str:
        if not u:
            return ""
        if u.startswith(("http://", "https://")):
            return u
        return "https://" + u.lstrip("/")

    def consent_continue(u: str) -> str | None:
        p = urlparse(u)
        if "consent.google." not in (p.netloc or ""):
            return None
        qs = parse_qs(p.query or "")
        cont = qs.get("continue") or qs.get("continue_url")
        if cont and cont[0]:
            return ensure_https(unquote(cont[0]))
        return None

    url = ensure_https(url)

    # 1) Direkter Google-News-Redirect (?url=)
    try:
        p = urlparse(url)
        if "news.google." in (p.netloc or ""):
            qs = parse_qs(p.query or "")
            if "url" in qs and qs["url"]:
                return ensure_https(unquote(qs["url"][0]))
    except Exception:
        pass

    # 2) Direkter Consent-Link
    cc = consent_continue(url)
    if cc:
        return cc

    # 3) /rss/articles -> /articles (liefert oft Ziel-Links im HTML)
    try:
        p = urlparse(url)
        if "news.google." in (p.netloc or "") and "/rss/articles/" in p.path:
            p = p._replace(path=p.path.replace("/rss/articles/", "/articles/"))
            url = urlunparse(p)
    except Exception:
        pass

    if not resolve_redirects:
        return url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    try:
        r = requests.get(url, allow_redirects=True, timeout=timeout, headers=headers)

        # 3a) Consent in Redirect-Kette?
        for h in (r.history or []):
            u = getattr(h, "headers", {}).get("Location", "") or h.url
            cont = consent_continue(u)
            if cont:
                return cont

        # 3b) Finale URL != google.* -> fertig
        if r.url and "google.com" not in r.url and "google." not in r.url:
            return ensure_https(r.url)

        html = r.text or ""

        # 3c) canonical / meta refresh / JS location
        m = re.search(r'rel=["\']canonical["\'][^>]*href=["\']([^"\']+)', html, re.I)
        if m:
            return ensure_https(unquote(m.group(1)))
        m = re.search(r'http-equiv=["\']refresh["\'][^>]*url=([^"\';>]+)', html, re.I)
        if m:
            return ensure_https(unquote(m.group(1)))
        m = re.search(r'location\.(?:replace|href)\((["\'])(.+?)\1\)', html, re.I)
        if m:
            return ensure_https(unquote(m.group(2)))

        # 3d) Links mit /url?url=... im HTML
        m = re.search(r'href=["\'](?:https?://news\.google\.com)?/url\?[^"\']*?\burl=([^"&]+)', html, re.I)
        if m:
            return ensure_https(unquote(m.group(1)))

        # 3e) BRUTE-FORCE: erste absolute Nicht-Google-URL im HTML
        candidates = re.findall(r'https?://[^\s"\'<>]+', html, flags=re.I)
        for cand in candidates:
            if not re.search(r'(?:^|\.)google\.[^/]+|(?:^|\.)gstatic\.com', cand, re.I):
                return ensure_https(unquote(cand))

    except Exception:
        pass

    # 4) Kosmetische Tracking-Parameter entfernen
    try:
        p = urlparse(url)
        clean_q = re.sub(r'(?:^|&)(ved|usg|utm_[^=]+|si|sca_esv|gws_[^=]+|opi)=[^&]*', '', p.query or '')
        if clean_q != (p.query or ''):
            p = p._replace(query=clean_q)
            return urlunparse(p)
    except Exception:
        pass

    return url



def build_query(name: str, ticker: str) -> str:
    """
    Erzeugt eine sinnvolle Finanz-Query für Google News.
    """
    name = (name or "").strip()
    ticker = (ticker or "").strip()
    finance_terms = [
        "stock", "Aktie", "Börse",
        "earnings", "guidance", "outlook",
        "revenue", "profit", "dividend",
        "forecast", "rating", "upgrade", "downgrade",
        "merger", "acquisition", "M&A",
    ]
    kw = " OR ".join(finance_terms)
    parts = []
    if name:
        parts.append(f"\"{name}\"")
    if ticker:
        parts.append(ticker)
    base = " OR ".join(parts) if parts else ticker
    return f"{base} ({kw})"


def filter_titles(items: List[Dict[str, str]], required_keywords: Iterable[str] = ()) -> List[Dict[str, str]]:
    """
    Behält nur Headlines, deren Titel eines der Keywords enthält (case-insensitive).
    Leere Keywordliste -> unverändert zurückgeben.
    """
    req = [k.strip().lower() for k in (required_keywords or []) if k and k.strip()]
    if not req:
        return items
    out: List[Dict[str, str]] = []
    for it in items:
        title = (it.get("title") or "").lower()
        if any(k in title for k in req):
            out.append(it)
    return out


def _google_news_rss_url(query: str, lang: str = "de", country: str = "DE") -> str:
    """
    Baut die Google-News-RSS-URL.
    """
    q = quote_plus(query)
    return f"{_GOOGLE_NEWS_SEARCH}?q={q}&hl={lang}&gl={country}&ceid={country}:{lang}"


# ---------------------------------------------------------------------------
# Hauptfunktionen (DICT-Variante – kompatibel zu deiner core.py)
# ---------------------------------------------------------------------------
def fetch_headlines(
    query: str,
    limit: int = 2,
    lookback_hours: int = 12,
    lang: str = "de",
    country: str = "DE",
) -> List[Dict[str, str]]:
    """
    Holt aktuelle Headlines aus Google News RSS für die Query.
    Gibt Dicts mit 'title', 'source', 'url', 'published' zurück.
    Nutzt feedparser, fällt sonst auf requests+ET zurück.
    """
    # Zeitfenster in der Query ausdrücken
    q = f"{query} when:{int(lookback_hours)}h"
    url = _google_news_rss_url(q, lang=lang, country=country)

    out: List[Dict[str, str]] = []
    now_utc = dt.datetime.now(dt.timezone.utc)

    if feedparser is not None:
        # Weg A: feedparser
        feed = feedparser.parse(url)
        for e in feed.entries:
            title = getattr(e, "title", "").strip()
            link = getattr(e, "link", "").strip()
            source = ""
            try:
                source = getattr(getattr(e, "source", None), "title", "") or ""
            except Exception:
                source = ""
            pub_dt_utc = None
            if getattr(e, "published_parsed", None):
                pub_dt_utc = dt.datetime(*e.published_parsed[:6], tzinfo=dt.timezone.utc)

            if pub_dt_utc:
                age = now_utc - pub_dt_utc
                if age.total_seconds() > lookback_hours * 3600:
                    continue

            if title and link:
                out.append({
                    "title": title,
                    "source": source or "news.google.com",
                    "url": _extract_original_url(link),
                    "published": pub_dt_utc.isoformat().replace("+00:00", "Z") if pub_dt_utc else "",
                })
            if len(out) >= int(limit):
                break
        return out

    # Weg B: Fallback ohne feedparser
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        def _findtext(elem, *names):
            for n in names:
                x = elem.find(n)
                if x is not None and (x.text or "").strip():
                    return (x.text or "").strip()
            return ""

        # pubDate parsen (Fallback)
        from email.utils import parsedate_to_datetime

        for item in root.findall(".//item"):
            title = _findtext(item, "title")
            link = _findtext(item, "link")
            # Source steht je nach Feed als <source> oder namespaced
            source = _findtext(item, "source", "{http://news.google.com}source") or "news.google.com"
            pub_raw = _findtext(item, "pubDate")
            pub_iso = ""
            if pub_raw:
                try:
                    pub_dt = parsedate_to_datetime(pub_raw)
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=dt.timezone.utc)
                    pub_iso = pub_dt.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
                    if (now_utc - pub_dt.astimezone(dt.timezone.utc)).total_seconds() > lookback_hours * 3600:
                        continue
                except Exception:
                    pass

            if title and link:
                out.append({
                    "title": title,
                    "source": source,
                    "url": _extract_original_url(link),
                    "published": pub_iso,
                })
            if len(out) >= int(limit):
                break
        return out
    except Exception as e:  # pragma: no cover
        logger.warning("News abrufen fehlgeschlagen (%s): %s", query, e)
        return []


# ---------------------------------------------------------------------------
# Optionale Tuple-Variante (falls mal benötigt)
# ---------------------------------------------------------------------------
def fetch_news(query: str, *, max_items: int = 3, lang: str = "de") -> List[Tuple[str, str, str]]:
    """
    Einfache Variante, liefert Tuples (title, source, final_url).
    Wird von core.py nicht benötigt, kann aber nützlich sein.
    """
    params = {
        "q": query,
        "hl": lang,
        "gl": "DE" if lang == "de" else "US",
        "ceid": f"{'DE' if lang == 'de' else 'US'}:{lang}",
    }
    try:
        r = requests.get(_GOOGLE_NEWS_SEARCH, params=params, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items: List[Tuple[str, str, str]] = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            # Quelle kann im Google-Namespace liegen
            src = (item.findtext("{http://news.google.com}source") or
                   item.findtext("source") or "").strip()
            if title and link:
                items.append((title, src or "news.google.com", _extract_original_url(link)))
            if len(items) >= max_items:
                break
        return items
    except Exception as e:  # pragma: no cover
        logger.warning("News abrufen fehlgeschlagen (%s): %s", query, e)
        return []



# # from __future__ import annotations
# # import datetime as dt
# # from typing import List, Dict, Iterable
# # from urllib.parse import quote_plus
# # import feedparser


# # def build_query(name: str, ticker: str) -> str:
# #     """
# #     Build a Google News search query for a company.
# #     """
# #     # : Return a query combining company name, ticker, and finance keywords
# #     pass


# # def filter_titles(items: List[Dict[str, str]], required_keywords: Iterable[str] = ()) -> List[Dict[str, str]]:
# #     """
# #     Filter news items so that only those containing required keywords
# #     in their title are kept.
# #     """
# #     # : If no required keywords, return items unchanged
# #     # : Otherwise, keep only items whose title contains any keyword (case-insensitive)
# #     pass


# # def _google_news_rss_url(query: str, lang: str = "de", country: str = "DE") -> str:
# #     """
# #     Build a Google News RSS URL for a given query.
# #     """
# #     # : Encode the query with quote_plus, append "when:12h"
# #     # : Construct and return the final RSS URL
# #     pass


# # def fetch_headlines(
# #     query: str,
# #     limit: int = 2,
# #     lookback_hours: int = 12,
# #     lang: str = "de",
# #     country: str = "DE",
# # ) -> List[Dict[str, str]]:
# #     """
# #     Fetch latest headlines from Google News RSS for a given query.
# #     """
# #     # : Build the RSS URL via _google_news_rss_url and parse it with feedparser
# #     # : Filter entries by publication time (lookback_hours) and collect title/source/link
# #     # : Stop after collecting 'limit' items
# #     pass
