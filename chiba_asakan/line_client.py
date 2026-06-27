"""LINE Messaging API クライアント（push 送信）。

公式SDKを使わず requests で直接 push API を呼ぶ。
個別配信のため push（/v2/bot/message/push）を 1 ユーザーずつ送る。
"""
from __future__ import annotations

import requests

from .logging_config import get_logger

logger = get_logger("line_client")

PUSH_URL = "https://api.line.me/v2/bot/message/push"
# LINE のテキストメッセージは 5000 文字まで
MAX_TEXT_LENGTH = 5000


class LineApiError(Exception):
    """LINE API 呼び出しに失敗した場合の例外。"""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class LineClient:
    def __init__(self, channel_access_token: str, timeout: float = 10.0):
        if not channel_access_token:
            raise ValueError("LINE_CHANNEL_ACCESS_TOKEN が未設定です。")
        self._token = channel_access_token
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {channel_access_token}",
                "Content-Type": "application/json",
            }
        )

    @staticmethod
    def split_text(text: str, limit: int = MAX_TEXT_LENGTH) -> list[str]:
        """5000文字を超える場合は行単位で分割する。"""
        if len(text) <= limit:
            return [text]
        chunks: list[str] = []
        current = ""
        for line in text.split("\n"):
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > limit:
                if current:
                    chunks.append(current)
                # 1行自体が長すぎる場合は強制分割
                while len(line) > limit:
                    chunks.append(line[:limit])
                    line = line[limit:]
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def push_messages(self, user_id: str, messages: list[dict]) -> None:
        """messages 配列（最大5件）をそのまま push する。失敗時は LineApiError。"""
        if len(messages) > 5:
            logger.warning("メッセージが5件を超えたため先頭5件に切り詰めます: user=%s", user_id)
            messages = messages[:5]
        payload = {"to": user_id, "messages": messages}
        try:
            resp = self._session.post(PUSH_URL, json=payload, timeout=self._timeout)
        except requests.RequestException as exc:
            raise LineApiError(f"ネットワークエラー: {exc}") from exc
        if resp.status_code != 200:
            raise LineApiError(
                f"LINE push 失敗 (status={resp.status_code})",
                status_code=resp.status_code,
                body=resp.text,
            )

    def push_text(self, user_id: str, text: str) -> None:
        """1 ユーザーにテキストを送信する（5000字超は分割）。失敗時は LineApiError。"""
        messages = [{"type": "text", "text": chunk} for chunk in self.split_text(text)]
        self.push_messages(user_id, messages)

    def push_flex(self, user_id: str, alt_text: str, contents: dict) -> None:
        """Flex Message を1件送信する。失敗時は LineApiError。"""
        message = {"type": "flex", "altText": (alt_text or "ちば営業朝刊")[:400], "contents": contents}
        self.push_messages(user_id, [message])

    def verify_token(self) -> bool:
        """トークンが有効かどうかをかんたんに確認する（bot 情報の取得）。"""
        try:
            resp = self._session.get("https://api.line.me/v2/bot/info", timeout=self._timeout)
            return resp.status_code == 200
        except requests.RequestException:
            return False
