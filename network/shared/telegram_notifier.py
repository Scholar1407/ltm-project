"""
Telegram Alert Notifier Extension for Smoke Alert Protocol (SAP)
Provides non-blocking, asynchronous alerts via Telegram Bot API.
Does not affect core UDP SAP networking or require third-party packages.
"""

import json
import logging
import os
import sys
import threading
import urllib.parse
import urllib.request
from typing import Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logger = logging.getLogger("telegram_notifier")

# Default credentials provided for extension
DEFAULT_BOT_TOKEN = "9055001520:AAE5Ocx_wQFlwASQlLiXPP3f07U2pqARN3A"
DEFAULT_CHAT_ID = "6847438161"


class TelegramNotifier:
    """
    Lightweight Telegram Bot notifier using standard library urllib.
    Dispatches alerts in non-blocking daemon threads to guarantee zero
    latency overhead on core UDP transmission.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: bool = True,
    ):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", DEFAULT_BOT_TOKEN)
        self.chat_id = str(chat_id or os.getenv("TELEGRAM_CHAT_ID", DEFAULT_CHAT_ID))
        self.enabled = enabled and bool(self.bot_token and self.chat_id)
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    def send_alert_async(self, message: str, image_bytes: Optional[bytes] = None):
        """Dispatches notification on a background daemon thread."""
        if not self.enabled:
            return
        thread = threading.Thread(
            target=self.send_alert,
            args=(message, image_bytes),
            daemon=True,
            name="TelegramNotifyThread",
        )
        thread.start()

    def send_alert(self, message: str, image_bytes: Optional[bytes] = None) -> bool:
        """Sends text message or photo alert via Telegram Bot API."""
        if not self.enabled:
            return False

        try:
            if image_bytes:
                boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
                body = []
                
                # chat_id field
                body.append(f"--{boundary}".encode("utf-8"))
                body.append(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{self.chat_id}'.encode("utf-8"))
                
                # caption field
                body.append(f"--{boundary}".encode("utf-8"))
                body.append(f'Content-Disposition: form-data; name="caption"\r\n\r\n{message}'.encode("utf-8"))
                
                # photo field
                body.append(f"--{boundary}".encode("utf-8"))
                body.append(
                    b'Content-Disposition: form-data; name="photo"; filename="smoke_alert.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
                    + image_bytes
                )
                body.append(f"--{boundary}--\r\n".encode("utf-8"))

                req_data = b"\r\n".join(body)
                req = urllib.request.Request(
                    f"{self.api_url}/sendPhoto",
                    data=req_data,
                    headers={
                        "Content-Type": f"multipart/form-data; boundary={boundary}",
                        "User-Agent": "SmokeAlertBot/1.0",
                    },
                )
            else:
                payload = json.dumps({"chat_id": self.chat_id, "text": message}).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.api_url}/sendMessage",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "SmokeAlertBot/1.0",
                    },
                )

            with urllib.request.urlopen(req, timeout=8) as response:
                status = response.status
                return status == 200

        except Exception as e:
            # Catch all network/timeout errors silently to avoid impacting core services
            print(f"[TelegramNotifier] Warning: Failed to deliver alert to Telegram: {e}")
            return False


# Global singleton instance for clean external import
notifier = TelegramNotifier()


def send_telegram_alert(message: str, image_bytes: Optional[bytes] = None):
    """Convenience helper function to send async Telegram alerts."""
    notifier.send_alert_async(message, image_bytes)


if __name__ == "__main__":
    print("Testing TelegramNotifier connectivity...")
    test_notifier = TelegramNotifier()
    success = test_notifier.send_alert("🧪 [TEST] Kết nối thử nghiệm Telegram Bot từ Smoke Alert System!")
    print(f"Result: {'Thành công ✅' if success else 'Thất bại ❌'}")
