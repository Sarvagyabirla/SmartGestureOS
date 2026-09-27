import logging
from logging.handlers import RotatingFileHandler
from src.paths import LOGS_DIR

def setup_logger():
    log_dir = LOGS_DIR
    log_file = log_dir / "smart_gesture_os.log"

    logger = logging.getLogger("SmartGestureOS")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    # A permissions/storage failure must not prevent application startup.
    try:
        file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError as exc:
        logger.warning("Diagnostic file logging unavailable: %s", exc)
        
    return logger

logger = setup_logger()
