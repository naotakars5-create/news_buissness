"""観光・イベント情報ソース（ちば観光ナビ等）。

週末イベント・観光・スポーツなど、雑談ネタになりやすい情報源。
フィードURLは要確認のため既定は空。SOURCE_FEED_OVERRIDES で `"tourism"` を指定する。
"""
from __future__ import annotations

from .source_base import FeedSource, Fetcher

DEFAULT_FEEDS: list[str] = []


class TourismSource(FeedSource):
    key = "tourism"
    name = "ちば観光・イベント"
    area = "千葉県"
    category = "tourism"

    def __init__(self, feed_urls: list[str] | None = None, fetcher: Fetcher | None = None) -> None:
        super().__init__(fetcher=fetcher)
        self.feed_urls = feed_urls or list(DEFAULT_FEEDS)
