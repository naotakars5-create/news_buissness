"""全ソースを束ねて巡回するマネージャ。

config の enabled_sources / source_feed_overrides に従ってソースを構築し、
すべて巡回してネタ（SourceItem）を集める。1ソースの失敗で全体を止めない。
"""
from __future__ import annotations

from ..config import Config
from ..logging_config import get_logger
from .city_news import build_city_sources
from .commerce import CommerceSource
from .prefecture import PrefectureSource
from .prtimes import PrTimesSource
from .source_base import BaseSource, Fetcher, SourceItem
from .tourism import TourismSource

logger = get_logger("sources.manager")

# overrides で単一URLを指定できるソースキー → クラス
_SINGLE_FEED_SOURCES = {
    "prtimes": PrTimesSource,
    "prefecture": PrefectureSource,
    "tourism": TourismSource,
    "commerce": CommerceSource,
}


class SourceManager:
    def __init__(self, cfg: Config, fetcher: Fetcher | None = None) -> None:
        self.cfg = cfg
        self.fetcher = fetcher
        self.sources: list[BaseSource] = self._build_sources()

    def _build_sources(self) -> list[BaseSource]:
        sources: list[BaseSource] = []
        overrides = self.cfg.source_feed_overrides
        enabled = self.cfg.enabled_sources

        for key, cls in _SINGLE_FEED_SOURCES.items():
            if key not in enabled:
                continue
            override = overrides.get(key)
            feed_urls = [override] if override else None
            sources.append(cls(feed_urls=feed_urls, fetcher=self.fetcher))

        if "city" in enabled:
            sources.extend(build_city_sources(overrides, fetcher=self.fetcher))

        active = [s.name for s in sources if getattr(s, "feed_urls", None)]
        logger.info(
            "ソース構築: 有効=%d / フィード設定済み=%s",
            len(sources), ", ".join(active) or "なし",
        )
        return sources

    def collect_all(self) -> list[SourceItem]:
        """全ソースを巡回し、URL重複を除いたネタのリストを返す。"""
        all_items: list[SourceItem] = []
        seen: set[str] = set()
        for source in self.sources:
            try:
                items = source.collect()
            except Exception as exc:  # noqa: BLE001  個別ソースの失敗は握りつぶして続行
                logger.error("ソース巡回でエラー (%s): %s", source.name, exc)
                continue
            for item in items:
                if item.url in seen:
                    continue
                seen.add(item.url)
                all_items.append(item)
        logger.info("巡回完了: 合計 %d 件（重複除去後）", len(all_items))
        return all_items
