"""ネタ収集モジュール。

各情報ソース（PR TIMES / 千葉県報道発表 / 主要市の新着 / 観光 / 商業）から
営業マン向けの「ネタ」を取得する。取得するのは
  title / url / source_name / published_at / summary / area / category / raw_text(任意)
のみ。記事本文の転載はしない（著作権配慮）。
"""

from .source_base import BaseSource, FeedSource, SourceItem, default_fetcher, parse_feed_xml
from .source_manager import SourceManager

__all__ = [
    "BaseSource",
    "FeedSource",
    "SourceItem",
    "SourceManager",
    "default_fetcher",
    "parse_feed_xml",
]
