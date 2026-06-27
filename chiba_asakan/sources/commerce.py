"""商業・経済情報ソース（商工会議所・地元企業の動き・新店舗など）。

出店・リニューアル・採用・新サービスなど、法人営業の提案ネタになりやすい情報源。
フィードURLは要確認のため既定は空。SOURCE_FEED_OVERRIDES で `"commerce"` を指定する。
"""
from __future__ import annotations

from .source_base import FeedSource, Fetcher

DEFAULT_FEEDS: list[str] = []


class CommerceSource(FeedSource):
    key = "commerce"
    name = "千葉の商業・経済"
    area = "千葉県"
    category = "commerce"

    def __init__(self, feed_urls: list[str] | None = None, fetcher: Fetcher | None = None) -> None:
        super().__init__(fetcher=fetcher)
        self.feed_urls = feed_urls or list(DEFAULT_FEEDS)
