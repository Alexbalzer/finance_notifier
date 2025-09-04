# streamlit_app.py
from __future__ import annotations
import json, os
from pathlib import Path
from datetime import time as dtime
import streamlit as st

CONFIG_PATH = Path("config.json")

DEFAULT_CFG = {
    "tickers": ["AAPL", "O", "WPY.F", "QDVX.DE"],
    "threshold_pct": 1.0,
    "ntfy": {"server": "https://ntfy.sh", "topic": "${NTFY_TOPIC}"},
    "log": {"level": "${LOG_LEVEL:INFO}", "file": "alerts.log"},
    "state_file": "alert_state.json",
    "market_hours": {
        "timezone": "America/New_York",
        "open": "09:30",
        "close": "16:00",
        "active_days": [1, 2, 3, 4, 5],  # 1..7 (Mo..So)
        "pause_on_closed": True,
    },
    "test": {
        "enabled": True,
        "dry_run": False,
        "bypass_market_hours": False,
        "force_delta_pct": None,
        "force_run_outside_hours": False
    },
    "news": {
        "enabled": True,
        "max_items": 3,
        "lookback_hours": 12,
        "lang": "de",
        "country": "DE",
        "fallback_lang": "en",
        "fallback_country": "US"
    }
}

def read_raw_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            st.warning("config.json war ungültig – es wird eine Standardvorlage geladen.")
    return DEFAULT_CFG.copy()

def write_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def hhmm_to_time(s: str) -> dtime:
    hh, mm = (s or "09:30").split(":")
    return dtime(int(hh), int(mm))

def time_to_hhmm(t: dtime) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"

st.set_page_config(page_title="Stock Notifier – Einstellungen", page_icon="🛠️", layout="centered")
st.title("⚙️ Stock Notifier – Konfiguration")

cfg = read_raw_config()
tabs = st.tabs(["Allgemein", "Benachrichtigung", "Logging", "Marktzeiten", "News", "Test/Debug"])

# --- Allgemein ---
with tabs[0]:
    tickers_text = st.text_area(
        "Ticker (kommagetrennt)", value=",".join(cfg.get("tickers", [])),
        help="Beispiele: AAPL, MSFT, NVDA, O, SAP.DE"
    )
    threshold = st.number_input("Schwelle Δ% vs. Open", min_value=0.01, max_value=50.0,
                                step=0.01, value=float(cfg.get("threshold_pct", 1.0)))
    st.caption("Hinweis: Sehr niedrige Schwellen erzeugen viele Benachrichtigungen.")

# --- Benachrichtigung ---
with tabs[1]:
    ntfy = cfg.get("ntfy", {})
    ntfy_server = st.text_input("ntfy Server", ntfy.get("server", "https://ntfy.sh"))
    ntfy_topic = st.text_input("ntfy Topic", ntfy.get("topic", "${NTFY_TOPIC}"),
                               help="Tipp: '${NTFY_TOPIC}' belassen und Topic als GitHub Secret setzen.")
    if st.button("🔔 Testbenachrichtigung senden"):
        # einfacher Test ohne App-Importe
        import requests
        title = "Config Test"
        body = "Hallo von der Streamlit-UI 👋"
        try:
            r = requests.post(ntfy_server.rstrip("/") + "/" + ntfy_topic, data=body.encode("utf-8"),
                              headers={"Title": title, "Priority": "default", "Markdown": "yes"}, timeout=15)
            st.success(f"ntfy Antwort: {r.status_code}")
        except Exception as e:
            st.error(f"Fehler: {e}")

# --- Logging ---
with tabs[2]:
    log = cfg.get("log", {})
    level = st.selectbox("Log Level", ["DEBUG", "INFO", "WARNING", "ERROR"],
                         index=["DEBUG","INFO","WARNING","ERROR"].index(str(log.get("level", "INFO")).split(":")[-1]))
    log_file = st.text_input("Log Datei", log.get("file", "alerts.log"))

# --- Marktzeiten ---
with tabs[3]:
    mh = cfg.get("market_hours", {})
    tz = st.text_input("Zeitzone", mh.get("timezone", "America/New_York"),
                       help="IANA Timezone, z. B. Europe/Berlin oder America/New_York")
    open_time = st.time_input("Börsenstart (hh:mm)", value=hhmm_to_time(mh.get("open", "09:30")))
    close_time = st.time_input("Börsenschluss (hh:mm)", value=hhmm_to_time(mh.get("close", "16:00")))
    day_labels = [(1,"Mo"),(2,"Di"),(3,"Mi"),(4,"Do"),(5,"Fr"),(6,"Sa"),(7,"So")]
    sel_days = st.multiselect("Aktive Tage", options=[d for d,_ in day_labels],
                              default=list(mh.get("active_days", [1,2,3,4,5])),
                              format_func=lambda x: dict(day_labels)[x])
    pause = st.checkbox("Außerhalb der Marktzeiten pausieren", value=bool(mh.get("pause_on_closed", True)))

# --- News ---
with tabs[4]:
    nw = cfg.get("news", {})
    news_enabled = st.checkbox("News anfügen", value=bool(nw.get("enabled", True)))
    news_limit = st.slider("Max. Headlines", min_value=0, max_value=5, value=int(nw.get("max_items", 3)))
    news_lookback = st.slider("Zeitraum (Stunden)", min_value=6, max_value=48, value=int(nw.get("lookback_hours", 12)))
    col1, col2 = st.columns(2)
    with col1:
        news_lang = st.text_input("Sprache (primär)", nw.get("lang", "de"))
        news_country = st.text_input("Land (primär)", nw.get("country", "DE"))
    with col2:
        fb_lang = st.text_input("Fallback-Sprache", nw.get("fallback_lang", "en"))
        fb_country = st.text_input("Fallback-Land", nw.get("fallback_country", "US"))

# --- Test/Debug ---
with tabs[5]:
    tc = cfg.get("test", {})
    t_enabled = st.checkbox("Testmodus aktiv", value=bool(tc.get("enabled", True)))
    t_dry = st.checkbox("Dry-Run (kein Versand)", value=bool(tc.get("dry_run", False)))
    t_bypass = st.checkbox("Market Hours ignorieren", value=bool(tc.get("bypass_market_hours", False)))
    t_force = st.text_input("Erzwinge Δ% (leer = aus)", value="" if tc.get("force_delta_pct") in (None,"") else str(tc.get("force_delta_pct")))
    t_force_out = st.checkbox("force_run_outside_hours (Legacy)", value=bool(tc.get("force_run_outside_hours", False)))

st.divider()
if st.button("💾 Speichern"):
    new_cfg = {
        "tickers": [t.strip() for t in tickers_text.split(",") if t.strip()],
        "threshold_pct": float(threshold),
        "ntfy": {"server": ntfy_server, "topic": ntfy_topic},
        "log": {"level": level, "file": log_file},
        "state_file": cfg.get("state_file", "alert_state.json"),
        "market_hours": {
            "timezone": tz,
            "open": time_to_hhmm(open_time),
            "close": time_to_hhmm(close_time),
            "active_days": [int(d) for d in sel_days],
            "pause_on_closed": bool(pause),
        },
        "test": {
            "enabled": bool(t_enabled),
            "dry_run": bool(t_dry),
            "bypass_market_hours": bool(t_bypass),
            "force_delta_pct": None if (t_force.strip() == "") else float(t_force),
            "force_run_outside_hours": bool(t_force_out),
        },
        "news": {
            "enabled": bool(news_enabled),
            "max_items": int(news_limit),
            "lookback_hours": int(news_lookback),
            "lang": news_lang,
            "country": news_country,
            "fallback_lang": fb_lang,
            "fallback_country": fb_country,
        },
    }
    write_config(new_cfg)
    st.success("Konfiguration gespeichert.")
    st.code(json.dumps(new_cfg, ensure_ascii=False, indent=2), language="json")

st.caption("Tipp: `streamlit run streamlit_app.py` starten. Cron bei GitHub Actions läuft in UTC.")
