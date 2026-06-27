"""配信原稿（Manuscript）のデータモデル。

原稿は 1 日 1 本。以下の 5 セクション + テーマ + 出典で構成される。
  今日のテーマ
  1. 今日の千葉ネタ
  2. 営業マンが見るべきポイント
  3. 今日の営業心理・行動経済学（テーマ付き）
  4. そのまま使える営業トーク
  5. 今日のアクション
  出典（ソース名: URL）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

# (フィールド名, 見出し) の並び。本文 5 セクション。
SECTIONS: list[tuple[str, str]] = [
    ("chiba_topic", "今日の千葉ネタ"),
    ("sales_point", "営業マンが見るべきポイント"),
    ("psychology", "今日の営業心理"),
    ("sales_talk", "そのまま使える営業トーク"),
    ("action", "今日のアクション"),
]
SECTION_KEYS = [key for key, _ in SECTIONS]

# 営業心理・行動経済学のテーマ候補（ここから選ぶ）
PSYCHOLOGY_THEMES = [
    "損失回避", "返報性", "社会的証明", "希少性", "一貫性の原理",
    "フレーミング効果", "アンカリング", "単純接触効果", "権威性", "ハロー効果",
    "ピークエンドの法則", "現状維持バイアス", "選択肢過多", "初頭効果", "親近効果",
]

# 文字量プリセット
LENGTH_PRESETS = [800, 1000, 1200]

_WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

# ステータス
STATUS_DRAFT = "draft"        # 下書き（未承認 → 自動配信されない）
STATUS_APPROVED = "approved"  # 承認済み（自動配信の対象になる）
STATUS_SENT = "sent"          # 配信完了


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def format_date_slash(d: date) -> str:
    """2026/06/25 形式。"""
    return f"{d.year}/{d.month:02d}/{d.day:02d}"


def format_date_ja(d: date) -> str:
    """2026/06/25(木) 形式。"""
    return f"{format_date_slash(d)}({_WEEKDAYS_JA[d.weekday()]})"


@dataclass
class Manuscript:
    """1 日分の配信原稿。"""

    date: str  # YYYY-MM-DD
    theme: str = ""                 # 今日のテーマ
    chiba_topic: str = ""           # 今日の千葉ネタ
    sales_point: str = ""           # 営業マンが見るべきポイント
    psychology_theme: str = ""      # 心理テーマ（PSYCHOLOGY_THEMES から）
    psychology: str = ""            # 今日の営業心理 本文
    sales_talk: str = ""            # そのまま使える営業トーク
    action: str = ""                # 今日のアクション
    sources: list[dict] = field(default_factory=list)  # [{"name":.., "url":..}]
    status: str = STATUS_DRAFT
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    last_delivery: dict | None = None

    # ---- バリデーション ----------------------------------------------
    def is_complete(self) -> bool:
        """テーマ + 5 セクションすべてに本文があるか。"""
        if not self.theme.strip():
            return False
        return all(getattr(self, key).strip() for key in SECTION_KEYS)

    def missing_sections(self) -> list[str]:
        missing: list[str] = []
        if not self.theme.strip():
            missing.append("今日のテーマ")
        for key, heading in SECTIONS:
            if not getattr(self, key).strip():
                missing.append(heading)
        return missing

    def char_count(self) -> int:
        """本文の合計文字数（出典・見出しを除く目安）。"""
        return sum(len(getattr(self, key)) for key in SECTION_KEYS) + len(self.theme)

    def has_sources(self) -> bool:
        return any(s.get("url") for s in self.sources)

    @property
    def date_obj(self) -> date:
        return datetime.strptime(self.date, "%Y-%m-%d").date()

    @property
    def approved(self) -> bool:
        """承認済みかどうか（status == approved）。"""
        return self.status == STATUS_APPROVED

    # ---- LINE メッセージ生成 ------------------------------------------
    def to_line_text(self) -> str:
        """LINE で配信するテキスト本文を組み立てる（指定フォーマット）。"""
        talk = self.sales_talk.strip()
        if talk and not talk.startswith("「"):
            talk = f"「{talk}」"

        parts: list[str] = [
            f"【ちば営業朝刊｜{format_date_slash(self.date_obj)}】",
            "",
            f"今日のテーマ：{self.theme.strip() or '（未設定）'}",
            "",
            "■ 今日の千葉ネタ",
            self.chiba_topic.strip() or "（未入力）",
            "",
            "■ 営業マンが見るべきポイント",
            self.sales_point.strip() or "（未入力）",
            "",
            "■ 今日の営業心理",
            f"テーマ：{self.psychology_theme.strip() or '（未設定）'}",
            self.psychology.strip() or "（未入力）",
            "",
            "■ そのまま使える営業トーク",
            talk or "（未入力）",
            "",
            "■ 今日のアクション",
            self.action.strip() or "（未入力）",
        ]
        if self.has_sources():
            parts += ["", "■ 出典"]
            for s in self.sources:
                url = (s.get("url") or "").strip()
                if not url:
                    continue
                name = (s.get("name") or "出典").strip()
                parts.append(f"・{name}：{url}")
        return "\n".join(parts)

    # ---- 直列化 -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "theme": self.theme,
            "chiba_topic": self.chiba_topic,
            "sales_point": self.sales_point,
            "psychology_theme": self.psychology_theme,
            "psychology": self.psychology,
            "sales_talk": self.sales_talk,
            "action": self.action,
            "sources": self.sources,
            "status": self.status,
            # 承認済みフラグ（status から導出。配信側は status を正とする）
            "approved": self.approved,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_delivery": self.last_delivery,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Manuscript":
        return cls(
            date=data["date"],
            theme=data.get("theme", ""),
            chiba_topic=data.get("chiba_topic", ""),
            # 旧モデル(sales_usage)からの後方互換
            sales_point=data.get("sales_point", data.get("sales_usage", "")),
            psychology_theme=data.get("psychology_theme", ""),
            psychology=data.get("psychology", ""),
            sales_talk=data.get("sales_talk", ""),
            action=data.get("action", ""),
            sources=data.get("sources", []),
            status=data.get("status", STATUS_DRAFT),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            last_delivery=data.get("last_delivery"),
        )

    def touch(self) -> None:
        self.updated_at = _now_iso()
