"""ソース取得・フィード解析・PR TIMESキーワードフィルタのテスト。"""
from __future__ import annotations

from chiba_asakan.sources.prtimes import PrTimesSource
from chiba_asakan.sources.source_base import FeedSource, parse_feed_xml


def test_parse_feed_xml_required_fields(sample_rss):
    items = parse_feed_xml(sample_rss, source_name="テスト")
    assert len(items) == 3
    it = items[0]
    # 必須項目が取得できている
    assert it.title and it.url and it.source_name
    assert it.url == "https://example.com/chiba-mall"
    assert it.published_at == "2026-06-24"
    assert "幕張" in it.title
    assert it.summary  # 短い概要が入る
    assert len(it.summary) <= 230  # 本文転載ではなく短い概要


def test_feedsource_uses_injected_fetcher(fixed_fetcher):
    class _S(FeedSource):
        name = "テストソース"
        feed_urls = ["https://example.com/feed"]

    items = _S(fetcher=fixed_fetcher).collect()
    assert len(items) == 3
    assert all(i.source_name == "テストソース" for i in items)


def test_prtimes_keyword_filter_keeps_only_chiba(fixed_fetcher):
    # PR TIMES は千葉キーワードを含むものだけ残す（都内ネタは除外）
    items = PrTimesSource(fetcher=fixed_fetcher).collect()
    urls = {i.url for i in items}
    assert "https://example.com/chiba-mall" in urls      # 千葉ネタは残る
    assert "https://example.com/tokyo-office" not in urls # 都内のみは残らない
    # 入札ネタは「千葉県」を含むのでこの時点では残る（除外は exclusion 側で行う）
    assert "https://example.com/chiba-bid" in urls


def test_published_at_iso_parsing():
    rss = """<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>ISO日付</title><link>https://e.com/a</link>
      <pubDate>2026-06-24T09:00:00+09:00</pubDate></item></channel></rss>"""
    items = parse_feed_xml(rss, source_name="x")
    assert items[0].published_at == "2026-06-24"
