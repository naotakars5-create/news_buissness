"""ロギング設定。

本番運用を想定し、ファイル（ローテーション付き）とコンソールの両方に出力する。
各モジュールは `logging.getLogger("chiba_asakan.xxx")` でロガーを取得する。
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """ルートに近い 'chiba_asakan' ロガーを初期化して返す。

    複数回呼ばれてもハンドラが重複しないようにする。
    """
    global _CONFIGURED
    logger = logging.getLogger("chiba_asakan")
    logger.setLevel(level)

    if _CONFIGURED:
        return logger

    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    # ファイル（1ファイル5MB・5世代）
    file_handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # コンソール
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    logger.propagate = False
    _CONFIGURED = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """サブモジュール用ロガーを取得する。"""
    return logging.getLogger(f"chiba_asakan.{name}")
