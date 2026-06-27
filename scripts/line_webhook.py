"""LINE Webhook 受信用の簡易サーバ（LINE_TEST_USER_ID 取得補助）。

自分が LINE 公式アカウントにメッセージを送る／友だち追加すると、
受信イベントから userId を取り出してログ＆コンソールに大きく表示する。
取得した userId を `.env` の LINE_TEST_USER_ID に貼り付ければ「テスト配信」が使える。

依存は標準ライブラリのみ（http.server）。LINE_CHANNEL_SECRET があれば署名検証する。

使い方:
  1) .env に LINE_CHANNEL_ACCESS_TOKEN（と任意で LINE_CHANNEL_SECRET）を設定
  2) python -m scripts.line_webhook            # 既定 0.0.0.0:8000 /callback で待受
  3) ngrok 等で公開し、LINE Developers の Webhook URL に設定
  4) 自分のLINEから公式アカウントにメッセージ送信 → コンソールに userId が出る
  5) Ctrl+C で停止

オプション:
  --port 8000    待受ポート（既定: 環境変数 LINE_WEBHOOK_PORT または 8000）
  --path /callback  受信パス（既定: 環境変数 LINE_WEBHOOK_PATH または /callback）
  --host 0.0.0.0
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chiba_asakan.config import load_config  # noqa: E402
from chiba_asakan.logging_config import get_logger, setup_logging  # noqa: E402

cfg = load_config()
setup_logging(cfg.log_dir)
logger = get_logger("line_webhook")


def _verify_signature(body: bytes, signature: str) -> bool:
    """X-Line-Signature を channel secret で検証する。"""
    if not cfg.line_channel_secret:
        return True  # secret 未設定なら検証スキップ（取得目的のため許容）
    mac = hmac.new(cfg.line_channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")


def _show_user_id(user_id: str, extra: str = "") -> None:
    """userId をコンソールに目立つ形で表示し、ログにも残す。"""
    banner = (
        "\n================ LINE userId 取得 ================\n"
        f"  userId : {user_id}\n"
        + (f"  内容   : {extra}\n" if extra else "")
        + "  → .env に貼り付け:\n"
        f"     LINE_TEST_USER_ID={user_id}\n"
        "=================================================\n"
    )
    print(banner, flush=True)
    logger.info("LINE userId を受信: %s %s", user_id, extra)


def _handle_events(payload: dict) -> None:
    events = payload.get("events", [])
    if not events:
        logger.info("検証リクエスト（events空）を受信しました。Webhookは到達しています。")
        return
    for ev in events:
        source = ev.get("source", {}) or {}
        user_id = source.get("userId", "")
        ev_type = ev.get("type", "")
        extra = ""
        if ev_type == "message":
            msg = ev.get("message", {}) or {}
            if msg.get("type") == "text":
                extra = f"message: {msg.get('text', '')}"
            else:
                extra = f"message: ({msg.get('type')})"
        elif ev_type:
            extra = f"event: {ev_type}"
        if user_id:
            _show_user_id(user_id, extra)
        else:
            logger.info("userId を含まないイベント: type=%s (グループ/ルーム等の可能性)", ev_type)


class _Handler(BaseHTTPRequestHandler):
    server_version = "chiba-asakan-webhook/1.0"
    webhook_path = "/callback"

    def _ok(self, body: bytes = b"OK") -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 ヘルスチェック用
        self._ok("ちば営業朝刊 LINE webhook は起動しています。".encode("utf-8"))

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != self.webhook_path.rstrip("/"):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        signature = self.headers.get("X-Line-Signature", "")

        if not _verify_signature(body, signature):
            logger.warning("署名検証に失敗しました（X-Line-Signature 不一致）。リクエストを無視します。")
            self.send_response(400)
            self.end_headers()
            return

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
            _handle_events(payload)
        except json.JSONDecodeError:
            logger.warning("JSONの解析に失敗しました。")

        # LINE には常に 200 を返す
        self._ok()

    def log_message(self, fmt: str, *args) -> None:  # アクセスログを抑制
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LINE Webhook 受信（userId取得補助）")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("LINE_WEBHOOK_PORT", "8000"))
    )
    parser.add_argument(
        "--path", default=os.getenv("LINE_WEBHOOK_PATH", "/callback")
    )
    args = parser.parse_args(argv)

    _Handler.webhook_path = args.path

    if not cfg.line_channel_secret:
        logger.warning(
            "LINE_CHANNEL_SECRET が未設定です。署名検証はスキップします"
            "（userId取得目的なら問題ありません）。"
        )

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    logger.info(
        "Webhook待受開始: http://%s:%d%s （Ctrl+Cで停止）",
        args.host, args.port, args.path,
    )
    print(
        f"\n受信待機中… 公開URL（例 ngrok の https://xxxx ）+ `{args.path}` を\n"
        "LINE Developers の Webhook URL に設定し、公式アカウントにメッセージを送ってください。\n",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("停止します。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
