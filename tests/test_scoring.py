"""スコアリングのテスト。"""
from __future__ import annotations

from datetime import date

from chiba_asakan.scoring import score_item_heuristic
from chiba_asakan.sources.source_base import SourceItem

TODAY = date(2026, 6, 24)


def _item(title, summary, area="千葉県", published="2026-06-24"):
    return SourceItem(
        title=title, url="https://e.com/x", source_name="t",
        published_at=published, summary=summary, area=area, category="release",
    )


def test_strong_chiba_business_item_is_candidate():
    item = _item(
        "幕張に新店舗オープン、週末はイベントも",
        "船橋・柏の企業が新サービスを発表。採用も拡大し、法人向けに展開。人気で行列。",
    )
    result = score_item_heuristic(item, today=TODAY)
    assert result.total == (
        result.chiba_relevance + result.sales_useful + result.young_appeal
        + result.freshness + result.smalltalk + result.proposal
    )
    assert result.total >= 20, result.reason
    assert result.reason  # 理由が入る


def test_trivial_non_chiba_item_low_score():
    item = _item(
        "天気はおおむね晴れ",
        "全国的に穏やかな一日になるでしょう。",
        area="全国",
        published="2026-06-10",  # 2週間前 → 新しさ低
    )
    result = score_item_heuristic(item, today=TODAY)
    assert result.total < 20


def test_freshness_today_is_max():
    item = _item("千葉ネタ", "オープン", published="2026-06-24")
    assert score_item_heuristic(item, today=TODAY).freshness == 5


def test_scores_within_range():
    item = _item("幕張 出店 採用 イベント 人気 法人 DX", "千葉 船橋 柏 オープン リニューアル")
    r = score_item_heuristic(item, today=TODAY)
    for v in [r.chiba_relevance, r.sales_useful, r.young_appeal,
              r.freshness, r.smalltalk, r.proposal]:
        assert 0 <= v <= 5
