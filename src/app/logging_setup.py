import logging
from logging.handlers import RotatingFileHandler
from typing import Dict, Any

def setup_logging(cfg_log: Dict[str, Any]) -> logging.Logger:
    level_name = (cfg_log or {}).get("level", "INFO")
    level = getattr(logging, str(level_name).upper(), logging.INFO)

    logger = logging.getLogger("stock-alerts")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if (cfg_log or {}).get("to_file", False):
        fh = RotatingFileHandler(
            (cfg_log.get("file_path") or "alerts.log"),
            maxBytes=int(cfg_log.get("file_max_bytes", 1_000_000)),
            backupCount=int(cfg_log.get("file_backup_count", 3)),
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.debug("Logging initialized: level=%s, to_file=%s",
                 level_name, (cfg_log or {}).get("to_file", False))
    return logger

# import logging
# from logging.handlers import RotatingFileHandler
# from typing import Dict, Any


# def setup_logging(cfg_log: Dict[str, Any]) -> logging.Logger:
#     """
#     Configure and return the central logger for the app.

#     Features:
#       - Log level configurable via config (DEBUG, INFO, WARNING, …)
#       - Always logs to console (stdout)
#       - Optional rotating file handler for persistent logs:
#           * File size limit (maxBytes)
#           * Number of backups (backupCount)
#           * UTF-8 encoding for international characters

#     Args:
#         cfg_log: Logging configuration dictionary. Expected keys:
#             - "level": str - log level (e.g. "INFO", "DEBUG")
#             - "to_file": bool - whether to also log to a file
#             - "file_path": str - log filename (default "alerts.log")
#             - "file_max_bytes": int - max file size before rotation
#             - "file_backup_count": int - number of rotated backups to keep

#     Returns:
#         logging.Logger: Configured logger instance named "stock-alerts".
#     """
#     # Resolve log level from cfg_log (fallback to INFO)
#     # level_name = ...
#     # level = ...

#     # : Obtain the named logger "stock-alerts" and set its level
#     # logger = ...
#     # logger.setLevel(level)

#     # : Clear any existing handlers to avoid duplicates
#     # logger.handlers.clear()

#     # : Create a Formatter with timestamp, level and message
#     # fmt = ...

#     # : Configure a StreamHandler for console output, apply formatter and add it
#     # ch = ...
#     # logger.addHandler(ch)

#     # : If cfg_log["to_file"] is true, create a RotatingFileHandler with provided settings
#     # if cfg_log.get("to_file", False):
#     #     fh = RotatingFileHandler(...)
#     #     fh.setFormatter(fmt)
#     #     logger.addHandler(fh)

#     # : Log a debug message summarizing the final logging setup
#     # logger.debug("Logging initialized: level=%s, to_file=%s", level_name, cfg_log.get("to_file", False))

#     # : Return the configured logger
#     # return logger
#     pass  # Remove once implemented
