"""ネタ収集スクリプト（毎朝 6:30 JST 想定）。

情報ソースを巡回 → 除外フィルター → スコアリング → 候補保存（data/source_items/）。
承認・配信は行わない。

使い方:
  python -m scripts.collect_news               # 今日ぶんを収集
  python -m scripts.collect_news --date 2026-06-25
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chiba_asakan.config import load_config  # noqa: E402
from chiba_asakan.logging_config import get_logger, setup_logging  # noqa: E402
from chiba_asakan.pipeline import collect_and_store  # noqa: E402


def _today_in_tz(tz_name: str) -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:  # noqa: BLE001
        return date.today()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ちば営業朝刊 ネタ収集")
    parser.add_argument("--date", help="対象日 YYYY-MM-DD（既定: 今日）")
    args = parser.parse_args(argv)

    cfg = load_config()
    setup_logging(cfg.log_dir)
    logger = get_logger("collect_news")

    date_str = args.date or _today_in_tz(cfg.timezone).isoformat()
    logger.info("=== ネタ収集開始: date=%s ===", date_str)

    records = collect_and_store(cfg, date_str)
    candidates = [r for r in records if not r.excluded and r.score >= cfg.score_threshold]
    excluded = [r for r in records if r.excluded]

    logger.info(
        "=== ネタ収集終了: 取得=%d 候補=%d 除外=%d ===",
        len(records), len(candidates), len(excluded),
    )
    if not records:
        logger.warning(
            "取得0件。フィードURL未設定の可能性があります（SOURCE_FEED_OVERRIDES を確認）。"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
