"""除外フィルター（補助金・公募・入札など行政調達系を除外）。

方針:
  - 完全除外ではなく「除外フラグ＋理由」を記録し、管理画面で人が最終判断できる。
  - ハード除外キーワード … 含まれたら除外（行政調達・契約系）。
  - ソフト除外キーワード … 含まれても、イベント等の「許可キーワード」があれば残す。
  - 「イベント参加者募集」などは残せるようにする。

判定対象は title + summary（必要なら raw_text も含める）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 必ず除外（補助金・公募・入札・調達など）
HARD_EXCLUDE = [
    "補助金", "助成金", "公募", "入札", "調達", "電子調達", "仕様書",
    "プロポーザル", "募集要項", "企画提案", "落札", "委託先",
    "業務委託", "指名競争", "一般競争", "随意契約", "行政委託",
]

# 含まれていても、許可キーワードがあれば残す（文脈で良ネタになりうる）
SOFT_EXCLUDE = ["委託", "契約", "募集", "調達品"]

# ソフト除外を打ち消す許可キーワード（一般イベント・営業ネタとして有用）
ALLOW_KEYWORDS = [
    "イベント", "参加者募集", "体験", "フェア", "フェス", "マルシェ",
    "ワークショップ", "観光", "ツアー", "セミナー参加", "来場",
    "出店", "オープン", "開業", "リニューアル", "新店", "新商品",
    "キャンペーン", "コラボ", "限定", "祭り", "まつり",
]


@dataclass
class ExclusionResult:
    excluded: bool
    reason: str = ""
    matched: list[str] = field(default_factory=list)


def _contains_any(text: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if kw in text]


def evaluate_exclusion(
    text: str,
    extra_hard: list[str] | None = None,
) -> ExclusionResult:
    """テキストを評価し、除外すべきかと理由を返す。

    extra_hard: .env の EXCLUDE_KEYWORDS_EXTRA など、追加のハード除外語。
    """
    hard = HARD_EXCLUDE + (extra_hard or [])

    hard_hits = _contains_any(text, hard)
    if hard_hits:
        return ExclusionResult(
            excluded=True,
            reason="行政調達・補助/公募/入札系のため除外: " + " / ".join(hard_hits),
            matched=hard_hits,
        )

    soft_hits = _contains_any(text, SOFT_EXCLUDE)
    if soft_hits:
        allow_hits = _contains_any(text, ALLOW_KEYWORDS)
        if allow_hits:
            # ソフト除外語はあるが、許可キーワードがあるので残す（理由は記録）
            return ExclusionResult(
                excluded=False,
                reason=(
                    "ソフト除外語あり(" + " / ".join(soft_hits) + ")だが許可語(" +
                    " / ".join(allow_hits) + ")があるため残す"
                ),
                matched=soft_hits,
            )
        return ExclusionResult(
            excluded=True,
            reason="委託・契約系のため除外: " + " / ".join(soft_hits),
            matched=soft_hits,
        )

    return ExclusionResult(excluded=False, reason="", matched=[])


def evaluate_item_exclusion(item, extra_hard: list[str] | None = None) -> ExclusionResult:
    """SourceItem を評価する（title + summary + raw_text を対象）。"""
    parts = [item.title or "", item.summary or "", item.raw_text or ""]
    return evaluate_exclusion(" ".join(parts), extra_hard=extra_hard)
