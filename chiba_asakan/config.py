"""環境変数・パスの一元管理。

.env から設定を読み込み、アプリ全体で使う `Config` を提供する。
秘密情報（各種APIキー）はここ以外で直接 os.getenv しないようにする。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# プロジェクトルート（このファイルの 1 つ上の階層）
BASE_DIR = Path(__file__).resolve().parent.parent

# .env を読み込む（既に環境変数がある場合はそちらを優先しない＝上書きしない）
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _get_json_dict(name: str) -> dict[str, str]:
    raw = os.getenv(name)
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError:
        pass
    return {}


# 既定で有効にするソース
DEFAULT_SOURCES = ["prtimes", "prefecture", "city", "tourism", "commerce"]


@dataclass(frozen=True)
class Config:
    # --- 秘密情報 ---
    line_channel_access_token: str
    line_channel_secret: str       # Webhook 署名検証用（任意）
    stripe_api_key: str
    anthropic_api_key: str

    # --- AI ---
    ai_model: str

    # --- Stripe ---
    require_stripe_paid: bool
    stripe_active_statuses: list[str]

    # --- 購読者ソース ---
    subscriber_source: str  # "csv" | "google_sheets"
    subscriber_csv_path: Path
    google_sheets_id: str
    google_sheets_worksheet: str
    google_service_account_json: Path

    # --- ネタ収集・採点・原稿 ---
    enabled_sources: list[str]
    source_feed_overrides: dict[str, str]
    score_threshold: int            # 原稿候補にする合計点のしきい値（既定20）
    scoring_mode: str               # "heuristic" | "ai"
    draft_length_default: int       # 自動生成の既定文字数
    exclude_keywords_extra: list[str]

    # --- テスト配信 ---
    line_test_user_id: str          # 「テスト配信」で自分に送るときの LINE userId

    # --- その他 ---
    timezone: str

    # --- ディレクトリ（自動生成） ---
    data_dir: Path = field(default=BASE_DIR / "data")
    # 原稿（下書き〜承認済み）の保存先。1日1ファイル data/drafts/<日付>.json
    manuscript_dir: Path = field(default=BASE_DIR / "data" / "drafts")
    delivery_log_dir: Path = field(default=BASE_DIR / "data" / "delivery_logs")
    source_item_dir: Path = field(default=BASE_DIR / "data" / "source_items")
    log_dir: Path = field(default=BASE_DIR / "logs")

    # ---- 便利メソッド -------------------------------------------------
    def has_line(self) -> bool:
        return bool(self.line_channel_access_token)

    def has_stripe(self) -> bool:
        return bool(self.stripe_api_key)

    def has_ai(self) -> bool:
        return bool(self.anthropic_api_key)

    def ensure_dirs(self) -> None:
        for d in (
            self.data_dir,
            self.manuscript_dir,
            self.delivery_log_dir,
            self.source_item_dir,
            self.log_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def missing_for_delivery(self) -> list[str]:
        """配信に最低限必要な設定のうち欠けているものを返す。"""
        missing: list[str] = []
        if not self.has_line():
            missing.append("LINE_CHANNEL_ACCESS_TOKEN")
        if self.require_stripe_paid and not self.has_stripe():
            missing.append("STRIPE_API_KEY (REQUIRE_STRIPE_PAID=true のため必須)")
        if self.subscriber_source == "csv" and not self.subscriber_csv_path.exists():
            missing.append(f"購読者CSV ({self.subscriber_csv_path})")
        if self.subscriber_source == "google_sheets" and not self.google_sheets_id:
            missing.append("GOOGLE_SHEETS_ID")
        return missing


def _resolve_path(raw: str | None, default: Path) -> Path:
    if not raw:
        return default
    p = Path(raw)
    return p if p.is_absolute() else (BASE_DIR / p)


def load_config() -> Config:
    """環境変数から Config を生成する。"""
    cfg = Config(
        line_channel_access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip(),
        line_channel_secret=os.getenv("LINE_CHANNEL_SECRET", "").strip(),
        stripe_api_key=os.getenv("STRIPE_API_KEY", "").strip(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        ai_model=os.getenv("AI_MODEL", "claude-opus-4-8").strip() or "claude-opus-4-8",
        require_stripe_paid=_get_bool("REQUIRE_STRIPE_PAID", default=False),
        stripe_active_statuses=_get_list("STRIPE_ACTIVE_STATUSES", ["active", "trialing"]),
        subscriber_source=(os.getenv("SUBSCRIBER_SOURCE", "csv").strip().lower() or "csv"),
        subscriber_csv_path=_resolve_path(
            os.getenv("SUBSCRIBER_CSV_PATH"), BASE_DIR / "data" / "subscribers.csv"
        ),
        google_sheets_id=os.getenv("GOOGLE_SHEETS_ID", "").strip(),
        google_sheets_worksheet=os.getenv("GOOGLE_SHEETS_WORKSHEET", "subscribers").strip(),
        google_service_account_json=_resolve_path(
            os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"), BASE_DIR / "google_service_account.json"
        ),
        enabled_sources=_get_list("ENABLED_SOURCES", DEFAULT_SOURCES),
        source_feed_overrides=_get_json_dict("SOURCE_FEED_OVERRIDES"),
        score_threshold=_get_int("SCORE_THRESHOLD", 20),
        scoring_mode=(os.getenv("SCORING_MODE", "heuristic").strip().lower() or "heuristic"),
        draft_length_default=_get_int("DRAFT_LENGTH_DEFAULT", 1000),
        exclude_keywords_extra=_get_list("EXCLUDE_KEYWORDS_EXTRA", []),
        line_test_user_id=os.getenv("LINE_TEST_USER_ID", "").strip(),
        timezone=os.getenv("TIMEZONE", "Asia/Tokyo").strip() or "Asia/Tokyo",
    )
    cfg.ensure_dirs()
    return cfg
