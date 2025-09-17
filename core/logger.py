"""
アプリ全体のログ管理（ローテーション対応）
"""
import logging
from logging.handlers import RotatingFileHandler
import os
from config.settings import LOG_DIR, LOG_FILE_BASENAME, LOG_MAX_BYTES, LOG_BACKUP_COUNT

_logger = None

def get_logger():
    global _logger
    if _logger:
        return _logger

    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("multi_cam_qr_app")
    logger.setLevel(logging.INFO)

    log_path = os.path.join(LOG_DIR, LOG_FILE_BASENAME)
    handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # コンソールにも出す
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    _logger = logger
    return _logger
