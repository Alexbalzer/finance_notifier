import json
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger("stock-alerts")

def load_state(path: Path) -> Dict[str, str]:
    """Load the last alert state from a JSON file."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                logger.debug("Loaded state from %s: %s", path, data)
                return data
        except Exception as e:
            logger.warning("Could not read state %s: %s", path, e)
    return {}

def save_state(path: Path, state: Dict[str, str]) -> None:
    """Save the current alert state to disk."""
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("Saved state to %s: %s", path, state)


# import json
# import logging
# from pathlib import Path
# from typing import Dict

# logger = logging.getLogger("stock-alerts")

# def load_state(path: Path) -> Dict[str, str]:
#     """Load the last alert state from a JSON file."""
#     """
#     Load the last alert "state" from a JSON file.

#     The state keeps track of which direction (up/down/none) a stock
#     has already triggered an alert for. This prevents sending duplicate
#     notifications every run.
#     """
#     if path.exists():
#         try:
#             data = json.loads(path.read_text(encoding="utf-8"))
#             if isinstance(data, dict):
#                 logger.debug("Loaded state from %s: %s", path, data)
#                 return data
#         except Exception as e:
#             logger.warning("Could not read state %s: %s", path, e)
#     return {}

# def load_state(path: Path) -> Dict[str, str]:
    
#     # Prüfen, ob die Datei existiert und deren Inhalt als JSON laden
#     # Bei Erfolg den geladenen Zustand zurückgeben und einen Debug-Log schreiben
#     # Bei Fehlern eine Warnung loggen und ein leeres Dict zurückgeben
#     pass


# def save_state(path: Path, state: Dict[str, str]) -> None:
#     """
#     Save the current alert state to disk.
#     """
#     # : Den Zustand als JSON (UTF-8) in die Datei schreiben
#     # : Einen Debug-Log mit dem gespeicherten Zustand ausgeben
#     pass
