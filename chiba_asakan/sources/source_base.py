"""ソースの基底クラスと、依存ライブラリ不要のフィードパーサ。

設計方針（テスト容易性）:
  - ネットワーク取得（fetch）と解析（parse）を分離する。
  - fetch はコールバック（Fetcher）として注入できるので、テストでは
    ローカルのフィクスチャ文字列を渡せる。
  - RSS2.0 / RSS1.0(RDF) / Atom を標準ライブラリ(xml.etree)だけで解析する。
"""
from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
import xml.etree.ElementTree as ET

from ..logging_config import get_logger

logger = get_logger("sources")

# URL を渡すと本文（XML/HTML文字列）を返す関数
Fetcher = Callable[[str], str]

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
SUMMARY_MAX = 220


# ---------------------------------------------------------------------------
# データモデル
# ---------------------------------------------------------------------------
@dataclass
class SourceItem:
    title: str
    url: str
    source_name: str
    published_at: str = ""          # YYYY-MM-DD（不明なら空）
    summary: str = ""               # 短い概要のみ（本文転載はしない）
    area: str = "千葉県"
    category: str = "general"
    raw_text: str | None = None     # 任意（社内処理用。配信文には使わない）

    def item_id(self) -> str:
        """URL をもとにした安定IDを返す。"""
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "id": self.item_id(),
            "title": self.title,
            "url": self.url,
            "source_name": self.source_name,
            "published_at": self.published_at,
            "summary": self.summary,
            "area": self.area,
            "category": self.category,
            "raw_text": self.raw_text,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SourceItem":
        return cls(
            title=d.get("title", ""),
            url=d.get("url", ""),
            source_name=d.get("source_name", ""),
            published_at=d.get("published_at", ""),
            summary=d.get("summary", ""),
            area=d.get("area", "千葉県"),
            category=d.get("category", "general"),
            raw_text=d.get("raw_text"),
        )


# ---------------------------------------------------------------------------
# 取得（ネットワーク）
# ---------------------------------------------------------------------------
def default_fetcher(url: str, timeout: float = 10.0) -> str:
    """URL から本文テキストを取得する（既定の取得処理）。"""
    import requests

    headers = {"User-Agent": "chiba-asakan/1.0 (+https://example.com)"}
    resp = requests.get(url, timeout=timeout, headers=headers)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


# ---------------------------------------------------------------------------
# フィード解析（RSS/Atom/RDF, 標準ライブラリのみ）
# ---------------------------------------------------------------------------
def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(elem, names: tuple[str, ...]) -> str:
    for child in elem:
        if _localname(child.tag) in names:
            return (child.text or "").strip()
    return ""


def _extract_link(elem) -> str:
    # Atom: <link href="..."/> / RSS: <link>...text...</link>
    fallback = ""
    for child in elem:
        if _localname(child.tag) == "link":
            href = child.attrib.get("href")
            if href:
                return href.strip()
            if child.text and child.text.strip():
                fallback = child.text.strip()
        if _localname(child.tag) == "guid" and not fallback:
            if child.text and child.text.strip().startswith("http"):
                fallback = child.text.strip()
    return fallback


def clean_summary(raw: str, limit: int = SUMMARY_MAX) -> str:
    """HTMLタグを除去し、空白を整理して短く切り詰める。"""
    if not raw:
        return ""
    text = _TAG_RE.sub("", raw)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def parse_date(raw: str) -> str:
    """pubDate / dc:date / Atom date を YYYY-MM-DD に正規化する。"""
    if not raw:
        return ""
    raw = raw.strip()
    # RFC822 (Tue, 24 Jun 2026 09:00:00 +0900)
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt.astimezone().date().isoformat()
    except (TypeError, ValueError):
        pass
    # ISO8601 (2026-06-24T09:00:00+09:00 / ...Z)
    iso = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().date().isoformat()
    except ValueError:
        pass
    # 末尾が日付っぽい場合だけ拾う
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return datetime(y, mo, d).date().isoformat()
        except ValueError:
            return ""
    return ""


def parse_feed_xml(
    raw: str,
    *,
    source_name: str,
    area: str = "千葉県",
    category: str = "general",
) -> list[SourceItem]:
    """RSS/Atom/RDF 文字列を SourceItem のリストに変換する。"""
    if not raw or not raw.strip():
        return []
    try:
        root = ET.fromstring(raw.strip())
    except ET.ParseError as exc:
        logger.warning("フィード解析に失敗 (%s): %s", source_name, exc)
        return []

    entries = [e for e in root.iter() if _localname(e.tag) in ("item", "entry")]
    items: list[SourceItem] = []
    for e in entries:
        title = _child_text(e, ("title",))
        url = _extract_link(e)
        if not title or not url:
            continue
        summary = clean_summary(
            _child_text(e, ("description", "summary", "encoded", "content", "subtitle"))
        )
        published = parse_date(
            _child_text(e, ("pubdate", "date", "published", "updated", "issued"))
        )
        items.append(
            SourceItem(
                title=title.strip(),
                url=url.strip(),
                source_name=source_name,
                published_at=published,
                summary=summary,
                area=area,
                category=category,
            )
        )
    return items


# ---------------------------------------------------------------------------
# 基底クラス
# ---------------------------------------------------------------------------
class BaseSource:
    """全ソースの基底。`collect()` を実装する。"""

    key: str = "base"
    name: str = "base"
    area: str = "千葉県"
    category: str = "general"

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        self.fetcher: Fetcher = fetcher or default_fetcher

    def collect(self) -> list[SourceItem]:  # pragma: no cover - 抽象
        raise NotImplementedError


class FeedSource(BaseSource):
    """RSS/Atom フィードを取得・解析する汎用ソース。

    サブクラスは `feed_urls`（と任意で `keyword_filter`）を設定するだけでよい。
    """

    feed_urls: list[str] = []
    keyword_filter: list[str] = []  # 設定時、いずれかを含む項目だけ残す

    def _match_keyword(self, item: SourceItem) -> bool:
        if not self.keyword_filter:
            return True
        haystack = f"{item.title} {item.summary}"
        return any(kw in haystack for kw in self.keyword_filter)

    def collect(self) -> list[SourceItem]:
        results: list[SourceItem] = []
        seen: set[str] = set()
        for url in self.feed_urls:
            if not url:
                continue
            try:
                raw = self.fetcher(url)
            except Exception as exc:  # noqa: BLE001  個別ソースの失敗で全体を止めない
                logger.warning("フィード取得に失敗 (%s / %s): %s", self.name, url, exc)
                continue
            for item in parse_feed_xml(
                raw, source_name=self.name, area=self.area, category=self.category
            ):
                if item.url in seen:
                    continue
                if not self._match_keyword(item):
                    continue
                seen.add(item.url)
                results.append(item)
        logger.info("%s: %d 件取得", self.name, len(results))
        return results
