# Datei: src/agent/stock_agent.py
# Zweck: "AI-Agent" Wrapper um deinen Notifier: nutzt deine Tools (market/news/ntfy/state)
#        und – falls verfügbar – ein LLM für Bewertung/Formatierung der Pushes.

from __future__ import annotations
import os, json, datetime as dt
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from zoneinfo import ZoneInfo

# --- deine bestehenden Module als "Tools" ---
from src.app.market import get_open_and_last
from src.app.news import build_query, fetch_headlines
from src.app.ntfy import notify_ntfy
from src.app.state import load_state, save_state

# Optional: Company-Meta/Keywords (falls vorhanden)
try:
    from src.app.company import auto_keywords
except Exception:
    auto_keywords = None  # optional

# Optionaler LLM-Client (Agent). Falls nicht vorhanden, nutzen wir Fallback.
# Du kannst hier jede Provider-Lib verwenden (OpenAI, Azure OpenAI, Groq, etc.)
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Secret setzen, wenn LLM aktiv sein soll
client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        client = None  # Fallback

# ----------------------------- Hilfsfunktionen -----------------------------
def now_tz(tz: str) -> dt.datetime:
    return dt.datetime.now(ZoneInfo(tz))

def pct_change(open_price: float, last_price: float) -> float:
    if not open_price:
        return 0.0
    return (last_price - open_price) / open_price * 100.0

def within_market_hours(cfg: Dict[str, Any]) -> bool:
    # Unterstützt dein Schema {"timezone","open","close","active_days","pause_on_closed"}
    tz = cfg.get("timezone", "America/New_York")
    pause = bool(cfg.get("pause_on_closed", True))
    if not pause:
        return True
    open_hh, open_mm = map(int, str(cfg.get("open", "09:30")).split(":"))
    close_hh, close_mm = map(int, str(cfg.get("close", "16:00")).split(":"))
    active_days = set(int(x) for x in cfg.get("active_days", (1,2,3,4,5)))
    now = now_tz(tz)
    wk = now.weekday() + 1  # 1..7
    if active_days and wk not in active_days:
        return False
    start = now.replace(hour=open_hh, minute=open_mm, second=0, microsecond=0)
    end = now.replace(hour=close_hh, minute=close_mm, second=0, microsecond=0)
    return start <= now <= end

def format_plain_push(ticker: str, open_px: float, last_px: float, delta_pct: float,
                      headlines: List[Dict[str, str]]) -> Tuple[str, str, Optional[str]]:
    """Solider Fallback ohne LLM: formatiert Nachricht + wählt Click-URL."""
    up = delta_pct >= 0
    arrow = "📈" if up else "📉"
    dirsym = "↑" if up else "↓"
    title = f"Stock Alert: {ticker}"  # ASCII im Header
    body = (
        f"{arrow} {ticker}: {dirsym} {abs(delta_pct):.2f}% vs. Open\n"
        f"Aktuell: {last_px:.2f} | Open: {open_px:.2f}"
    )
    click = None
    if headlines:
        lines = ["", "📰 News:"]
        for it in headlines:
            title_h = (it.get("title") or "").strip()
            url = (it.get("url") or it.get("link") or "").strip()
            src = (it.get("source") or "").strip()
            if not title_h or not url:
                continue
            lines.append(f"• {title_h} — {src}")
            lines.append(f"   🔗 {url}")
        body += "\n".join(lines)
        click = headlines[0].get("url") or headlines[0].get("link")
    return title, body, click

def agent_summarize_and_decide(ticker: str, open_px: float, last_px: float, delta_pct: float,
                               headlines: List[Dict[str, str]], threshold_pct: float) -> Tuple[bool, str, str, Optional[str]]:
    """
    Nutzt optional ein LLM, um Wichtigkeit zu bewerten und die Nachricht hübsch zu formatieren.
    Fällt bei fehlendem LLM automatisiert auf die Plain-Variante zurück.
    Rückgabe: (send_alert, title, body, click_url)
    """
    # 1) harter Gate: ohne LLM nur deterministisch
    if client is None:
        title, body, click = format_plain_push(ticker, open_px, last_px, delta_pct, headlines)
        # deterministische Entscheidung: Δ außerhalb ±threshold -> senden
        return (abs(delta_pct) >= threshold_pct), title, body, click

    # 2) Mit LLM: Headlines komponieren + Wichtigkeit
    #    (Wir geben strukturierte JSON-Antwort vor; robust gegen leere News.)
    sys = (
        "Du bist ein Stock-Alerts-Agent. Entscheide, ob ein Push geschickt werden soll.\n"
        "Gib eine JSON-Antwort mit den Feldern: send_alert (bool), title (string, ASCII), "
        "body (string, Markdown erlaubt), click_url (string|null).\n"
        "Regeln:\n"
        f"- Schwellwert: {threshold_pct:.3f}% absolut vs. Open.\n"
        "- Schicke immer, wenn |delta_pct| >= Schwelle.\n"
        "- Kürze Headlines prägnant; nutze max. 2–3 relevante. Verwende echte Ziel-Links.\n"
        "- Title muss ASCII bleiben (z. B. 'Stock Alert: TICKER'). Emoji nur im Body.\n"
    )
    user = {
        "ticker": ticker,
        "open": open_px,
        "last": last_px,
        "delta_pct": delta_pct,
        "threshold_pct": threshold_pct,
        "headlines": headlines[:5],
    }
    try:
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ]
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        send_alert = bool(data.get("send_alert", abs(delta_pct) >= threshold_pct))
        title = str(data.get("title") or f"Stock Alert: {ticker}")
        body = str(data.get("body") or "")
        click_url = data.get("click_url") or None
        if not body:
            # Fallback, falls LLM keine Body liefert
            title, body, click_url = format_plain_push(ticker, open_px, last_px, delta_pct, headlines)
        return send_alert, title, body, click_url
    except Exception:
        # robuster Fallback
        title, body, click = format_plain_push(ticker, open_px, last_px, delta_pct, headlines)
        return (abs(delta_pct) >= threshold_pct), title, body, click

# ----------------------------- Agent-Workflow -----------------------------
def run_agent_once(
    *,
    tickers: List[str],
    threshold_pct: float,
    ntfy_server: str,
    ntfy_topic: str,
    state_file: Path,
    market_hours_cfg: Dict[str, Any],
    news_cfg: Dict[str, Any] | None = None,
    test_cfg: Dict[str, Any] | None = None,
) -> None:
    """
    Agent-basierter Einzeldurchlauf:
      - Market hours (optional) beachten
      - Für jeden Ticker Open/Last, Δ%
      - Headlines holen
      - LLM (falls aktiv) entscheidet/komponiert Nachricht
      - Korridor/State anwenden (up/down/none), dann ntfy
    """
    test_cfg = test_cfg or {}
    if market_hours_cfg.get("pause_on_closed", True) and not test_cfg.get("bypass_market_hours", False):
        if not within_market_hours(market_hours_cfg):
            print("Außerhalb der Handelszeiten – Agent-Durchlauf übersprungen.")
            return

    st = load_state(state_file)  # speichert pro Ticker Richtung: up/down/none
    tz = market_hours_cfg.get("timezone", "America/New_York")
    print(f"Agent run @ {now_tz(tz):%Y-%m-%d %H:%M:%S} | tickers={','.join(tickers)}")

    for t in tickers:
        try:
            open_px, last_px = get_open_and_last(t)
            d_pct = pct_change(open_px, last_px)

            # Richtung für Korridor
            direction = "up" if d_pct >= threshold_pct else ("down" if d_pct <= -threshold_pct else "none")
            prev = st.get(t, "none")

            # Headlines (optional)
            headlines: List[Dict[str, str]] = []
            if news_cfg and news_cfg.get("enabled", True):
                # Query bauen
                name = ""
                if auto_keywords:
                    try:
                        name, _req = auto_keywords(t)
                    except Exception:
                        name = ""
                q = build_query(name, t)
                headlines = fetch_headlines(
                    q,
                    limit=int(news_cfg.get("max_items", 3)),
                    lookback_hours=int(news_cfg.get("lookback_hours", 12)),
                    lang=news_cfg.get("lang", "de"),
                    country=news_cfg.get("country", "DE"),
                )
                if not headlines:
                    # Fallback EN/US
                    headlines = fetch_headlines(
                        q,
                        limit=int(news_cfg.get("max_items", 3)),
                        lookback_hours=int(news_cfg.get("lookback_hours", 12)),
                        lang=news_cfg.get("fallback_lang", "en"),
                        country=news_cfg.get("fallback_country", "US"),
                    )

            # Agent-Entscheidung (oder Fallback)
            send, title, body, click = agent_summarize_and_decide(
                ticker=t,
                open_px=open_px,
                last_px=last_px,
                delta_pct=d_pct,
                headlines=headlines,
                threshold_pct=float(threshold_pct),
            )

            # Korridor anwenden: nur senden, wenn neu aus Korridor ausbricht
            if direction != "none" and direction != prev and send:
                notify_ntfy(
                    server=ntfy_server,
                    topic=ntfy_topic,
                    title=title,          # ASCII-Header
                    message=body,         # Markdown/Unicode ok
                    markdown=True,
                    click_url=click,
                    dry_run=bool(test_cfg.get("dry_run", False)),
                )
                st[t] = direction
                save_state(state_file, st)
            elif direction == "none" and prev != "none":
                # Reset: zurück im Korridor
                st[t] = "none"
                save_state(state_file, st)
            else:
                # nichts zu tun
                pass

        except Exception as e:
            print(f"Fehler bei {t}: {e}")

# ----------------------------- CLI-Einstieg -----------------------------
if __name__ == "__main__":
    # Minimaler Loader deiner config.json
    from src.app.config import load_config
    cfg = load_config("config.json")

    # cfg_path = Path("config.json")
    # cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    run_agent_once(
    tickers=cfg["tickers"],
    threshold_pct=float(cfg["threshold_pct"]),
    ntfy_server=cfg["ntfy"]["ntfy_server"] if "ntfy_server" in cfg.get("ntfy", {}) else cfg["ntfy"]["server"],
    ntfy_topic=cfg["ntfy"]["topic"],  # bereits aufgelöst!
    state_file=Path(cfg.get("state_file", "alert_state.json")),
    market_hours_cfg=cfg.get("market_hours", {}),
    news_cfg=cfg.get("news", {"enabled": False}),
    test_cfg=cfg.get("test", {}),
)

