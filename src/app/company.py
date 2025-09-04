from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import json
import time
import logging
import yfinance as yf

logger = logging.getLogger("stock-alerts")

# Cache-Datei im selben Ordner wie diese Datei
CACHE_FILE: Path = Path(__file__).resolve().parent / "company_cache.json"

# Häufige Rechtsformen/Suffixe (dürfen gern noch erweitert werden)
LEGAL_SUFFIXES = {
    # EN
    "inc", "inc.", "corp", "corp.", "corporation", "co", "co.", "company",
    "ltd", "ltd.", "limited", "llc", "lp", "plc",
    # DE
    "ag", "se", "gmbh", "kgaa", "kg", "ohg", "ug",
    # CH/FR/ES/IT/NL/SE/FIN etc.
    "sa", "s.a.", "nv", "n.v.", "bv", "b.v.", "ab", "oy", "oyj", "oyj.",
    "spa", "s.p.a.", "sarl", "sas",
    # Häufiges Nachwort
    "holding", "holdings",
}

@dataclass
class CompanyMeta:
    """
    Metadaten zu einer Firma/einem Ticker.
    """
    ticker: str
    name: Optional[str]      # gesäuberter Name (ohne Rechtsform)
    raw_name: Optional[str]  # Originalname aus Yahoo (long/short/display)
    source: str              # Quelle: "info.longName" / "info.shortName" / "displayName" / "fallback"
    base_ticker: str         # Ticker ohne Suffixe (z. B. "SAP" aus "SAP.DE")


def _load_cache() -> Dict[str, Any]:
    """Cache aus JSON laden."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug("company cache defekt (%s) -> neu anlegen", e)
            return {}
    return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    """Cache speichern."""
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _strip_legal_suffixes(name: str) -> str:
    """
    Entfernt gängige Rechtsform-Zusätze am Ende des Namens.
    "Apple Inc." -> "Apple", "SAP SE" -> "SAP"
    """
    if not name:
        return ""
    parts: List[str] = [p.strip(",. ") for p in name.split()]
    while parts and parts[-1].lower().strip(",. ") in LEGAL_SUFFIXES:
        parts.pop()
    return " ".join(parts).strip() if parts else name.strip()


def _base_ticker(symbol: str) -> str:
    """
    Basis-Ticker extrahieren.
    "SAP.DE" -> "SAP", "BRK.B" -> "BRK", Indizes wie "^GDAXI" bleiben.
    """
    if symbol.startswith("^"):
        return symbol
    if "." in symbol:
        return symbol.split(".", 1)[0]
    if "-" in symbol:  # ältere Klassenteiler (z. B. RDS-A)
        return symbol.split("-", 1)[0]
    return symbol


def _fetch_yf_info(symbol: str, retries: int = 2, delay: float = 0.4) -> Dict[str, Any]:
    """
    Firmendaten aus Yahoo Finance laden (robust mit Retries).
    """
    last_exc: Optional[Exception] = None
    for _ in range(retries + 1):
        try:
            t = yf.Ticker(symbol)
            # yfinance>=0.2: get_info() bevorzugen; fallback auf .info
            try:
                info = t.get_info()
            except Exception:
                info = getattr(t, "info", {}) or {}
            if isinstance(info, dict) and info:
                return info
        except Exception as e:
            last_exc = e
            time.sleep(delay)
    if last_exc:
        logger.debug("Yahoo info fehlgeschlagen für %s: %s", symbol, last_exc)
    return {}


def get_company_meta(symbol: str) -> CompanyMeta:
    """
    Ermittelt Metadaten (Name, Base-Ticker, Quelle) mit Cache und Fallbacks.
    """
    cache = _load_cache()
    if symbol in cache:
        try:
            data = cache[symbol]
            return CompanyMeta(**data)
        except Exception:
            # Falls Cache-Eintrag alt/inkompatibel ist -> neu aufbauen
            pass

    info = _fetch_yf_info(symbol)

    raw_name: Optional[str] = None
    source = "fallback"

    for k in ("longName", "shortName", "displayName", "name"):
        v = (info.get(k) or "").strip() if isinstance(info, dict) else ""
        if v:
            raw_name = v
            source = f"info.{k}"
            break

    clean = _strip_legal_suffixes(raw_name) if raw_name else ""
    base = _base_ticker(symbol)

    if not clean:
        clean = base
        source = "fallback"

    meta = CompanyMeta(
        ticker=symbol,
        name=clean,
        raw_name=raw_name,
        source=source,
        base_ticker=base,
    )

    cache[symbol] = asdict(meta)
    _save_cache(cache)
    return meta


def auto_keywords(symbol: str) -> Tuple[str, list[str]]:
    """
    Liefert (Anzeige-Name, Pflicht-Keywords) für News-Filter.
    Keywords z. B.: [Name, Base, Symbol] – du kannst hier später verfeinern.
    """
    meta = get_company_meta(symbol)
    name = (meta.name or meta.raw_name or meta.base_ticker or symbol).strip()
    base = meta.base_ticker or symbol

    # einfache, robuste Keyword-Liste (case-insensitive Filter nutzt lower)
    req = [name, base, symbol]
    # Duplikate/Leerstrings entfernen, Reihenfolge bewahren:
    seen = set()
    cleaned = []
    for k in req:
        kk = k.strip()
        if kk and kk.lower() not in seen:
            seen.add(kk.lower())
            cleaned.append(kk)

    return name, cleaned


# Optional: Query-Helfer für News (falls in core genutzt)
def news_query_for_ticker(ticker: str, override_name: Optional[str] = None) -> str:
    """
    Baut eine sinnvolle Google-News-Query auf Basis von Name+Ticker.
    """
    from src.app.news import build_query  # lazy import (damit keine Zyklen entstehen)
    meta = get_company_meta(ticker)
    name = override_name or meta.name or meta.raw_name or ""
    return build_query(name, ticker)

# from __future__ import annotations
# from dataclasses import dataclass
# from pathlib import Path
# from typing import Optional, Dict, Any, Tuple
# import json
# import time
# import yfinance as yf

# #  Create with 'Path' class the 'CACHE_FILE' object which stores location to 'company_cache.json'
# # CACHE_FILE =

# #  # Common legal suffixes often found in company names (ADD MORE),
# # which we remove to get a cleaner keyword (e.g., "Apple Inc." -> "Apple"). 
# LEGAL_SUFFIXES = {
#     "inc", "inc.",
# }

# #  Add class attributes like in the class description

# @dataclass
# class CompanyMeta:
#     """
#     Represents metadata about a company/ticker.
    
#     Attributes:
#         ticker (str): The full ticker symbol, e.g., "SAP.DE".
#         name (Optional[str]): Cleaned company name without legal suffixes, e.g., "Apple".
#         raw_name (Optional[str]): Original company name as returned by Yahoo Finance, e.g., "Apple Inc.".
#         source (str): Source of the name (e.g., "info.longName", "info.shortName", "fallback").
#         base_ticker (str): Simplified ticker without suffixes, e.g., "SAP" for "SAP.DE".
#     """
#     pass

# #  Finish this function:

# def _load_cache() -> Dict[str, Any]:
#     """Load cached company metadata from JSON file."""
#     if CACHE_FILE.exists():
#         try:
#             # Return content of file
#             pass
#         except Exception:
#             # Return empty dictionary
#             pass
#     else:
#         # Return empty dictionary
#         pass

# def _save_cache(cache: Dict[str, Any]) -> None:
#     """Save company metadata to local cache file."""
#     #  What parameters are missing?
#     # CACHE_FILE.write_text(json.dumps(), encoding="utf-8")


# #  Finish the function logic    
# def _strip_legal_suffixes(name: str) -> str:
#     """
#     Remove common legal suffixes from a company name.

#     Example:
#         "Apple Inc." -> "Apple"
#         "SAP SE" -> "SAP"
#     """
#     parts = [p.strip(",. ") for p in name.split()]
#     while parts and parts[-1].lower() in LEGAL_SUFFIXES:
#         # There is something missing
#         pass
#     return " ".join(parts) if parts else name.strip()

# #  Finish the function logic
# def _base_ticker(symbol: str) -> str:
#     """
#     Extract the base ticker symbol.

#     Examples:
#         "SAP.DE" -> "SAP"
#         "BRK.B"  -> "BRK"
#         "^GDAXI" -> "^GDAXI" (indices remain unchanged)
#     """
#     if symbol.startswith("^"):  # Index tickers like ^GDAXI
#         pass
#     if "." in symbol:
#         pass
#     return symbol

# #  Finish the try and except block
# def _fetch_yf_info(symbol: str, retries: int = 2, delay: float = 0.4) -> Dict[str, Any]:
#     """
#     Fetch company information from Yahoo Finance.

#     Args:
#         symbol (str): Ticker symbol.
#         retries (int): Number of retries if request fails.
#         delay (float): Delay between retries in seconds.

#     Returns:
#         dict: Yahoo Finance info dictionary (may be empty if lookup fails).
#     """
#     last_exc = None
#     for _ in range(retries + 1):
#         try:
#             # Missing code
#             if info:
#                 return info
#         except Exception as e:
#             # Missing code
#             time.sleep(delay)
#     return {}


# def get_company_meta(symbol: str) -> CompanyMeta:
#     """
#     Retrieve company metadata (name, base ticker, etc.) with caching and fallbacks.
#     """
#     # : Load the cache with _load_cache() and return early if the symbol exists
#     # cache = _load_cache()
#     # if symbol in cache:
#     #     ...

#     # : Fetch raw company information via _fetch_yf_info
#     # info = _fetch_yf_info(symbol)

#     # : Extract a potential company name from info ("longName", "shortName", "displayName")
#     # raw_name = ...
#     # source = ...

#     # : Clean the extracted name with _strip_legal_suffixes and handle fallback to _base_ticker
#     # clean = ...
#     # if not clean:
#     #     ...

#     # : Create a CompanyMeta instance and cache the result using _save_cache
#     # meta = CompanyMeta(...)

#     # : Save the constructed metadata back into the cache
#     # _save_cache(cache)

#     pass  # Remove this once the function is implemented


# def auto_keywords(symbol: str) -> Tuple[str, list[str]]:
#     """
#     Generate a company search keyword set based on symbol.
#     """
#     # : Fetch the CompanyMeta for the symbol
#     # meta = get_company_meta(symbol)

#     # : Determine the display name and construct the keyword list
#     # name = ...
#     # base = ...
#     # primary = ...
#     # req = ...

#     # : Return the cleaned name and the list of required keywords
#     # return name, req

#     pass  # Remove this once the function is implemented