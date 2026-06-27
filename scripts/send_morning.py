"""毎朝の自動配信スクリプト（GitHub Actions / Cloud Run / cron から実行）。

安全設計（要件: 完全自動ではなく承認後に配信）:
  - 対象日の原稿が「承認済み(approved)」のときだけ配信する。
  - 承認されていない／原稿が無い場合は、配信せずにログを残して正常終了する。
  - --force を付けると承認チェックを飛ばす（手動リカバリ用）。

使い方:
  python -m scripts.send_morning                # 今日（TIMEZONE基準）の承認済み原稿を配信
  python -m scripts.send_morning --date 2026-06-25
  python -m scripts.send_morning --dry-run      # 送信せず対象者数のみ
  python -m scripts.send_morning --force        # 承認チェックを飛ばす
  python -m scripts.send_morning --to-test-user # 購読者ではなく LINE_TEST_USER_ID（自分）だけに配信

終了コード:
  0 = 正常（配信した／対象なしでスキップ）
  1 = 設定不足や原稿不備で配信できず
  2 = 配信したが一部失敗者あり
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

# `python scripts/send_morning.py` でも動くようにプロジェクトルートを import パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chiba_asakan.config import load_config  # noqa: E402
from chiba_asakan.delivery import deliver, mark_manuscript_sent, should_deliver  # noqa: E402
from chiba_asakan.logging_config import get_logger, setup_logging  # noqa: E402
from chiba_asakan.models import STATUS_APPROVED  # noqa: E402
from chiba_asakan.storage import ManuscriptStore  # noqa: E402


def _today_in_tz(tz_name: str) -> date:
    """設定タイムゾーンでの「今日」を返す。"""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(tz_name)).date()
    except Exception:  # noqa: BLE001  zoneinfo不可なら端末ローカル
        return date.today()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ちば営業朝刊 自動配信")
    parser.add_argument("--date", help="配信日 YYYY-MM-DD（既定: 今日）")
    parser.add_argument("--dry-run", action="store_true", help="送信せず対象者数のみ集計")
    parser.add_argument(
        "--force", action="store_true", help="承認チェックを飛ばして配信（手動リカバリ用）"
    )
    parser.add_argument(
        "--rate-limit-sleep", type=float, default=0.0, help="1通ごとの待機秒（任意）"
    )
    parser.add_argument(
        "--to-test-user", action="store_true",
        help="購読者リストではなく LINE_TEST_USER_ID（自分）だけに配信する",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = load_config()
    setup_logging(cfg.log_dir)
    logger = get_logger("send_morning")
    store = ManuscriptStore(cfg.manuscript_dir)

    target_date = args.date or _today_in_tz(cfg.timezone).isoformat()
    logger.info("=== 自動配信開始: date=%s dry_run=%s force=%s to_test_user=%s ===",
                target_date, args.dry_run, args.force, args.to_test_user)

    # 設定不足チェック（自分宛てモードは購読者CSV不要・LINEトークン+TEST_USER_IDのみ）
    if args.to_test_user:
        missing = []
        if not cfg.has_line():
            missing.append("LINE_CHANNEL_ACCESS_TOKEN")
        if not cfg.line_test_user_id:
            missing.append("LINE_TEST_USER_ID")
    else:
        missing = cfg.missing_for_delivery()
    if missing and not args.dry_run:
        logger.error("配信に必要な設定が不足しています: %s", ", ".join(missing))
        return 1

    # 原稿のロードと配信可否判定（承認済みのみ・--forceで承認チェックのみスキップ）
    manuscript = store.load(target_date)
    ok, reason = should_deliver(manuscript, force=args.force)
    if not ok:
        # 「承認済み原稿なし（または原稿なし）」は正常終了(0)。本文不備など準備不足は 1。
        no_approved = manuscript is None or (
            not args.force and manuscript.status != STATUS_APPROVED
        )
        if no_approved:
            logger.warning(
                "承認済み原稿なし: 配信しません（date=%s）。理由: %s", target_date, reason
            )
            return 0
        logger.warning("配信しません（date=%s）: %s", target_date, reason)
        return 1
    assert manuscript is not None

    # 配信
    if args.to_test_user:
        from chiba_asakan.subscribers import Subscriber  # noqa: E402

        logger.info("自分宛てモード: LINE_TEST_USER_ID にのみ配信します。")
        subs = [Subscriber(
            line_user_id=cfg.line_test_user_id, name="(test)", paid=True, active=True
        )]
        result = deliver(
            cfg, manuscript, dry_run=args.dry_run, subscribers=subs,
            skip_payment_check=True, rate_limit_sleep=args.rate_limit_sleep,
        )
    else:
        result = deliver(
            cfg, manuscript, dry_run=args.dry_run, rate_limit_sleep=args.rate_limit_sleep
        )

    if not args.dry_run:
        mark_manuscript_sent(manuscript, result)
        store.save(manuscript)

    logger.info(
        "=== 自動配信終了: 成功=%d 失敗=%d 対象=%d ===",
        result.sent_count, result.failed_count, result.target_count,
    )

    if result.failed_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
