"""ネタ保存（SourceRecord/SourceItemStore）のテスト。出典URL保存の確認を含む。"""
from __future__ import annotations

from chiba_asakan.exclusion import ExclusionResult
from chiba_asakan.scoring import ScoreResult
from chiba_asakan.source_store import SourceItemStore, SourceRecord
from chiba_asakan.sources.source_base import SourceItem


def _record(url, title="幕張オープン", score=24, excluded=False):
    item = SourceItem(
        title=title, url=url, source_name="PR TIMES",
        published_at="2026-06-24", summary="千葉・幕張で新店オープン",
        area="千葉県", category="release",
    )
    sr = ScoreResult(chiba_relevance=5, sales_useful=4, young_appeal=4,
                     freshness=5, smalltalk=4, proposal=2, reason="千葉:幕張")
    sr.compute_total()
    sr.total = score
    ex = ExclusionResult(excluded=excluded, reason="入札" if excluded else "", matched=["入札"] if excluded else [])
    return SourceRecord.build(item, "2026-06-24", sr, ex)


def test_save_load_preserves_url_and_fields(tmp_path):
    store = SourceItemStore(tmp_path / "src")
    rec = _record("https://example.com/a")
    store.save_records("2026-06-24", [rec])
    loaded = store.load_records("2026-06-24")
    assert len(loaded) == 1
    # 出典URLが保存されている
    assert loaded[0].url == "https://example.com/a"
    assert loaded[0].score == 24
    assert loaded[0].excluded is False


def test_candidates_filters_excluded_and_threshold(tmp_path):
    store = SourceItemStore(tmp_path / "src")
    recs = [
        _record("https://e.com/keep", score=24, excluded=False),
        _record("https://e.com/low", score=10, excluded=False),
        _record("https://e.com/excluded", score=30, excluded=True),
    ]
    store.save_records("2026-06-24", recs)
    cands = store.candidates("2026-06-24", threshold=20)
    urls = {c.url for c in cands}
    assert urls == {"https://e.com/keep"}


def test_set_used_and_merge_keeps_used_flag(tmp_path):
    store = SourceItemStore(tmp_path / "src")
    rec = _record("https://e.com/a")
    store.save_records("2026-06-24", [rec])
    store.set_used("2026-06-24", {rec.id}, used=True)
    # 再収集（マージ）しても used_in_draft が引き継がれる
    store.merge_records("2026-06-24", [_record("https://e.com/a")])
    loaded = store.load_records("2026-06-24")
    assert loaded[0].used_in_draft is True
