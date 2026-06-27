"""ネタ収集パイプライン: 巡回 → 除外判定 → 採点 → 保存。

scripts/collect_news.py と Streamlit の「巡回」ボタンの両方から呼ばれる。
"""
from __future__ import annotations

from datetime import date, datetime

from .config import Config
from .exclusion import evaluate_item_exclusion
from .logging_config import get_logger
from .scoring import score_item
from .source_store import SourceItemStore, SourceRecord
from .sources.source_base import Fetcher
from .sources.source_manager import SourceManager

logger = get_logger("pipeline")


def _to_date(date_str: str) -> date:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return date.today()


def collect_and_store(
    cfg: Config,
    date_str: str,
    fetcher: Fetcher | None = None,
) -> list[SourceRecord]:
    """全ソースを巡回し、除外判定・採点して保存し、マージ後のレコードを返す。"""
    today = _to_date(date_str)

    manager = SourceManager(cfg, fetcher=fetcher)
    items = manager.collect_all()

    records: list[SourceRecord] = []
    for item in items:
        exclusion = evaluate_item_exclusion(item, extra_hard=cfg.exclude_keywords_extra)
        score = score_item(cfg, item, today=today)
        records.append(SourceRecord.build(item, date_str, score, exclusion))

    store = SourceItemStore(cfg.source_item_dir)
    merged = store.merge_records(date_str, records)

    n_excluded = sum(1 for r in merged if r.excluded)
    n_candidate = sum(1 for r in merged if not r.excluded and r.score >= cfg.score_threshold)
    logger.info(
        "収集結果: 取得=%d 除外=%d 候補(>=%d点)=%d",
        len(merged), n_excluded, cfg.score_threshold, n_candidate,
    )
    return merged
