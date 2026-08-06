"""Slack/Teams 알림 (선택)"""
import requests
from .config import settings


def notify(message: str) -> None:
    for url in [settings.SLACK_WEBHOOK_URL, settings.TEAMS_WEBHOOK_URL]:
        if not url:
            continue
        try:
            requests.post(url, json={"text": message}, timeout=10)
        except Exception:
            pass  # 알림 실패는 무시
