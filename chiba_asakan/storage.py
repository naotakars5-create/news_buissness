"""配信原稿の保存・読込（JSON ファイル）。

MVP ではデータベースを使わず、1 日 1 ファイル（YYYY-MM-DD.json）で管理する。
将来 DB に差し替えやすいよう、ここにアクセスを閉じ込める。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .logging_config import get_logger
from .models import Manuscript

logger = get_logger("storage")


class ManuscriptStore:
    def __init__(self, manuscript_dir: Path) -> None:
        self.dir = manuscript_dir
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, date_str: str) -> Path:
        return self.dir / f"{date_str}.json"

    def exists(self, date_str: str) -> bool:
        return self._path(date_str).exists()

    def save(self, manuscript: Manuscript) -> Path:
        manuscript.touch()
        path = self._path(manuscript.date)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(manuscript.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)  # 原子的に置き換え（書き込み途中の破損を防ぐ）
        logger.info("原稿を保存しました: %s (status=%s)", path.name, manuscript.status)
        return path

    def load(self, date_str: str) -> Manuscript | None:
        path = self._path(date_str)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Manuscript.from_dict(data)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("原稿の読込に失敗: %s (%s)", path.name, exc)
            return None

    def get_or_create(self, date_str: str) -> Manuscript:
        existing = self.load(date_str)
        if existing is not None:
            return existing
        return Manuscript(date=date_str)

    def list_dates(self, descending: bool = True) -> list[str]:
        """保存済み原稿の日付一覧（YYYY-MM-DD）を返す。"""
        dates = sorted(
            (p.stem for p in self.dir.glob("*.json")),
            reverse=descending,
        )
        return dates

    def list_manuscripts(self, descending: bool = True) -> list[Manuscript]:
        result: list[Manuscript] = []
        for d in self.list_dates(descending=descending):
            m = self.load(d)
            if m is not None:
                result.append(m)
        return result

    def delete(self, date_str: str) -> bool:
        path = self._path(date_str)
        if path.exists():
            path.unlink()
            logger.info("原稿を削除しました: %s", path.name)
            return True
        return False
