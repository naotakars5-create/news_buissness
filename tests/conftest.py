"""pytest 共通フィクスチャ。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# プロジェクトルートを import パスへ
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chiba_asakan.config import Config  # noqa: E402


def make_cfg(tmp_path: Path, **overrides) -> Config:
    """テスト用 Config を一時ディレクトリで作る。"""
    base = dict(
        line_channel_access_token="dummy-line-token",
        line_channel_secret="",
        stripe_api_key="",
        anthropic_api_key="test-ai-key",
        ai_model="claude-opus-4-8",
        require_stripe_paid=False,
        stripe_active_statuses=["active", "trialing"],
        subscriber_source="csv",
        subscriber_csv_path=tmp_path / "subscribers.csv",
        google_sheets_id="",
        google_sheets_worksheet="subscribers",
        google_service_account_json=tmp_path / "sa.json",
        enabled_sources=["prtimes"],
        source_feed_overrides={},
        score_threshold=20,
        scoring_mode="heuristic",
        draft_length_default=1000,
        exclude_keywords_extra=[],
        line_test_user_id="",
        timezone="Asia/Tokyo",
        data_dir=tmp_path,
        manuscript_dir=tmp_path / "manuscripts",
        delivery_log_dir=tmp_path / "delivery_logs",
        source_item_dir=tmp_path / "source_items",
        log_dir=tmp_path / "logs",
    )
    base.update(overrides)
    cfg = Config(**base)
    cfg.ensure_dirs()
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return make_cfg(tmp_path)


@pytest.fixture
def sample_rss() -> str:
    """千葉ネタ1件 + 都内ネタ1件 + 入札ネタ1件 を含む RSS2.0 フィード。"""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>テストフィード</title>
    <item>
      <title>幕張新都心に新商業施設がオープン</title>
      <link>https://example.com/chiba-mall</link>
      <description>千葉・幕張で大型ショッピングモールがリニューアルオープン。週末はイベントも。</description>
      <pubDate>Wed, 24 Jun 2026 09:00:00 +0900</pubDate>
    </item>
    <item>
      <title>渋谷の新オフィスビル竣工</title>
      <link>https://example.com/tokyo-office</link>
      <description>東京・渋谷で新しいオフィスビルが完成した。</description>
      <pubDate>Wed, 24 Jun 2026 08:00:00 +0900</pubDate>
    </item>
    <item>
      <title>千葉県 道路維持工事の一般競争入札を公告</title>
      <link>https://example.com/chiba-bid</link>
      <description>千葉県は道路維持工事の入札を公告した。仕様書は電子調達システムで配布。</description>
      <pubDate>Wed, 24 Jun 2026 07:00:00 +0900</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def fixed_fetcher(sample_rss):
    """どのURLでも同じフィクスチャRSSを返す fetcher。"""
    def _fetch(url: str) -> str:
        return sample_rss
    return _fetch
