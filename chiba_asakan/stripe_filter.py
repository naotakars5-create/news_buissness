"""Stripe を使った「支払い済みユーザー」の判定。

2 つのモードをサポートする:
  - REQUIRE_STRIPE_PAID=false : CSV/Sheets の `paid` 列だけで判定（Stripe照会なし）
  - REQUIRE_STRIPE_PAID=true  : 各購読者の stripe_customer_id を Stripe にライブ照会し、
                               有効なサブスク契約（active/trialing 等）がある人だけを対象にする

Stripe 障害時の安全側設計:
  有料サービスのため、判定できなかった購読者は「未払い扱い（配信対象外）」にして
  誤配信を防ぐ。除外した場合は必ずログに残す。
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .logging_config import get_logger
from .subscribers import Subscriber

logger = get_logger("stripe_filter")


@dataclass
class PaidResolution:
    """支払い判定の結果。"""

    paid: list[Subscriber]               # 配信対象（支払い済み & active）
    unpaid: list[Subscriber]             # 未払い
    inactive: list[Subscriber]           # 配信OFF（active=false）
    errors: list[tuple[Subscriber, str]] # 判定エラー（安全側で除外したもの）

    @property
    def target_count(self) -> int:
        return len(self.paid)


def _check_stripe_active(stripe_module, customer_id: str, active_statuses: list[str]) -> bool:
    """Stripe で顧客に有効なサブスク契約があるかを返す。"""
    if not customer_id:
        return False
    # status="all" で取得し、こちらで active_statuses に含まれるか判定する
    subs = stripe_module.Subscription.list(customer=customer_id, status="all", limit=100)
    for sub in subs.auto_paging_iter():
        if sub.get("status") in active_statuses:
            return True
    return False


def resolve_paid_subscribers(subscribers: list[Subscriber], cfg: Config) -> PaidResolution:
    """購読者リストから配信対象（支払い済み）を解決する。"""
    paid: list[Subscriber] = []
    unpaid: list[Subscriber] = []
    inactive: list[Subscriber] = []
    errors: list[tuple[Subscriber, str]] = []

    # 配信OFF を先に除外
    active_subs: list[Subscriber] = []
    for s in subscribers:
        if not s.active:
            inactive.append(s)
        else:
            active_subs.append(s)

    if not cfg.require_stripe_paid:
        # CSV/Sheets の paid 列だけで判定
        for s in active_subs:
            (paid if s.paid else unpaid).append(s)
        logger.info(
            "支払い判定(CSVモード): 対象=%d 未払い=%d 配信OFF=%d",
            len(paid), len(unpaid), len(inactive),
        )
        return PaidResolution(paid=paid, unpaid=unpaid, inactive=inactive, errors=errors)

    # --- Stripe ライブ照会モード ---
    try:
        import stripe as stripe_module
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("stripe パッケージが必要です。`pip install stripe`") from exc

    if not cfg.has_stripe():
        raise RuntimeError("REQUIRE_STRIPE_PAID=true ですが STRIPE_API_KEY が未設定です。")

    stripe_module.api_key = cfg.stripe_api_key

    for s in active_subs:
        if not s.stripe_customer_id:
            unpaid.append(s)
            logger.info("stripe_customer_id 未設定のため未払い扱い: %s", s.line_user_id)
            continue
        try:
            if _check_stripe_active(stripe_module, s.stripe_customer_id, cfg.stripe_active_statuses):
                paid.append(s)
            else:
                unpaid.append(s)
        except Exception as exc:  # noqa: BLE001  Stripe例外は安全側で握る
            # 障害時は安全側（配信対象外）に倒し、ログに残す
            errors.append((s, str(exc)))
            logger.error(
                "Stripe照会に失敗したため配信対象外にします: cust=%s line=%s err=%s",
                s.stripe_customer_id, s.line_user_id, exc,
            )

    logger.info(
        "支払い判定(Stripeモード): 対象=%d 未払い=%d 配信OFF=%d 照会エラー=%d",
        len(paid), len(unpaid), len(inactive), len(errors),
    )
    return PaidResolution(paid=paid, unpaid=unpaid, inactive=inactive, errors=errors)
