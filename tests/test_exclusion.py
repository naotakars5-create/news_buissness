"""除外フィルターのテスト（補助金・公募・入札の除外／一般イベントの保持）。"""
from __future__ import annotations

import pytest

from chiba_asakan.exclusion import evaluate_exclusion


@pytest.mark.parametrize(
    "text",
    [
        "千葉県の中小企業向け補助金の公募開始",
        "道路維持工事の一般競争入札を公告",
        "システム調達のプロポーザル募集要項を公開",
        "業務委託先の選定に関する企画提案の受付",
        "電子調達システムで仕様書を配布",
    ],
)
def test_subsidy_bid_excluded(text):
    result = evaluate_exclusion(text)
    assert result.excluded is True
    assert result.reason  # 除外理由が記録される
    assert result.matched


@pytest.mark.parametrize(
    "text",
    [
        "夏祭りのイベント参加者募集が始まりました",
        "千葉ポートタワーで体験ワークショップの参加者募集",
        "新商業施設オープン記念フェアを開催",
    ],
)
def test_general_event_kept(text):
    result = evaluate_exclusion(text)
    assert result.excluded is False


def test_soft_exclude_without_allow_is_excluded():
    # 「委託」「契約」だけで許可語がなければ除外
    result = evaluate_exclusion("清掃業務の委託契約を締結")
    assert result.excluded is True


def test_soft_exclude_with_allow_kept_and_reason_recorded():
    # ソフト除外語があってもイベント等の許可語があれば残し、理由を記録する
    result = evaluate_exclusion("委託事業のキックオフ・イベント参加者募集")
    assert result.excluded is False
    assert "残す" in result.reason


def test_extra_hard_keyword():
    result = evaluate_exclusion("特別な案件です", extra_hard=["特別な案件"])
    assert result.excluded is True
