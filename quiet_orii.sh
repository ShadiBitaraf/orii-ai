#!/bin/bash
export PYTHONWARNINGS="ignore"
export LOGLEVEL="CRITICAL"
python -c "import logging; logging.basicConfig(level=logging.CRITICAL); from backend.app.utils.logger import logger; logger.setLevel(logging.CRITICAL); import logging.config; logging.config.dictConfig({\"version\": 1, \"disable_existing_loggers\": True}); from backend.app.cli.main import main; main()"
