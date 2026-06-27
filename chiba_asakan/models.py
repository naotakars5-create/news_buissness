"""配信原稿（Manuscript）のデータモデル。

原稿は 1 日 1 本。「営業で使える朝のインサイト」として以下の構成で作る。
  今日のテーマ
  1. 今日の千葉トピック
  2. 営業マンが見るべき理由
  3. 刺さりやすい営業・業界
  4. 商談での使い方
  5. そのまま使える営業トーク
  6. 切り返し例
  7. 今日の営業心理・行動経済学（テーマ付き）
  8. 今日のアクション
  9. 出典（ソース名: URL）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

# (フィールド名, 見出し) の並び。本文セクション（出典・テーマは別扱い）。
SECTIONS: list[tuple[str, str]] = [
    ("chiba_topic", "今日の千葉トピック"),
    ("why_sales", "営業マンが見るべき理由"),
    ("target_audience", "刺さりやすい営業・業界"),
    ("deal_usage", "商談での使い方"),
    ("sales_talk", "そのまま使える営業トーク"),
    ("rebuttal", "切り返し例"),
    ("psychology", "今日の営業心理・行動経済学"),
    ("action", "今日のアクション"),
]
SECTION_KEYS = [key for key, _ in SECTIONS]

# 営業心理・行動経済学のテーマ候補（ここから選ぶ）
PSYCHOLOGY_THEMES = [
    "損失回避", "返報性", "社会的証明", "希少性", "一貫性の原理",
    "フレーミング効果", "アンカリング", "単純接触効果", "権威性", "ハロー効果",
    "ピークエンドの法則", "現状維持バイアス", "選択肢過多", "初頭効果", "親近効果",
]

# 文字量プリセット（テキスト全体で 900〜1400 字）
LENGTH_PRESETS = [900, 1100, 1400]

_WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

# ステータス
STATUS_DRAFT = "draft"        # 下書き（未承認 → 自動配信されない）
STATUS_APPROVED = "approved"  # 承認済み（自動配信の対象になる）
STATUS_SENT = "sent"          # 配信完了


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def format_date_slash(d: date) -> str:
    return f"{d.year}/{d.month:02d}/{d.day:02d}"


def format_date_ja(d: date) -> str:
    return f"{format_date_slash(d)}({_WEEKDAYS_JA[d.weekday()]})"


def quote_talk(talk: str) -> str:
    """営業トークを「」で囲む（既に囲ってあればそのまま）。"""
    t = (talk or "").strip()
    if t and not t.startswith("「"):
        t = f"「{t}」"
    return t


@dataclass
class Manuscript:
    """1 日分の配信原稿。"""

    date: str  # YYYY-MM-DD
    theme: str = ""                 # 今日のテーマ
    chiba_topic: str = ""           # 今日の千葉トピック
    why_sales: str = ""             # 営業マンが見るべき理由
    target_audience: str = ""       # 刺さりやすい営業・業界（誰に刺さるか）
    deal_usage: str = ""            # 商談での使い方
    sales_talk: str = ""            # そのまま使える営業トーク
    rebuttal: str = ""              # 切り返し例
    psychology_theme: str = ""      # 心理テーマ（PSYCHOLOGY_THEMES から）
    psychology: str = ""            # 今日の営業心理 本文
    action: str = ""                # 今日のアクション
    sources: list[dict] = field(default_factory=list)  # [{"name":.., "url":..}]
    status: str = STATUS_DRAFT
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    last_delivery: dict | None = None

    # ---- バリデーション ----------------------------------------------
    def is_complete(self) -> bool:
        """テーマ + 心理テーマ + 各セクションに本文があるか。"""
        if not self.theme.strip() or not self.psychology_theme.strip():
            return False
        return all(getattr(self, key).strip() for key in SECTION_KEYS)

    def missing_sections(self) -> list[str]:
        missing: list[str] = []
        if not self.theme.strip():
            missing.append("今日のテーマ")
        for key, heading in SECTIONS:
            if not getattr(self, key).strip():
                missing.append(heading)
        if not self.psychology_theme.strip():
            missing.append("営業心理テーマ")
        return missing

    def char_count(self) -> int:
        return sum(len(getattr(self, key)) for key in SECTION_KEYS) + len(self.theme)

    def has_sources(self) -> bool:
        return any(s.get("url") for s in self.sources)

    def first_source_url(self) -> str:
        for s in self.sources:
            if s.get("url"):
                return s["url"]
        return ""

    @property
    def date_obj(self) -> date:
        return datetime.strptime(self.date, "%Y-%m-%d").date()

    @property
    def approved(self) -> bool:
        return self.status == STATUS_APPROVED

    # ---- LINE プレーンテキスト生成 ------------------------------------
    def to_line_text(self) -> str:
        """LINE で配信するテキスト本文（Flex非対応時のフォールバックにも使う）。"""
        parts: list[str] = [
            f"【ちば営業朝刊｜{format_date_slash(self.date_obj)}】",
            "",
            f"今日のテーマ：{self.theme.strip() or '（未設定）'}",
        ]
        for key, heading in SECTIONS:
            body = getattr(self, key).strip() or "（未入力）"
            if key == "sales_talk":
                body = quote_talk(body)
            parts += ["", f"■ {heading}"]
            if key == "psychology":
                parts.append(f"テーマ：{self.psychology_theme.strip() or '（未設定）'}")
            parts.append(body)
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
            "why_sales": self.why_sales,
            "target_audience": self.target_audience,
            "deal_usage": self.deal_usage,
            "sales_talk": self.sales_talk,
            "rebuttal": self.rebuttal,
            "psychology_theme": self.psychology_theme,
            "psychology": self.psychology,
            "action": self.action,
            "sources": self.sources,
            "status": self.status,
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
            why_sales=data.get("why_sales", ""),
            target_audience=data.get("target_audience", ""),
            # 旧モデル(sales_point/sales_usage)からの後方互換 → 商談での使い方へ
            deal_usage=data.get("deal_usage", data.get("sales_point", data.get("sales_usage", ""))),
            sales_talk=data.get("sales_talk", ""),
            rebuttal=data.get("rebuttal", ""),
            psychology_theme=data.get("psychology_theme", ""),
            psychology=data.get("psychology", ""),
            action=data.get("action", ""),
            sources=data.get("sources", []),
            status=data.get("status", STATUS_DRAFT),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            last_delivery=data.get("last_delivery"),
        )

    def touch(self) -> None:
        self.updated_at = _now_iso()
