"""原稿の自動下書き生成スクリプト（毎朝 6:45 JST 想定）。

その日の候補ネタ（除外されておらず score>=しきい値）から原稿案を AI 生成し、
status=draft で保存する。承認はしない（人が管理画面で確認・承認する）。

安全設計:
  - 既に承認済み(approved)/配信済み(sent)の原稿がある日は上書きしない（--force-overwrite で可）。
  - 候補ネタが無い／AIキー未設定なら何もせず終了（理由をログに残す）。

使い方:
  python -m scripts.generate_draft
  python -m scripts.generate_draft --date 2026-06-25 --length 1200 --psychology 損失回避
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chiba_asakan.config import load_config  # noqa: E402
from chiba_asakan.logging_config import get_logger, setup_logging  # noqa: E402
from chiba_asakan.models import STATUS_APPROVED, STATUS_DRAFT, STATUS_SENT  # noqa: E402
from chiba_asakan.source_store import SourceItemStore  # noqa: E402
from chiba_asakan.storage import ManuscriptStore  # noqa: E402


def _today_in_tz(tz_name: str) -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:  # noqa: BLE001
        return date.today()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ちば営業朝刊 原稿自動下書き")
    parser.add_argument("--date", help="対象日 YYYY-MM-DD（既定: 今日）")
    parser.add_argument("--length", type=int, default=None, help="文字量 800/1000/1200")
    parser.add_argument("--psychology", default=None, help="営業心理テーマを固定する場合に指定")
    parser.add_argument("--max-items", type=int, default=4, help="使う候補ネタの最大件数")
    parser.add_argument("--force-overwrite", action="store_true", help="承認済みでも上書き生成する")
    args = parser.parse_args(argv)

    cfg = load_config()
    setup_logging(cfg.log_dir)
    logger = get_logger("generate_draft")

    date_str = args.date or _today_in_tz(cfg.timezone).isoformat()
    logger.info("=== 原稿自動生成開始: date=%s ===", date_str)

    if not cfg.has_ai():
        logger.error("ANTHROPIC_API_KEY が未設定のため生成できません。")
        return 1

    store = ManuscriptStore(cfg.manuscript_dir)
    existing = store.load(date_str)
    if existing and existing.status in (STATUS_APPROVED, STATUS_SENT) and not args.force_overwrite:
        logger.warning(
            "既に %s の原稿があるため自動生成をスキップします（上書きするなら --force-overwrite）。",
            existing.status,
        )
        return 0

    source_store = SourceItemStore(cfg.source_item_dir)
    candidates = source_store.candidates(date_str, cfg.score_threshold)
    if not candidates:
        logger.warning(
            "候補ネタがありません（score>=%d）。先に collect_news を実行するか、"
            "フィードURLを設定してください。原稿は生成しません。",
            cfg.score_threshold,
        )
        return 0

    items = candidates[: max(1, args.max_items)]
    from chiba_asakan.ai_writer import generate_manuscript  # noqa: E402

    manuscript = generate_manuscript(
        cfg,
        datetime.strptime(date_str, "%Y-%m-%d").date(),
        items,
        psychology_theme=args.psychology,
        target_length=args.length or cfg.draft_length_default,
        status=STATUS_DRAFT,  # 承認はしない
    )
    store.save(manuscript)
    # 使用したネタにフラグを立てる
    source_store.set_used(date_str, {r.id for r in items}, used=True)

    logger.info(
        "=== 原稿自動生成終了: date=%s 使用ネタ=%d件 本文約%d字 status=%s ===",
        date_str, len(items), manuscript.char_count(), manuscript.status,
    )
    logger.info("※ 配信するには管理画面（③ 原稿確認・承認）で承認してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
