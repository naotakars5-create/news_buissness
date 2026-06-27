"""配信ロジックのテスト（承認済みのみ配信される安全設計の確認）。"""
from __future__ import annotations

from chiba_asakan.delivery import (
    TEST_MESSAGE,
    deliver,
    send_line_test,
    should_deliver,
)
from chiba_asakan.models import STATUS_APPROVED, STATUS_DRAFT, Manuscript
from chiba_asakan.subscribers import Subscriber

from .conftest import make_cfg


def _complete_manuscript(status=STATUS_DRAFT) -> Manuscript:
    return Manuscript(
        date="2026-06-24",
        theme="幕張の新店オープン",
        chiba_topic="本文",
        why_sales="本文",
        target_audience="不動産・住宅営業",
        deal_usage="本文",
        sales_talk="一言",
        rebuttal="本文",
        psychology_theme="社会的証明",
        psychology="本文",
        action="本文",
        sources=[{"name": "PR TIMES", "url": "https://example.com/a"}],
        status=status,
    )


def test_should_deliver_approved_complete():
    ok, reason = should_deliver(_complete_manuscript(STATUS_APPROVED))
    assert ok is True
    assert reason == ""


def test_should_deliver_draft_is_blocked():
    ok, reason = should_deliver(_complete_manuscript(STATUS_DRAFT))
    assert ok is False
    assert "承認" in reason


def test_should_deliver_none():
    ok, reason = should_deliver(None)
    assert ok is False


def test_should_deliver_incomplete_blocked_even_if_approved():
    m = _complete_manuscript(STATUS_APPROVED)
    m.chiba_topic = ""  # 未入力にする
    ok, reason = should_deliver(m)
    assert ok is False
    assert "未入力" in reason


def test_force_skips_approval_but_not_completeness():
    draft = _complete_manuscript(STATUS_DRAFT)
    ok, _ = should_deliver(draft, force=True)
    assert ok is True  # force で承認チェックはスキップ
    draft.action = ""
    ok2, _ = should_deliver(draft, force=True)
    assert ok2 is False  # ただし本文不備は force でも配信しない


def test_send_line_test_success_fixed_message(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path, line_test_user_id="U" + "9" * 32)
    sent = []

    class _FakeClient:
        def __init__(self, token):
            self.token = token

        def push_text(self, uid, text):
            sent.append((uid, text))

    monkeypatch.setattr("chiba_asakan.delivery.LineClient", _FakeClient)
    ok, err = send_line_test(cfg)
    assert ok is True and err == ""
    assert len(sent) == 1
    assert sent[0][0] == "U" + "9" * 32
    assert sent[0][1] == TEST_MESSAGE  # 指定の固定メッセージ


def test_send_line_test_manual_text(tmp_path, monkeypatch):
    cfg = make_cfg(tmp_path, line_test_user_id="U" + "9" * 32)
    sent = []
    monkeypatch.setattr(
        "chiba_asakan.delivery.LineClient",
        type("_FC", (), {"__init__": lambda self, t: None,
                         "push_text": lambda self, uid, text: sent.append(text)}),
    )
    ok, _ = send_line_test(cfg, text="手動メッセージ")
    assert ok is True
    assert sent == ["手動メッセージ"]


def test_send_line_test_no_token_fails_and_logs(tmp_path):
    cfg = make_cfg(tmp_path, line_channel_access_token="", line_test_user_id="U" + "9" * 32)
    ok, err = send_line_test(cfg)
    assert ok is False
    assert "LINE_CHANNEL_ACCESS_TOKEN" in err
    # 失敗が logs/line_test.log に記録される
    log_file = cfg.log_dir / "line_test.log"
    assert log_file.exists()
    assert "FAILED" in log_file.read_text(encoding="utf-8")


def test_send_line_test_no_userid_fails(tmp_path):
    cfg = make_cfg(tmp_path, line_test_user_id="")
    ok, err = send_line_test(cfg)
    assert ok is False
    assert "LINE_TEST_USER_ID" in err


def test_deliver_dry_run_targets_paid_only(cfg):
    subs = [
        Subscriber(line_user_id="U" + "1" * 32, name="paid", paid=True, active=True),
        Subscriber(line_user_id="U" + "2" * 32, name="unpaid", paid=False, active=True),
        Subscriber(line_user_id="U" + "3" * 32, name="off", paid=True, active=False),
    ]
    result = deliver(cfg, _complete_manuscript(STATUS_APPROVED), dry_run=True, subscribers=subs)
    assert result.target_count == 1
    assert result.sent_count == 1
    assert result.skipped_unpaid == 1
    assert result.skipped_inactive == 1
    assert result.failed_count == 0


def test_deliver_skip_payment_check_includes_active_unpaid(cfg):
    # 自分宛て配信など: 支払い判定をスキップし active 全員を対象にする
    subs = [
        Subscriber(line_user_id="U" + "1" * 32, name="unpaid-active", paid=False, active=True),
        Subscriber(line_user_id="U" + "2" * 32, name="paid-off", paid=True, active=False),
    ]
    result = deliver(
        cfg, _complete_manuscript(STATUS_APPROVED),
        dry_run=True, subscribers=subs, skip_payment_check=True,
    )
    assert result.target_count == 1        # active な未払いも対象
    assert result.skipped_inactive == 1    # 配信OFFは除外
    assert result.skipped_unpaid == 0


def test_manuscript_json_has_approved_flag():
    assert _complete_manuscript(STATUS_APPROVED).to_dict()["approved"] is True
    assert _complete_manuscript(STATUS_DRAFT).to_dict()["approved"] is False
