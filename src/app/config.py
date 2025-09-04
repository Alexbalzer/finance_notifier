from __future__ import annotations
import os, json
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv

# Default configuration values used if no config.json or .env overrides are provided.
DEFAULTS: Dict[str, Any] = {
    "log": {
        "level": "INFO",               # Default logging level
        "to_file": False,              # Write logs to file? (default: only console)
        "file_path": "alerts.log",     # Log file location
        "file_max_bytes": 1_000_000,   # Max size of log file before rotation
        "file_backup_count": 3         # Number of rotated log files to keep
    },
    "ntfy": {
        "server": "https://ntfy.sh",   # Default ntfy server
        "topic": "CHANGE-ME"           # Must be set in config.json or .env
    },
    "tickers": ["AAPL"],               # Default ticker(s) to monitor
    "threshold_pct": 3.0,              # Default % threshold for alerts
    "state_file": "alert_state.json",  # File to persist alert state (anti-spam)
    "market_hours": {                  # Market hours configuration
        "enabled": True,
        "tz": "Europe/Berlin",         # Default timezone
        "start_hour": 8,
        "end_hour": 22,
        "days_mon_to_fri_only": True   # Only Monday–Friday
    },
    "test": {                          # Test mode settings
        "enabled": False,
        "bypass_market_hours": True,
        "force_delta_pct": None,       # Simulate price changes
        "dry_run": False               # Dry-run: do not send actual notifications
    },
}

def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge two dictionaries.
    """
    # Begin with a shallow copy of base
    out = dict(base)

    # Iterate through override items and merge/override accordingly
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v

    #  Return the merged dictionary
    return out
    


def load_config(path: str = "config.json") -> Dict[str, Any]:
    """
    Load the configuration for the application.

    Priority:
    1. Default values from DEFAULTS
    2. Overrides from config.json (if present)
    3. Overrides from environment variables (.env or OS-level)
    """
    # Load environment variables via load_dotenv()
    load_dotenv()

    # Read config.json (if it exists) and parse JSON into 'user'
    user = {}
    p = Path(path)
    if p.exists():
        try:
            user = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            raise RuntimeError(f"config.json could not be read: {e}")

    # Merge DEFAULTS with user config using deep_merge()
    cfg = deep_merge(base=DEFAULTS, override=user)

    #  Apply environment variable overrides (LOG_LEVEL, NTFY_SERVER, NTFY_TOPIC)
    if os.getenv("LOG_LEVEL"):
        cfg["log"]["level"] = os.getenv("LOG_LEVEL")
    if os.getenv("NTFY_SERVER"):
        cfg["ntfy"]["server"] = os.getenv("NTFY_SERVER")
    if os.getenv("NTFY_TOPIC"):
        cfg["ntfy"]["topic"] = os.getenv("NTFY_TOPIC")


    #  Validate critical settings (ntfy topic, tickers)
    if not cfg["ntfy"]["topic"] or cfg["ntfy"]["topic"] =="CHANGE-ME":
        raise RuntimeError(
            """
            Please set a secret ntfy topic on config.jons or .env

            """
        )
    if not cfg["tickers"]:
        raise RuntimeError("config.tickers must not be emty")

    # Return the final configuration dictionary
    return cfg
  # Remove once implemented
