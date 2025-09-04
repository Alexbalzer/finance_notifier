# Aufgaben

## Dienstag + Mittwoch

Ziel ist es, alle im Code hinterlegten TODO-Stellen implementieren.
<br>
`(Dateien: company.py, main.py, utils.py, state.py, ntfy.py, news.py, market.py, logging_setup.py, core.py, config.py)`

Ergebnis: Vollständig lauffähige Anwendung ohne offene Platzhalter

## Donnerstag - Grafische Oberfläche und Github Pipeline (Github Actions)

Ziele:
- Streamlit-Konfigurationsoberfläche: Eine kleine Web-App, mit der sich alle Einstellungen der Anwendung bequem anpassen lassen.
- Automatisierung via GitHub Actions: Die Anwendung soll alle 30 Minuten (oder manuell) über GitHub Actions laufen.

**Streamlit:**

Erstelle eine einfache Streamlit-Anwendung, mit der die Einstellungen des Stock-Notifier-Projekts komfortabel verwaltet werden können.
Die Anwendung Stock Notifier nutzt eine Konfigurationsdatei (config.json), um Parameter wie:
- zu überwachende Ticker,
- ntfy-Benachrichtigungsserver und -Topic,
- Logging-Einstellungen,
- Marktzeiten
zu speichern.

Eine grafische Oberfläche erleichtert es, diese Einstellungen zu verändern – ganz ohne manuelles Editieren der JSON-Datei.

**GitHub Actions:**

1. Lege im Repository einen Ordner .github/workflows an.
2. Erstelle darin die Datei stock_notifier.yml mit folgendem Inhalt:

```yaml
name: Stock Notifier

on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  run:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Restore alert_state.json (cache)
        uses: actions/cache@v4
        with:
          path: alert_state.json
          key: alert-state-${{ github.run_number }}
          restore-keys: |
            alert-state-

      - name: Run notifier
        env:
          NTFY_SERVER: https://ntfy.sh
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
          LOG_LEVEL: INFO
        run: |
          python main.py

      - name: Upload logs & state (optional)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: run-${{ github.run_id }}
          path: |
            alerts.log
            alert_state.json
          if-no-files-found: ignore
```

3. GitHub Secrets setzen

Unter Repository Settings → Secrets and variables → Actions den Secret NTFY_TOPIC mit eurem privaten Topic anlegen.

## Freitag: ML-Modell entwerfen und in die App einbauen

Entwickelt ein einfaches Machine-Learning-Modell, das auf Basis historischer Kursdaten vorhersagt, ob ein Ticker am nächsten Handelstag steigen oder fallen wird. Bindet dieses Modell in eure Stock-Notifier-Anwendung ein, sodass vor oder während der Benachrichtigung eine Prognose generiert und ausgegeben wird. Hier sind einige Ideen als Orientierung:

**Nutze yfinance, um historische Kursdaten zu beziehen:**

```python
import yfinance as yf
import pandas as pd

def load_hist_prices(ticker: str, period: str = "2y") -> pd.DataFrame:
    """
    Lädt historische Kursdaten für den angegebenen Ticker.
    
    Args:
        ticker: Börsenticker, z. B. "AAPL".
        period: Zeitraum (z. B. "2y", "1y", "6mo").

    Returns:
        DataFrame mit OHLC-Kursdaten (Open, High, Low, Close, Volume).
    """
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=True)
    df.dropna(inplace=True)  # Entfernt fehlende Einträge
    return df

```

**Leite aus den historischen Daten Features ab und definiere eine Zielvariable:**

```python
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Erstellt Trainingsfeatures und eine Zielvariable (steigt/fällt am nächsten Tag).
    """
    df["return"] = df["Close"].pct_change()
    df["MA5"] = df["Close"].rolling(5).mean()
    df["MA20"] = df["Close"].rolling(20).mean()
    df["target"] = (df["return"].shift(-1) > 0).astype(int)  # 1 = Kurs steigt
    df.dropna(inplace=True)
    return df
```

**Wähle ein geeignetes Modell (z.B. RandomForestClassifier, LogisticRegression). Trainiere, evaluiere und verwende es zur Vorhersage:**

```python
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

def train_model(df: pd.DataFrame):
    """
    Trainiert ein Klassifikationsmodell und gibt es zusammen mit dem Test-Score zurück.
    """
    X = df[["return", "MA5", "MA20"]]
    y = df["target"]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)
    
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"Test-Accuracy: {acc:.2f}")
    return model
```

**Prognose für den letzten Tag:**

```python
def predict_move(model, df: pd.DataFrame) -> bool:
    """
    Erzeugt eine Vorhersage für die letzte Zeile des DataFrames.
    
    Returns:
        True, wenn Modell einen Kursanstieg erwartet, sonst False.
    """
    last_row = df[["return", "MA5", "MA20"]].iloc[-1].values.reshape(1, -1)
    pred = model.predict(last_row)[0]
    return bool(pred)
```

Wie könnte man den Code in die Anwendung integrieren?