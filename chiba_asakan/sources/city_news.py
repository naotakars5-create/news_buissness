"""主要市（千葉市・船橋市・市川市・松戸市・柏市・成田市など）の新着情報ソース。

各市のフィードURLは要確認のため、既定では空にしている。
`.env` の SOURCE_FEED_OVERRIDES で市ごとに指定すると有効化される。
  例: SOURCE_FEED_OVERRIDES='{"city:千葉市":"https://www.city.chiba.jp/.../rss.xml",
                              "city:船橋市":"https://www.city.funabashi.lg.jp/.../rss.xml"}'
"""
from __future__ import annotations

from ..places import MAJOR_CITIES
from .source_base import FeedSource, Fetcher


class CityNewsSource(FeedSource):
    """1 市ぶんの新着情報フィード。"""

    category = "city"

    def __init__(
        self,
        city: str,
        feed_urls: list[str],
        fetcher: Fetcher | None = None,
    ) -> None:
        super().__init__(fetcher=fetcher)
        self.key = f"city:{city}"
        self.name = f"{city} 新着情報"
        self.area = city
        self.feed_urls = list(feed_urls)


def build_city_sources(
    overrides: dict[str, str],
    fetcher: Fetcher | None = None,
    cities: list[str] | None = None,
) -> list[CityNewsSource]:
    """overrides（{"city:千葉市": url, ...}）から市ソースを構築する。

    URL が指定された市だけを有効化する（未指定の市はスキップ）。
    """
    cities = cities or MAJOR_CITIES
    sources: list[CityNewsSource] = []
    for city in cities:
        url = overrides.get(f"city:{city}")
        if url:
            sources.append(CityNewsSource(city=city, feed_urls=[url], fetcher=fetcher))
    return sources
