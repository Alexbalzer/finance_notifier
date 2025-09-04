from pathlib import Path
from src.app.config import load_config
from src.app.logging_setup import setup_logging
from src.app.core import run_once
from src.app.utils import mask_secret

from src.app.ntfy import notify_ntfy


def main():
    """
    Entry point of the Stock Notifier application.
    """
    #  Load configuration from "config.json"
    cfg = load_config("config.json")

    #  Initialize the logging system with setup_logging
    logger = setup_logging(cfg["log"])

    # Log the loaded configuration, masking secrets with mask_secret
    logger.info(
        "Configuration loaded: ntfy.server=%s | ntfy.topic(masked)=%s | log.level=%s",
        cfg["ntfy"]["server"],
        mask_secret(cfg["ntfy"]["topic"]),
        cfg["log"]["level"],
    )

    # Run one monitoring cycle via run_once using settings from cfg
    run_once(
        tickers=cfg["tickers"],
        threshold_pct=float(cfg["threshold_pct"]),
        ntfy_server=cfg["ntfy"]["server"],
        ntfy_topic=cfg["ntfy"]["topic"],
        state_file=Path(cfg["state_file"]),
        market_hours_cfg=cfg["market_hours"],
        test_cfg=cfg["test"],
        news_cfg=cfg.get("news", {"enabled": False}),
    )

    # TEmporäres Test-Aufruf
    # from src.app.utils import mask_secret
    # print(mask_secret(cfg["ntfy"]["topic"]))
    # notify_ntfy(
    #     server = cfg["ntfy"]["server"], 
    #     topic=cfg["ntfy"]["topic"], 
    #     title="Test",
    #     message="diese Zeile kommt aus main.py")
    


if __name__ == "__main__":
    main()
