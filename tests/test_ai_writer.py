"""原稿生成のテスト（Anthropic SDK をフェイクに差し替えてネットワーク不要にする）。

出典URLが選んだネタから正しく付与されることも確認する。
"""
from __future__ import annotations

import json
import types
from datetime import date

import pytest

from chiba_asakan.ai_writer import generate_manuscript, generate_manuscript_dict
from chiba_asakan.sources.source_base import SourceItem

_FAKE_OUTPUT = {
    "theme": "幕張の新店オープン",
    "chiba_topic": "幕張に新しい商業施設がオープンしました。",
    "sales_point": "来店動線の変化は商談のきっかけになります。",
    "psychology_theme": "社会的証明",
    "psychology": "人は多くの人が選ぶものを選びがちです。",
    "sales_talk": "最近この辺り、人の流れ変わりましたよね",
    "action": "今日の訪問先に幕張の話題を1つ持っていく。",
}


@pytest.fixture
def fake_anthropic(monkeypatch):
    """sys.modules の anthropic をフェイクに差し替える。"""
    payload = json.dumps(_FAKE_OUTPUT, ensure_ascii=False)
    block = types.SimpleNamespace(type="text", text=payload)
    resp = types.SimpleNamespace(content=[block])

    class _Messages:
        def create(self, **kwargs):
            return resp

    class _Anthropic:
        def __init__(self, api_key=None):
            self.messages = _Messages()

    module = types.ModuleType("anthropic")
    module.Anthropic = _Anthropic
    monkeypatch.setitem(__import__("sys").modules, "anthropic", module)
    return module


def _items():
    return [
        SourceItem(title="幕張に新商業施設", url="https://example.com/chiba1",
                   source_name="PR TIMES", summary="新店オープン", area="千葉県"),
        SourceItem(title="柏で新サービス", url="https://example.com/chiba2",
                   source_name="千葉の商業・経済", summary="新サービス発表", area="柏市"),
    ]


def test_generate_manuscript_dict_has_all_sections(cfg, fake_anthropic):
    data = generate_manuscript_dict(cfg, date(2026, 6, 24), _items())
    for key in ["theme", "chiba_topic", "sales_point", "psychology_theme",
                "psychology", "sales_talk", "action", "sources"]:
        assert key in data
    assert data["theme"]


def test_sources_url_preserved(cfg, fake_anthropic):
    data = generate_manuscript_dict(cfg, date(2026, 6, 24), _items())
    urls = {s["url"] for s in data["sources"]}
    assert urls == {"https://example.com/chiba1", "https://example.com/chiba2"}
    # ソース名も保持
    names = {s["name"] for s in data["sources"]}
    assert "PR TIMES" in names


def test_psychology_theme_override(cfg, fake_anthropic):
    data = generate_manuscript_dict(cfg, date(2026, 6, 24), _items(), psychology_theme="損失回避")
    assert data["psychology_theme"] == "損失回避"


def test_generate_manuscript_object_complete_and_line_text(cfg, fake_anthropic):
    m = generate_manuscript(cfg, date(2026, 6, 24), _items())
    assert m.is_complete()
    text = m.to_line_text()
    assert "【ちば営業朝刊｜2026/06/24】" in text
    assert "■ 今日の千葉ネタ" in text
    assert "■ 出典" in text
    assert "https://example.com/chiba1" in text  # 出典URLが本文に入る
