"""ネタ採点（営業マン向けに使えるかを 6 項目 × 0〜5 点で評価）。

評価項目（各 0〜5、合計 0〜30 を sales_score とする）:
  - chiba_relevance : 千葉県内性
  - sales_useful    : 営業で使える度
  - young_appeal    : 20〜30代営業マンに刺さる度
  - freshness       : 今日性・新しさ
  - smalltalk       : 雑談に使いやすい度
  - proposal        : 提案や商談につながる度

既定は heuristic（ルールベース）。決定的でテストしやすく、API費用もかからない。
SCORING_MODE=ai にすると Claude で採点する（任意・ネット必要）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .config import Config
from .logging_config import get_logger
from .places import CHIBA_PLACES
from .sources.source_base import SourceItem

logger = get_logger("scoring")

# --- 各観点のキーワード ---
BUSINESS_KW = [
    "出店", "オープン", "開業", "開店", "リニューアル", "改装", "移転", "増床",
    "新店舗", "新サービス", "新商品", "新ブランド", "上場", "本社", "工場",
    "業務提携", "資本提携", "M&A", "値上げ", "値下げ", "再開発", "設備投資",
    "DX", "実証実験", "新規事業",
]
YOUNG_KW = [
    "カフェ", "スイーツ", "グルメ", "SNS", "映え", "トレンド", "人気", "話題",
    "スポーツ", "ジェフ", "ロッテ", "マリーンズ", "ジェッツ", "推し", "限定",
    "コラボ", "新店", "ポップアップ", "サウナ", "アウトドア", "フェス",
]
SMALLTALK_KW = [
    "話題", "人気", "行列", "週末", "イベント", "祭", "まつり", "フェス",
    "グルメ", "限定", "季節", "桜", "花火", "紅葉", "観光", "ランキング",
    "オープン", "リニューアル", "新店", "ご当地",
]
PROPOSAL_KW = [
    "法人", "企業", "中小企業", "BtoB", "設備投資", "移転", "増床", "採用",
    "求人", "人手不足", "採用拡大", "DX", "効率化", "コスト", "業務提携",
    "新工場", "オフィス", "物流", "再開発", "賃料", "テナント",
]


@dataclass
class ScoreResult:
    chiba_relevance: int = 0
    sales_useful: int = 0
    young_appeal: int = 0
    freshness: int = 0
    smalltalk: int = 0
    proposal: int = 0
    total: int = 0
    reason: str = ""
    breakdown: dict = field(default_factory=dict)

    def compute_total(self) -> int:
        self.total = (
            self.chiba_relevance
            + self.sales_useful
            + self.young_appeal
            + self.freshness
            + self.smalltalk
            + self.proposal
        )
        return self.total


def _hits(text: str, keywords: list[str]) -> list[str]:
    out: list[str] = []
    for kw in keywords:
        if kw in text and kw not in out:
            out.append(kw)
    return out


def _capped(n: int, per: int = 2, cap: int = 5) -> int:
    return min(cap, n * per)


def _freshness_score(published_at: str, today: date | None = None) -> int:
    if not published_at:
        return 2  # 不明は中間
    today = today or date.today()
    try:
        d = datetime.strptime(published_at, "%Y-%m-%d").date()
    except ValueError:
        return 2
    delta = (today - d).days
    if delta <= 0:
        return 5
    if delta == 1:
        return 4
    if delta <= 3:
        return 3
    if delta <= 7:
        return 2
    return 1


def score_item_heuristic(item: SourceItem, today: date | None = None) -> ScoreResult:
    """ルールベースで 1 件を採点する。"""
    text = f"{item.title} {item.summary} {item.area}"

    chiba_hits = _hits(text, CHIBA_PLACES)
    area_is_chiba = any(p in (item.area or "") for p in ["千葉", "市"]) or bool(chiba_hits)
    chiba_relevance = min(5, (1 if area_is_chiba else 0) + len(chiba_hits) * 2)

    biz = _hits(text, BUSINESS_KW)
    young = _hits(text, YOUNG_KW)
    small = _hits(text, SMALLTALK_KW)
    prop = _hits(text, PROPOSAL_KW)

    result = ScoreResult(
        chiba_relevance=chiba_relevance,
        sales_useful=_capped(len(biz)),
        young_appeal=_capped(len(young)),
        freshness=_freshness_score(item.published_at, today),
        smalltalk=_capped(len(small)),
        proposal=_capped(len(prop)),
    )
    result.breakdown = {
        "chiba": chiba_hits[:6],
        "business": biz[:6],
        "young": young[:6],
        "smalltalk": small[:6],
        "proposal": prop[:6],
    }
    result.compute_total()

    reason_parts: list[str] = []
    if chiba_hits:
        reason_parts.append("千葉:" + ",".join(chiba_hits[:4]))
    elif area_is_chiba:
        reason_parts.append("エリア千葉")
    if biz:
        reason_parts.append("ビジネス:" + ",".join(biz[:3]))
    if young:
        reason_parts.append("若手:" + ",".join(young[:3]))
    if small:
        reason_parts.append("雑談:" + ",".join(small[:3]))
    if prop:
        reason_parts.append("提案:" + ",".join(prop[:3]))
    reason_parts.append(f"新しさ:{result.freshness}/5")
    result.reason = " / ".join(reason_parts)
    return result


# ---------------------------------------------------------------------------
# AI 採点（任意）
# ---------------------------------------------------------------------------
def score_item_ai(cfg: Config, item: SourceItem) -> ScoreResult:
    """Claude で 1 件を採点する（SCORING_MODE=ai のとき）。"""
    import json

    import anthropic

    schema = {
        "type": "object",
        "properties": {
            k: {"type": "integer", "minimum": 0, "maximum": 5}
            for k in ["chiba_relevance", "sales_useful", "young_appeal",
                      "freshness", "smalltalk", "proposal"]
        }
        | {"reason": {"type": "string"}},
        "required": ["chiba_relevance", "sales_useful", "young_appeal",
                     "freshness", "smalltalk", "proposal", "reason"],
        "additionalProperties": False,
    }
    system = (
        "あなたは『ちば営業朝刊』の編集者。千葉で働く20〜30代の営業マンが今日の商談で"
        "使えるかという観点で、各項目を0〜5で採点します。補助金・公募・入札系は0点。"
    )
    prompt = (
        f"タイトル: {item.title}\n概要: {item.summary}\nエリア: {item.area}\n"
        f"カテゴリ: {item.category}\n公開日: {item.published_at}\n"
        "各項目(0〜5)で採点し、reasonに一言で理由を書いてください。"
    )
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    resp = client.messages.create(
        model=cfg.ai_model,
        max_tokens=500,
        system=system,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)
    result = ScoreResult(
        chiba_relevance=int(data["chiba_relevance"]),
        sales_useful=int(data["sales_useful"]),
        young_appeal=int(data["young_appeal"]),
        freshness=int(data["freshness"]),
        smalltalk=int(data["smalltalk"]),
        proposal=int(data["proposal"]),
        reason=data.get("reason", ""),
    )
    result.compute_total()
    return result


def score_item(cfg: Config, item: SourceItem, today: date | None = None) -> ScoreResult:
    """設定モードに応じて 1 件を採点する。AI失敗時は heuristic にフォールバック。"""
    if cfg.scoring_mode == "ai" and cfg.has_ai():
        try:
            return score_item_ai(cfg, item)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI採点に失敗。heuristicにフォールバック: %s", exc)
    return score_item_heuristic(item, today=today)
