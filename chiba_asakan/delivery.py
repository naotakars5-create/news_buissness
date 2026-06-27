"""配信オーケストレーション。

原稿（Manuscript）を支払い済み購読者へ LINE 配信し、
1 人ずつの成否を記録する。配信失敗者は必ずログ＆ファイルに残す（本番運用想定）。
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .line_client import LineApiError, LineClient
from .logging_config import get_logger
from .models import Manuscript, STATUS_APPROVED, STATUS_SENT
from .stripe_filter import PaidResolution, resolve_paid_subscribers
from .subscribers import Subscriber, load_subscribers

logger = get_logger("delivery")


@dataclass
class RecipientResult:
    line_user_id: str
    name: str
    status: str            # "sent" | "failed"
    error: str = ""
    http_status: int | None = None


@dataclass
class DeliveryResult:
    date: str
    started_at: str
    finished_at: str = ""
    dry_run: bool = False
    total_subscribers: int = 0
    target_count: int = 0       # 支払い済み（配信対象）
    sent_count: int = 0
    failed_count: int = 0
    skipped_unpaid: int = 0
    skipped_inactive: int = 0
    stripe_errors: int = 0
    results: list[RecipientResult] = field(default_factory=list)
    log_path: str = ""

    @property
    def failures(self) -> list[RecipientResult]:
        return [r for r in self.results if r.status == "failed"]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_delivery_log(cfg: Config, result: DeliveryResult) -> Path:
    """配信結果（失敗者含む）を JSON ファイルに保存する。"""
    cfg.delivery_log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_dryrun" if result.dry_run else ""
    path = cfg.delivery_log_dir / f"{result.date}_{ts}{suffix}.json"
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def deliver(
    cfg: Config,
    manuscript: Manuscript,
    *,
    dry_run: bool = False,
    subscribers: list[Subscriber] | None = None,
    rate_limit_sleep: float = 0.0,
    skip_payment_check: bool = False,
) -> DeliveryResult:
    """原稿を支払い済み購読者へ配信する。

    dry_run=True の場合は実際には送信せず、対象者の集計だけ行う（テスト用）。
    skip_payment_check=True の場合は支払い判定をスキップし、active な購読者を全員対象にする
    （自分宛てテスト配信など、購読者リストを直接渡すケース用）。
    """
    result = DeliveryResult(date=manuscript.date, started_at=_now_iso(), dry_run=dry_run)

    # 1) 購読者ロード
    if subscribers is None:
        subscribers = load_subscribers(cfg)
    result.total_subscribers = len(subscribers)

    # 2) 支払い判定（Stripe or CSV）。skip_payment_check 時は active 全員を対象に。
    if skip_payment_check:
        active = [s for s in subscribers if s.active]
        inactive = [s for s in subscribers if not s.active]
        resolution = PaidResolution(paid=active, unpaid=[], inactive=inactive, errors=[])
    else:
        resolution = resolve_paid_subscribers(subscribers, cfg)
    result.target_count = len(resolution.paid)
    result.skipped_unpaid = len(resolution.unpaid)
    result.skipped_inactive = len(resolution.inactive)
    result.stripe_errors = len(resolution.errors)

    logger.info(
        "配信開始: date=%s dry_run=%s 対象=%d (未払い=%d 配信OFF=%d 照会エラー=%d)",
        manuscript.date, dry_run, result.target_count,
        result.skipped_unpaid, result.skipped_inactive, result.stripe_errors,
    )

    text = manuscript.to_line_text()

    # 3) 実配信
    line_client: LineClient | None = None
    if not dry_run:
        line_client = LineClient(cfg.line_channel_access_token)

    for sub in resolution.paid:
        if dry_run:
            result.results.append(
                RecipientResult(line_user_id=sub.line_user_id, name=sub.name, status="sent")
            )
            result.sent_count += 1
            continue

        try:
            assert line_client is not None
            line_client.push_text(sub.line_user_id, text)
            result.results.append(
                RecipientResult(line_user_id=sub.line_user_id, name=sub.name, status="sent")
            )
            result.sent_count += 1
        except LineApiError as exc:
            result.results.append(
                RecipientResult(
                    line_user_id=sub.line_user_id,
                    name=sub.name,
                    status="failed",
                    error=str(exc),
                    http_status=exc.status_code,
                )
            )
            result.failed_count += 1
            logger.error(
                "配信失敗: line=%s name=%s status=%s body=%s",
                sub.line_user_id, sub.name, exc.status_code, (exc.body or "")[:300],
            )
        except Exception as exc:  # noqa: BLE001 想定外も必ず記録して続行
            result.results.append(
                RecipientResult(
                    line_user_id=sub.line_user_id,
                    name=sub.name,
                    status="failed",
                    error=f"想定外エラー: {exc}",
                )
            )
            result.failed_count += 1
            logger.exception("配信中に想定外エラー: line=%s", sub.line_user_id)

        if rate_limit_sleep > 0:
            time.sleep(rate_limit_sleep)

    result.finished_at = _now_iso()

    # 4) ログ保存
    log_path = _write_delivery_log(cfg, result)
    result.log_path = str(log_path)

    logger.info(
        "配信完了: date=%s 成功=%d 失敗=%d ログ=%s",
        manuscript.date, result.sent_count, result.failed_count, log_path.name,
    )
    if result.failures:
        logger.warning(
            "配信失敗者 %d 名: %s",
            len(result.failures),
            ", ".join(f"{r.name or r.line_user_id}" for r in result.failures),
        )
    return result


def mark_manuscript_sent(manuscript: Manuscript, result: DeliveryResult) -> None:
    """配信結果を原稿に書き戻す（呼び出し側で store.save する想定）。"""
    if not result.dry_run and result.sent_count > 0:
        manuscript.status = STATUS_SENT
    manuscript.last_delivery = {
        "finished_at": result.finished_at,
        "dry_run": result.dry_run,
        "target_count": result.target_count,
        "sent_count": result.sent_count,
        "failed_count": result.failed_count,
        "log_path": result.log_path,
    }


def should_deliver(manuscript: Manuscript | None, force: bool = False) -> tuple[bool, str]:
    """この原稿を本配信してよいかと、その理由（配信しない理由）を返す。

    安全設計: 原則『承認済み(approved)』かつ本文が揃っているときのみ配信する。
    force=True で承認チェックのみスキップ（本文不備は依然として配信しない）。
    """
    if manuscript is None:
        return False, "対象日の原稿がありません"
    if not force and manuscript.status != STATUS_APPROVED:
        return False, f"原稿が承認されていません（status={manuscript.status}）"
    if not manuscript.is_complete():
        return False, "原稿に未入力セクションがあります: " + " / ".join(manuscript.missing_sections())
    return True, ""


# 「LINEテスト配信」ボタンで送る固定メッセージ
TEST_MESSAGE = (
    "【ちば営業朝刊】\n"
    "LINEテスト配信に成功しました。\n"
    "このメッセージが届いていれば、LINE配信設定は完了です。"
)


def _mask_uid(uid: str) -> str:
    """userId を伏せ字にして返す（ログ・画面に生値を出さないため）。"""
    if not uid:
        return "(未設定)"
    if len(uid) > 8:
        return f"{uid[:5]}…{uid[-2:]}"
    return "***"


def _log_test_failure(cfg: Config, message: str, body: str | None = None) -> None:
    """テスト配信の失敗を logs/line_test.log に追記する（秘密情報は書かない）。"""
    try:
        cfg.log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        line = f"{ts}\tFAILED\t{message}"
        if body:
            line += f"\tresponse={body[:300]}"
        with (cfg.log_dir / "line_test.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001  ログ書き込み失敗で処理を止めない
        logger.exception("line_test.log への書き込みに失敗しました。")


def send_line_test(
    cfg: Config,
    text: str | None = None,
    user_id: str | None = None,
) -> tuple[bool, str]:
    """LINE_TEST_USER_ID 宛にテスト送信する。

    必要な設定は LINE_CHANNEL_ACCESS_TOKEN と LINE_TEST_USER_ID のみ。
    text=None なら固定メッセージ(TEST_MESSAGE)を送る。手動テキストは text に渡す。
    返り値: (成功, エラー文)。失敗時は logs/line_test.log に記録する。
    """
    target = (user_id or cfg.line_test_user_id or "").strip()
    message = TEST_MESSAGE if text is None else text

    if not cfg.has_line():
        err = "LINE_CHANNEL_ACCESS_TOKEN が未設定です"
        _log_test_failure(cfg, err)
        return False, err
    if not target:
        err = "LINE_TEST_USER_ID が未設定です"
        _log_test_failure(cfg, err)
        return False, err
    if not message.strip():
        return False, "送信するメッセージが空です"

    try:
        LineClient(cfg.line_channel_access_token).push_text(target, message)
        logger.info("LINEテスト配信 成功: 宛先=%s", _mask_uid(target))
        return True, ""
    except LineApiError as exc:
        err = f"LINE APIエラー (status={exc.status_code})"
        _log_test_failure(cfg, f"{err} 宛先={_mask_uid(target)} detail={exc}", exc.body)
        logger.error("LINEテスト配信 失敗: %s 宛先=%s", err, _mask_uid(target))
        return False, f"{err}: {exc}"
    except Exception as exc:  # noqa: BLE001
        _log_test_failure(cfg, f"想定外エラー 宛先={_mask_uid(target)}: {exc}")
        logger.exception("LINEテスト配信 想定外エラー")
        return False, str(exc)


def send_single_test(cfg: Config, manuscript: Manuscript, user_id: str) -> tuple[bool, str]:
    """原稿1本を指定ユーザー（自分など）にだけ送る『テスト配信』。

    内部は send_line_test に委譲（失敗は logs/line_test.log にも記録される）。
    """
    return send_line_test(cfg, text=manuscript.to_line_text(), user_id=user_id)
