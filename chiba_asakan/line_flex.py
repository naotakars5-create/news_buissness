"""LINE Flex Message（3枚カルーセル）生成モジュール。

原稿(Manuscript)から、視認性の高い 3 枚カードの Flex Message JSON を作る。
  カード1: 今日の千葉ネタ（青）
  カード2: 営業トーク（緑）
  カード3: 営業心理 ＋ 今日のアクション（オレンジ）
各カード: タイトル / サブタイトル / 本文 / タグ / 「出典を見る」ボタン。
テキストのみのフォールバックは Manuscript.to_line_text() を使う（delivery 側）。
"""
from __future__ import annotations

from .models import Manuscript, format_date_slash, quote_talk

# 既定デザイン（色・本文最大文字数）。Streamlit から style で上書き可能。
DEFAULT_COLORS = {"chiba": "#1E66E0", "talk": "#15A86A", "psych": "#E8821A"}
DEFAULT_TITLES = {
    "chiba": "今日の千葉トピック",
    "talk": "そのまま使える営業トーク",
    "psych": "今日の営業心理",
}
DEFAULT_BODY_MAX = 220
_WHITE = "#FFFFFF"
_WHITE_SUB = "#FFFFFFDD"
_TEXT = "#333333"


def _clip(text: str, body_max: int | None) -> str:
    t = (text or "").strip()
    if body_max and len(t) > body_max:
        return t[:body_max].rstrip() + "…"
    return t


def _label_block(label: str, color: str) -> dict:
    return {"type": "text", "text": label, "size": "xs", "weight": "bold",
            "color": color, "wrap": True, "margin": "md"}


def _body_text(text: str) -> dict:
    return {"type": "text", "text": text or "（未入力）", "size": "sm",
            "color": _TEXT, "wrap": True}


def _tag_block(text: str, color: str) -> dict:
    # 薄い背景のタグ風ボックス
    return {
        "type": "box", "layout": "vertical", "cornerRadius": "md",
        "backgroundColor": color + "1A", "paddingAll": "6px", "margin": "md",
        "contents": [{"type": "text", "text": text, "size": "xs",
                      "color": color, "weight": "bold", "wrap": True}],
    }


def _bubble(color: str, icon: str, title: str, subtitle: str,
            body_contents: list[dict], source_url: str) -> dict:
    bubble: dict = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": color,
            "paddingAll": "16px", "spacing": "xs",
            "contents": [
                {"type": "text", "text": f"{icon} {title}", "color": _WHITE,
                 "weight": "bold", "size": "lg", "wrap": True},
                {"type": "text", "text": subtitle or " ", "color": _WHITE_SUB,
                 "size": "sm", "wrap": True},
            ],
        },
        "body": {"type": "box", "layout": "vertical", "spacing": "sm",
                 "paddingAll": "16px", "contents": body_contents},
    }
    if source_url:
        bubble["footer"] = {
            "type": "box", "layout": "vertical",
            "contents": [{
                "type": "button", "style": "link", "height": "sm",
                "color": color,
                "action": {"type": "uri", "label": "📎 出典を見る", "uri": source_url},
            }],
        }
    return bubble


def build_carousel(manuscript: Manuscript, style: dict | None = None) -> dict:
    """3 枚カルーセルの contents を返す。"""
    style = style or {}
    colors = {**DEFAULT_COLORS, **(style.get("colors") or {})}
    titles = {**DEFAULT_TITLES, **(style.get("titles") or {})}
    body_max = style.get("body_max", DEFAULT_BODY_MAX)
    url = manuscript.first_source_url()
    m = manuscript

    # カード1: 千葉ネタ（青）
    c1 = colors["chiba"]
    card1 = _bubble(
        c1, "📍", titles["chiba"], _clip(m.theme, 60),
        [
            _body_text(_clip(m.chiba_topic, body_max)),
            _label_block("💡 営業マンが見るべき理由", c1),
            _body_text(_clip(m.why_sales, body_max)),
            _tag_block("🎯 刺さる: " + (_clip(m.target_audience, 60) or "営業全般"), c1),
        ],
        url,
    )

    # カード2: 営業トーク（緑）
    c2 = colors["talk"]
    card2 = _bubble(
        c2, "🗣", titles["talk"], "刺さる: " + (_clip(m.target_audience, 40) or "営業全般"),
        [
            _body_text(_clip(quote_talk(m.sales_talk), body_max)),
            _label_block("↩️ 切り返し例", c2),
            _body_text(_clip(m.rebuttal, body_max)),
            _label_block("🤝 商談での使い方", c2),
            _body_text(_clip(m.deal_usage, body_max)),
        ],
        url,
    )

    # カード3: 心理 ＋ アクション（オレンジ）
    c3 = colors["psych"]
    card3 = _bubble(
        c3, "🧠", titles["psych"], "テーマ：" + (m.psychology_theme or "—"),
        [
            _body_text(_clip(m.psychology, body_max)),
            _label_block("✅ 今日のアクション", c3),
            _body_text(_clip(m.action, body_max)),
        ],
        url,
    )

    return {"type": "carousel", "contents": [card1, card2, card3]}


def flex_alt_text(manuscript: Manuscript) -> str:
    """Flex非対応端末向けの代替テキスト（最大400字）。"""
    alt = f"【ちば営業朝刊｜{format_date_slash(manuscript.date_obj)}】{manuscript.theme}".strip()
    return alt[:380]


def build_flex_message(manuscript: Manuscript, style: dict | None = None) -> dict:
    """push 用の Flex メッセージ（1メッセージ）を返す。"""
    return {
        "type": "flex",
        "altText": flex_alt_text(manuscript),
        "contents": build_carousel(manuscript, style),
    }
