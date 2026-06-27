"""PR TIMES の千葉県関連リリースを取得するソース。

PR TIMES は全リリースの RDF フィードを公開している。千葉に関係する
キーワードを含むものだけを残す（企業の出店・リニューアル・採用・新サービス等）。
"""
from __future__ import annotations

from ..places import CHIBA_PLACES
from .source_base import FeedSource, Fetcher

# PR TIMES 全リリースの RDF フィード（公開フィード）
DEFAULT_FEEDS = ["https://prtimes.jp/index.rdf"]


class PrTimesSource(FeedSource):
    key = "prtimes"
    name = "PR TIMES"
    area = "千葉県"
    category = "release"
    keyword_filter = CHIBA_PLACES

    def __init__(self, feed_urls: list[str] | None = None, fetcher: Fetcher | None = None) -> None:
        super().__init__(fetcher=fetcher)
        self.feed_urls = feed_urls or list(DEFAULT_FEEDS)
