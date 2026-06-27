"""配信対象ユーザー（購読者）の管理。

CSV または Google Sheets から購読者を読み込む。
列:
  line_user_id        … LINE のユーザーID（必須・Uから始まる33文字）
  name                … 表示名（任意）
  stripe_customer_id  … Stripe の顧客ID（任意・cus_...）
  paid                … 支払い済みフラグ（true/false）。CSV運用時の手動判定に使う
  active              … 配信ON/OFF（退会・一時停止に使う。false なら対象外）
  note                … 備考（任意）
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .logging_config import get_logger

logger = get_logger("subscribers")

_TRUE_SET = {"1", "true", "yes", "on", "y", "はい", "○"}


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    v = str(value).strip().lower()
    if v == "":
        return default
    return v in _TRUE_SET


@dataclass
class Subscriber:
    line_user_id: str
    name: str = ""
    stripe_customer_id: str = ""
    paid: bool = False        # CSV/Sheets 上の支払い済みフラグ
    active: bool = True       # 配信ON/OFF
    note: str = ""

    def is_valid(self) -> bool:
        return bool(self.line_user_id) and self.line_user_id.startswith("U")


def _row_to_subscriber(row: dict[str, str]) -> Subscriber:
    # 余分な空白・BOM 対策でキーを正規化
    norm = { (k or "").strip().lstrip("﻿").lower(): (v or "").strip() for k, v in row.items() }
    return Subscriber(
        line_user_id=norm.get("line_user_id", ""),
        name=norm.get("name", ""),
        stripe_customer_id=norm.get("stripe_customer_id", ""),
        paid=_to_bool(norm.get("paid"), default=False),
        active=_to_bool(norm.get("active"), default=True),
        note=norm.get("note", ""),
    )


def load_from_csv(path: Path) -> list[Subscriber]:
    if not path.exists():
        logger.warning("購読者CSVが見つかりません: %s", path)
        return []
    subscribers: list[Subscriber] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # 2 行目から（1行目はヘッダ）
            sub = _row_to_subscriber(row)
            if not sub.is_valid():
                logger.warning("無効な購読者行をスキップ (行%d): line_user_id=%r", i, sub.line_user_id)
                continue
            subscribers.append(sub)
    logger.info("CSVから購読者を %d 件読み込みました: %s", len(subscribers), path.name)
    return subscribers


def load_from_google_sheets(cfg: Config) -> list[Subscriber]:
    """Google Sheets から購読者を読み込む。

    gspread + サービスアカウントを使用。スプレッドシートは
    サービスアカウントのメールアドレスに共有しておくこと。
    """
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Google Sheets を使うには gspread と google-auth が必要です。"
            "`pip install gspread google-auth`"
        ) from exc

    if not cfg.google_service_account_json.exists():
        raise FileNotFoundError(
            f"サービスアカウントJSONが見つかりません: {cfg.google_service_account_json}"
        )

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(
        str(cfg.google_service_account_json), scopes=scopes
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(cfg.google_sheets_id)
    worksheet = sheet.worksheet(cfg.google_sheets_worksheet)
    rows = worksheet.get_all_records()  # ヘッダを使った dict のリスト

    subscribers: list[Subscriber] = []
    for i, row in enumerate(rows, start=2):
        sub = _row_to_subscriber({str(k): str(v) for k, v in row.items()})
        if not sub.is_valid():
            logger.warning("無効な購読者行をスキップ (行%d)", i)
            continue
        subscribers.append(sub)
    logger.info("Google Sheetsから購読者を %d 件読み込みました", len(subscribers))
    return subscribers


def load_subscribers(cfg: Config) -> list[Subscriber]:
    """設定に応じて CSV か Google Sheets から購読者を読み込む。"""
    if cfg.subscriber_source == "google_sheets":
        return load_from_google_sheets(cfg)
    return load_from_csv(cfg.subscriber_csv_path)
