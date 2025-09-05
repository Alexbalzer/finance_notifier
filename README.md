# Stock Notifier (ntfy + Google News)

Ein leichter **Börsen-Notifier**, der Kursbewegungen überwacht, bei Überschreitung einer Schwelle per **ntfy** pusht und optional **Top-Headlines** aus Google News anhängt.  
Die Konfiguration erfolgt bequem über eine **Streamlit-Oberfläche**; der Betrieb kann automatisiert via **GitHub Actions** erfolgen.

---

## ✨ Features

- Δ % **gegenüber dem Eröffnungskurs** (intraday), hübsche **📈/📉** und **↑/↓** im Nachrichtentext  
- **Korridor-Logik** (`up` / `down` / `none`): erneute Alerts erst nach Rückkehr in den Korridor  
- **News-Block** (DE → EN/US-Fallback) mit Bereinigung von Google-Redirects  
- **Klickbarer Top-Link** (ntfy „Click“) direkt zur wichtigsten Meldung  
- **Streamlit-GUI** zum Bearbeiten von `config.json`  
- **GitHub Actions**: automatisch alle 30 Minuten oder manuell  
- Einfache **Spam-Vermeidung** via `alert_state.json` (wird bei Actions gecached)

---

## 📦 Installation (lokal)

```bash
# 1) Klonen
git clone git@github.com:Alexbalzer/finance_notifier.git
cd finance_notifier

# 2) Virtuelle Umgebung & Abhängigkeiten
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt


## 🚀 Installation

1. Repository klonen:
   ```bash
   git clone git@github.com:Alexbalzer/Credit-Risk-Modeling-Streamlit-App.git
   cd Credit-Risk-Modeling-Streamlit-App


2. Virtuelle Umgebung erstellen und Abhängigkeiten installieren:

python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

pip install -r requirements.txt

3

## ▶️ Starten
- A) Notifier einmalig ausführen
python main.py

- B) GUI zum Bearbeiten der Konfiguration
- streamlit run app.py

## ⚙️ Konfiguration (config.json)

Beispiel (gekürzt):
{
  "tickers": ["AAPL", "O", "WPY.F", "QDVX.DE"],
  "threshold_pct": 0.10,
  "ntfy": { "server": "https://ntfy.sh", "topic": "${NTFY_TOPIC}" },
  "log": { "level": "${LOG_LEVEL:INFO}", "file": "alerts.log" },
  "state_file": "alert_state.json",
  "market_hours": {
    "timezone": "America/New_York",
    "open": "09:30",
    "close": "16:00",
    "active_days": [1,2,3,4,5],
    "pause_on_closed": true
  },
  "test": {
    "enabled": true,
    "dry_run": false,
    "bypass_market_hours": false,
    "force_delta_pct": null,
    "force_run_outside_hours": false
  },
  "news": {
    "enabled": true,
    "max_items": 3,
    "lookback_hours": 12,
    "lang": "de",
    "country": "DE",
    "fallback_lang": "en",
    "fallback_country": "US"
  }
}
### Hinweise

ntfy.topic kann als ${NTFY_TOPIC} gesetzt bleiben (Secret/ENV).

threshold_pct ist die absolute Schwelle in Prozentpunkten (z. B. 0.10 = 0,10 %).

## 🖥️ Projektstruktur

.
├─ .github/
│  └─ workflows/
│     └─ stock_notifier.yml        # GitHub Actions (alle 30 Min. / manuell)
├─ src/
│  ├─ app/
│  │  ├─ core.py                   # Orchestrierung, Korridorlogik, ntfy
│  │  ├─ market.py                 # Kursdaten (Open/Last)
│  │  ├─ news.py                   # Google-News RSS + Link-Bereinigung
│  │  ├─ ntfy.py                   # Versand an ntfy
│  │  ├─ company.py                # Metadaten/Keywords (Cache)
│  │  ├─ state.py, utils.py, ...
│  └─ gui/
│     └─ app.py                    # Streamlit-Konfigoberfläche
├─ main.py                         # Einstieg: lädt config und ruft run_once
├─ config.json                     # Einstellungen (von Streamlit gepflegt)
├─ requirements.txt
├─ alert_state.json                # De-Dupe-State (wird von Actions gecached)
└─ alerts.log                      # Logfile (optional als Artifact)


## 🤖 GitHub Actions

Workflow: .github/workflows/stock_notifier.yml
Trigger: alle 30 Minuten (UTC) und manuell.

Secret setzen

Repo → Settings → Secrets and variables → Actions → New repository secret

Name: NTFY_TOPIC

Value: dein privates ntfy-Topic (nur der Topic-String, ohne URL)

- Artefakte

Nach jedem Lauf können (optional) alerts.log und alert_state.json als Artifacts hochgeladen werden.

## 🛠️ Troubleshooting
Keine ntfy-Nachricht?
Prüfe NTFY_TOPIC (Secret gesetzt?), config.json (Topic = ${NTFY_TOPIC}?) und ob du im ntfy-Web/Client das Topic abonniert hast.

„Bereits benachrichtigt … – skip.“
Das ist die De-Duping/Korridor-Logik. Lösche alert_state.json lokal oder warte, bis der Kurs wieder in den Korridor zurückkehrt.

Windows: „Fatal error in launcher … pip“
venv korrigieren und immer python -m pip verwenden.

Cron-Zeit
GitHub Actions läuft in UTC.

## 📜 Lizenz
Dieses Projekt dient Lern-/Demozwecken. Nutzung auf eigenes Risiko.