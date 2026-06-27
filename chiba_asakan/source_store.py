"""ネタ（収集・採点・除外結果）の保存・読込。

data/source_items/<YYYY-MM-DD>.json に、その日に収集したネタを保存する。
保存項目（要件）:
  id / date / source_name / title / url / published_at / summary /
  area / category / score / score_reason / excluded / exclude_reason / used_in_draft
  （加えて 6 項目のスコア内訳・除外マッチ語も保存）
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .exclusion import ExclusionResult
from .logging_config import get_logger
from .scoring import ScoreResult
from .sources.source_base import SourceItem

logger = get_logger("source_store")


@dataclass
class SourceRecord:
    id: str
    date: str
    source_name: str
    title: str
    url: str
    published_at: str
    summary: str
    area: str
    category: str
    score: int = 0
    score_reason: str = ""
    score_breakdown: dict = field(default_factory=dict)
    excluded: bool = False
    exclude_reason: str = ""
    exclude_matched: list[str] = field(default_factory=list)
    used_in_draft: bool = False

    @classmethod
    def build(
        cls,
        item: SourceItem,
        date_str: str,
        score: ScoreResult,
        exclusion: ExclusionResult,
    ) -> "SourceRecord":
        return cls(
            id=item.item_id(),
            date=date_str,
            source_name=item.source_name,
            title=item.title,
            url=item.url,
            published_at=item.published_at,
            summary=item.summary,
            area=item.area,
            category=item.category,
            score=score.total,
            score_reason=score.reason,
            score_breakdown={
                "chiba_relevance": score.chiba_relevance,
                "sales_useful": score.sales_useful,
                "young_appeal": score.young_appeal,
                "freshness": score.freshness,
                "smalltalk": score.smalltalk,
                "proposal": score.proposal,
            },
            excluded=exclusion.excluded,
            exclude_reason=exclusion.reason,
            exclude_matched=exclusion.matched,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SourceRecord":
        return cls(
            id=d["id"],
            date=d["date"],
            source_name=d.get("source_name", ""),
            title=d.get("title", ""),
            url=d.get("url", ""),
            published_at=d.get("published_at", ""),
            summary=d.get("summary", ""),
            area=d.get("area", ""),
            category=d.get("category", ""),
            score=int(d.get("score", 0)),
            score_reason=d.get("score_reason", ""),
            score_breakdown=d.get("score_breakdown", {}),
            excluded=bool(d.get("excluded", False)),
            exclude_reason=d.get("exclude_reason", ""),
            exclude_matched=d.get("exclude_matched", []),
            used_in_draft=bool(d.get("used_in_draft", False)),
        )


class SourceItemStore:
    def __init__(self, source_item_dir: Path) -> None:
        self.dir = source_item_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, date_str: str) -> Path:
        return self.dir / f"{date_str}.json"

    def save_records(self, date_str: str, records: list[SourceRecord]) -> Path:
        path = self._path(date_str)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
        logger.info("ネタを保存: %s (%d件)", path.name, len(records))
        return path

    def load_records(self, date_str: str) -> list[SourceRecord]:
        path = self._path(date_str)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [SourceRecord.from_dict(d) for d in data]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("ネタの読込に失敗: %s (%s)", path.name, exc)
            return []

    def list_dates(self, descending: bool = True) -> list[str]:
        return sorted((p.stem for p in self.dir.glob("*.json")), reverse=descending)

    def merge_records(self, date_str: str, records: list[SourceRecord]) -> list[SourceRecord]:
        """既存の同日ネタとマージ（重複IDは used_in_draft を引き継いで上書き）。"""
        existing = {r.id: r for r in self.load_records(date_str)}
        for rec in records:
            if rec.id in existing:
                rec.used_in_draft = existing[rec.id].used_in_draft
            existing[rec.id] = rec
        merged = sorted(existing.values(), key=lambda r: r.score, reverse=True)
        self.save_records(date_str, merged)
        return merged

    def set_used(self, date_str: str, item_ids: set[str], used: bool = True) -> None:
        """指定IDの used_in_draft を更新して保存する。"""
        records = self.load_records(date_str)
        for r in records:
            if r.id in item_ids:
                r.used_in_draft = used
        self.save_records(date_str, records)

    def candidates(self, date_str: str, threshold: int) -> list[SourceRecord]:
        """原稿候補（除外されておらず score>=threshold）を高得点順で返す。"""
        records = self.load_records(date_str)
        cands = [r for r in records if not r.excluded and r.score >= threshold]
        return sorted(cands, key=lambda r: r.score, reverse=True)
