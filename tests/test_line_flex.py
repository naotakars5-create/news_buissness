"""Flex Message 生成とテキストフォールバックのテスト。"""
from __future__ import annotations

from chiba_asakan.delivery import _send_to
from chiba_asakan.line_client import LineApiError
from chiba_asakan.line_flex import DEFAULT_COLORS, build_carousel, build_flex_message, flex_alt_text
from chiba_asakan.models import Manuscript


def _m() -> Manuscript:
    return Manuscript(
        date="2026-06-24", theme="幕張の新店", chiba_topic="千葉トピック本文",
        why_sales="理由", target_audience="不動産営業", deal_usage="使い方",
        sales_talk="最近この辺り変わりましたね", rebuttal="切り返し",
        psychology_theme="社会的証明", psychology="心理本文", action="アクション",
        sources=[{"name": "PR TIMES", "url": "https://example.com/a"}],
    )


def test_build_carousel_three_cards():
    car = build_carousel(_m())
    assert car["type"] == "carousel"
    assert len(car["contents"]) == 3
    assert all(b["type"] == "bubble" for b in car["contents"])


def test_card_colors_and_source_button():
    car = build_carousel(_m())
    # ヘッダ色が 青/緑/オレンジ
    assert car["contents"][0]["header"]["backgroundColor"] == DEFAULT_COLORS["chiba"]
    assert car["contents"][1]["header"]["backgroundColor"] == DEFAULT_COLORS["talk"]
    assert car["contents"][2]["header"]["backgroundColor"] == DEFAULT_COLORS["psych"]
    # 出典ボタンに URL が入る
    footer = car["contents"][0]["footer"]["contents"][0]
    assert footer["action"]["uri"] == "https://example.com/a"


def test_style_override_color_and_bodymax():
    car = build_carousel(_m(), style={"colors": {"chiba": "#000000"}, "body_max": 3})
    assert car["contents"][0]["header"]["backgroundColor"] == "#000000"


def test_no_source_no_footer():
    m = _m()
    m.sources = []
    car = build_carousel(m)
    assert "footer" not in car["contents"][0]


def test_flex_message_and_alt():
    msg = build_flex_message(_m())
    assert msg["type"] == "flex"
    assert "ちば営業朝刊" in msg["altText"]
    assert len(flex_alt_text(_m())) <= 380


# --- _send_to のフォールバック挙動 ---
class _FakeClient:
    def __init__(self, flex_fails=False, text_fails=False):
        self.flex_fails = flex_fails
        self.text_fails = text_fails
        self.calls = []

    def push_flex(self, uid, alt, contents):
        self.calls.append("flex")
        if self.flex_fails:
            raise LineApiError("flex error", status_code=400, body="bad flex")

    def push_text(self, uid, text):
        self.calls.append("text")
        if self.text_fails:
            raise LineApiError("text error", status_code=400)


def test_send_to_flex_ok():
    c = _FakeClient()
    mode = _send_to(c, "U1", "alt", {}, "text", use_flex=True)
    assert mode == "flex"
    assert c.calls == ["flex"]


def test_send_to_text_mode():
    c = _FakeClient()
    mode = _send_to(c, "U1", "alt", {}, "text", use_flex=False)
    assert mode == "text"
    assert c.calls == ["text"]


def test_send_to_flex_fallback_to_text():
    c = _FakeClient(flex_fails=True)
    mode = _send_to(c, "U1", "alt", {}, "text", use_flex=True)
    assert mode == "flex→text"
    assert c.calls == ["flex", "text"]  # Flex失敗 → テキストにフォールバック
