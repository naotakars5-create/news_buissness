"""千葉県の報道発表・新着情報を取得するソース。

千葉県公式サイトの RSS/Atom フィードを取得する。
フィードURLは自治体側の都合で変わることがあるため、既定値は持たせず
`.env` の SOURCE_FEED_OVERRIDES で `"prefecture"` を指定して有効化する。
（未設定なら空リストを返すだけで、他ソースには影響しない）
"""
from __future__ import annotations

from .source_base import FeedSource, Fetcher

# 既定フィードは持たない（自治体フィードURLは要確認のため）。
# 例: SOURCE_FEED_OVERRIDES='{"prefecture":"https://www.pref.chiba.lg.jp/.../rss.xml"}'
DEFAULT_FEEDS: list[str] = []


class PrefectureSource(FeedSource):
    key = "prefecture"
    name = "千葉県報道発表"
    area = "千葉県"
    category = "prefecture"

    def __init__(self, feed_urls: list[str] | None = None, fetcher: Fetcher | None = None) -> None:
        super().__init__(fetcher=fetcher)
        self.feed_urls = feed_urls or list(DEFAULT_FEEDS)
