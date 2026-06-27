"""send_morning の「承認済み原稿だけ配信」動作のテスト（実送信なし）。

load_config と deliver を差し替えて、ネットワークも実ファイルの本番configも使わずに
配信可否の判定だけを検証する。
"""
from __future__ import annotations

import scripts.send_morning as sm
from chiba_asakan.delivery import DeliveryResult
from chiba_asakan.models import STATUS_APPROVED, STATUS_DRAFT, Manuscript
from chiba_asakan.storage import ManuscriptStore

from .conftest import make_cfg

DATE = "2026-06-24"
ARGS = ["--to-test-user", "--date", DATE]  # 購読者CSV不要モードで判定だけ見る


def _manuscript(status: str) -> Manuscript:
    return Manuscript(
        date=DATE, theme="t", chiba_topic="a", sales_point="a",
        psychology_theme="社会的証明", psychology="a", sales_talk="x",
        action="a", status=status,
    )


def _cfg(tmp_path):
    return make_cfg(tmp_path, line_test_user_id="U" + "9" * 32)


def test_no_manuscript_skips_and_returns_0(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(sm, "load_config", lambda: cfg)
    calls = []
    monkeypatch.setattr(sm, "deliver", lambda *a, **k: calls.append(1))
    assert sm.main(ARGS) == 0
    assert calls == []  # 承認済み原稿なし → 配信されない


def test_draft_is_not_delivered(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ManuscriptStore(cfg.manuscript_dir).save(_manuscript(STATUS_DRAFT))
    monkeypatch.setattr(sm, "load_config", lambda: cfg)
    calls = []
    monkeypatch.setattr(sm, "deliver", lambda *a, **k: calls.append(1))
    assert sm.main(ARGS) == 0
    assert calls == []  # 未承認 → 配信されない


def test_approved_is_delivered(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ManuscriptStore(cfg.manuscript_dir).save(_manuscript(STATUS_APPROVED))
    monkeypatch.setattr(sm, "load_config", lambda: cfg)
    delivered = []

    def fake_deliver(cfg_, manuscript, **kwargs):
        delivered.append(manuscript)
        return DeliveryResult(
            date=manuscript.date, started_at="", finished_at="",
            dry_run=False, target_count=1, sent_count=1, failed_count=0,
        )

    monkeypatch.setattr(sm, "deliver", fake_deliver)
    assert sm.main(ARGS) == 0
    assert len(delivered) == 1  # 承認済み → 配信される
    # 配信後に sent へ更新され保存される
    saved = ManuscriptStore(cfg.manuscript_dir).load(DATE)
    assert saved is not None and saved.last_delivery is not None
