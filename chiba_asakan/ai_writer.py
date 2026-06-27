"""AI（Claude / Anthropic）による原稿生成。

収集したネタ（SourceRecord）から、千葉の営業マン向けの濃い原稿（5セクション）を
生成する。生成物は「たたき台」。管理画面で人が確認・編集・承認してから配信する。

著作権配慮:
  - 渡すのは title / summary / url / area / category のみ（本文転載はしない）。
  - 出典URLは AI の出力からではなく、選んだネタのURLをそのまま付与する（正確性担保）。
  - 補助金・公募・入札系は扱わないよう明示する（収集側でも除外済み）。
"""
from __future__ import annotations

import json
from datetime import date

from .config import Config
from .logging_config import get_logger
from .models import (
    LENGTH_PRESETS,
    PSYCHOLOGY_THEMES,
    Manuscript,
    format_date_slash,
)

logger = get_logger("ai_writer")

# 生成テキストのスキーマ（出典は別途プログラムで付与）
_SCHEMA = {
    "type": "object",
    "properties": {
        "theme": {"type": "string", "description": "今日のテーマ（短いキャッチ）"},
        "chiba_topic": {"type": "string", "description": "今日の千葉ネタ（独自の言葉で要約・解説）"},
        "sales_point": {"type": "string", "description": "営業マンが見るべきポイント"},
        "psychology_theme": {
            "type": "string",
            "enum": PSYCHOLOGY_THEMES,
            "description": "営業心理・行動経済学のテーマ",
        },
        "psychology": {"type": "string", "description": "上のテーマの分かりやすい説明と営業での使い方"},
        "sales_talk": {"type": "string", "description": "そのまま使える営業トーク（一言・セリフ）"},
        "action": {"type": "string", "description": "今日のアクション（今日すぐやれる具体行動）"},
    },
    "required": ["theme", "chiba_topic", "sales_point", "psychology_theme",
                 "psychology", "sales_talk", "action"],
    "additionalProperties": False,
}

_SYSTEM = (
    "あなたは『ちば営業朝刊』の編集者です。読者は千葉県内で働く20〜30代の営業マン全般"
    "（保険・不動産・人材・金融・車・住宅・IT・メーカー・商社・法人・ルート・新人・飛び込み等）。"
    "広告営業など特定業種に偏らないでください。\n"
    "コンセプト: 『毎朝3分、今日の商談で使える地元ネタ・営業心理・トーク例が届く』。\n"
    "方針:\n"
    "- 単なるニュース要約ではなく、千葉の情報を“営業で使える形”に変換する。\n"
    "- 文体は20〜30代が読みやすく、固すぎず、でもビジネスで使える信頼感がある。\n"
    "- 難しい理論はかみ砕く。『明日使える』ではなく『今日使える』実用感を重視。\n"
    "- 記事本文を転載しない。固有名詞や数字は与えられた範囲で、断定しすぎない。\n"
    "- 補助金・助成金・公募・入札・調達・委託・プロポーザル等の行政調達ネタは扱わない。\n"
    "- 営業トークは、そのまま声に出せる自然な一言にする。"
)


def _format_items(items: list) -> str:
    """SourceRecord（または dict）一覧をプロンプト用テキストに整形。"""
    lines: list[str] = []
    for i, it in enumerate(items, start=1):
        title = getattr(it, "title", None) or it.get("title", "")
        summary = getattr(it, "summary", None) or it.get("summary", "")
        area = getattr(it, "area", None) or it.get("area", "")
        category = getattr(it, "category", None) or it.get("category", "")
        url = getattr(it, "url", None) or it.get("url", "")
        lines.append(
            f"[{i}] タイトル: {title}\n    概要: {summary}\n"
            f"    エリア: {area} / カテゴリ: {category}\n    URL: {url}"
        )
    return "\n".join(lines) if lines else "（ネタなし。千葉の一般的な季節・地域の話題で構成してください）"


def _sources_from_items(items: list) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    for it in items:
        name = getattr(it, "source_name", None) or (it.get("source_name") if isinstance(it, dict) else "") or "出典"
        url = getattr(it, "url", None) or (it.get("url") if isinstance(it, dict) else "")
        if url and url not in seen:
            seen.add(url)
            sources.append({"name": name, "url": url})
    return sources


def _build_prompt(
    target_date: date,
    items: list,
    psychology_theme: str | None,
    target_length: int,
) -> str:
    lines = [
        f"配信日: {format_date_slash(target_date)}",
        f"目標文字数: 本文合計で約{target_length}字（短すぎず、有料LINEとして満足感のある濃さ）。",
        "",
        "今日のネタ候補:",
        _format_items(items),
        "",
        "上記をもとに、次のセクションを作ってください。",
        "- theme: 今日のテーマ（今日の千葉ネタを一言で）",
        "- chiba_topic: 今日の千葉ネタ（独自の言葉で要約・解説。本文転載しない）",
        "- sales_point: 営業マンが見るべきポイント（このネタが商談でどう効くか）",
        "- psychology_theme / psychology: 今日の営業心理（理論名＋かみ砕いた説明＋営業での使い方）",
        "- sales_talk: そのまま使える営業トーク（自然な一言）",
        "- action: 今日のアクション（今日すぐやれる具体行動）",
    ]
    if psychology_theme:
        lines.append(f"※ 営業心理のテーマは必ず「{psychology_theme}」にしてください。")
    else:
        lines.append("※ 営業心理のテーマは候補から今日のネタに合うものを選んでください。")
    return "\n".join(lines)


def generate_manuscript_dict(
    cfg: Config,
    target_date: date,
    items: list,
    psychology_theme: str | None = None,
    target_length: int | None = None,
) -> dict:
    """Claude で原稿(dict)を生成して返す（出典は items から付与）。"""
    if not cfg.has_ai():
        raise RuntimeError("ANTHROPIC_API_KEY が未設定のため AI 生成は利用できません。")

    import anthropic

    target_length = target_length or cfg.draft_length_default
    if target_length not in LENGTH_PRESETS:
        target_length = min(LENGTH_PRESETS, key=lambda x: abs(x - target_length))

    prompt = _build_prompt(target_date, items, psychology_theme, target_length)
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)

    logger.info(
        "AI原稿生成: model=%s date=%s ネタ=%d件 文字数=%d",
        cfg.ai_model, target_date.isoformat(), len(items), target_length,
    )

    try:
        resp = client.messages.create(
            model=cfg.ai_model,
            max_tokens=4000,
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("構造化出力に失敗。フォールバックで再生成します: %s", exc)
        data = _generate_fallback(client, cfg, prompt)

    keys = ["theme", "chiba_topic", "sales_point", "psychology_theme",
            "psychology", "sales_talk", "action"]
    result = {k: str(data.get(k, "")).strip() for k in keys}
    if psychology_theme:
        result["psychology_theme"] = psychology_theme
    result["sources"] = _sources_from_items(items)
    return result


def generate_manuscript(
    cfg: Config,
    target_date: date,
    items: list,
    psychology_theme: str | None = None,
    target_length: int | None = None,
    status: str = "draft",
) -> Manuscript:
    """Manuscript オブジェクトを生成して返す。"""
    data = generate_manuscript_dict(cfg, target_date, items, psychology_theme, target_length)
    m = Manuscript(date=target_date.isoformat())
    m.theme = data["theme"]
    m.chiba_topic = data["chiba_topic"]
    m.sales_point = data["sales_point"]
    m.psychology_theme = data["psychology_theme"]
    m.psychology = data["psychology"]
    m.sales_talk = data["sales_talk"]
    m.action = data["action"]
    m.sources = data["sources"]
    m.status = status
    return m


def _generate_fallback(client, cfg: Config, prompt: str) -> dict:
    """構造化出力が使えない場合に、JSONで返すよう指示して手動パースする。"""
    keys = ["theme", "chiba_topic", "sales_point", "psychology_theme",
            "psychology", "sales_talk", "action"]
    instruction = (
        prompt
        + "\n\n営業心理テーマは次から選ぶこと: " + ", ".join(PSYCHOLOGY_THEMES)
        + "\n必ず次のキーだけを持つJSONのみを返す（前後の説明なし）: " + json.dumps(keys, ensure_ascii=False)
    )
    resp = client.messages.create(
        model=cfg.ai_model,
        max_tokens=4000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": instruction}],
    )
    text = next(b.text for b in resp.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)
