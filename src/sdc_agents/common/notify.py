"""Notification delivery for SDC Agents SMB pipeline events.

Sends structured notifications to configured channels (Slack webhook,
Telegram bot, email) after pipeline operations complete or fail.
All sends are logged via AuditLogger. Individual channel failures
are logged but do not raise — other channels still receive the notification.
"""

from __future__ import annotations

import asyncio
import json
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict

import httpx

from sdc_agents.common.audit import AuditLogger
from sdc_agents.common.config import NotificationConfig, SDCAgentsConfig


class Notifier:
    """Sends structured notifications to all configured channels."""

    def __init__(self, config: SDCAgentsConfig):
        self._notifications = config.notifications
        self._audit = AuditLogger(config.audit.path, config.audit.log_level)

    async def send(self, event: str, summary: str, details: dict) -> list[dict]:
        """Send notification to all configured channels.

        Args:
            event: Event identifier (e.g., "validation_batch_complete").
            summary: Human-readable one-line summary.
            details: Structured event details (agent, tool, counts, etc.).

        Returns:
            List of dicts with channel name, status ("sent" or "failed"),
            and error message if failed.
        """
        if not self._notifications:
            return []

        start = time.monotonic()
        payload = {
            "source": "sdc-agents-smb",
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "details": details,
        }

        results = []
        for name, cfg in self._notifications.items():
            try:
                if cfg.type == "slack_webhook":
                    await self._send_slack(name, cfg, payload)
                    results.append({"channel": name, "status": "sent"})
                elif cfg.type == "telegram":
                    await self._send_telegram(name, cfg, payload)
                    results.append({"channel": name, "status": "sent"})
                elif cfg.type == "email":
                    await self._send_email(name, cfg, payload)
                    results.append({"channel": name, "status": "sent"})
                else:
                    results.append({
                        "channel": name,
                        "status": "failed",
                        "error": f"Unknown notification type: {cfg.type}",
                    })
            except Exception as exc:
                results.append({
                    "channel": name,
                    "status": "failed",
                    "error": str(exc),
                })

        self._audit.log(
            agent="notifier",
            tool="send_notification",
            inputs={"event": event, "channels": list(self._notifications.keys())},
            outputs=results,
            start_time=start,
        )
        return results

    async def _send_slack(
        self, name: str, cfg: NotificationConfig, payload: dict
    ) -> None:
        """Send notification via Slack incoming webhook."""
        if not cfg.webhook_url:
            raise ValueError(f"Slack notification '{name}' missing webhook_url")

        slack_payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"SDC Agents: {payload['event']}",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": payload["summary"],
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Agent:* {payload['details'].get('agent', '?')} | "
                            f"*Tool:* {payload['details'].get('tool', '?')} | "
                            f"*Time:* {payload['timestamp']}",
                        }
                    ],
                },
            ],
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(cfg.webhook_url, json=slack_payload, timeout=10.0)
            resp.raise_for_status()

    async def _send_telegram(
        self, name: str, cfg: NotificationConfig, payload: dict
    ) -> None:
        """Send notification via Telegram Bot API."""
        if not cfg.bot_token or not cfg.chat_id:
            raise ValueError(
                f"Telegram notification '{name}' missing bot_token or chat_id"
            )

        text = (
            f"*SDC Agents: {payload['event']}*\n\n"
            f"{payload['summary']}\n\n"
            f"Agent: `{payload['details'].get('agent', '?')}`\n"
            f"Tool: `{payload['details'].get('tool', '?')}`\n"
            f"Time: {payload['timestamp']}"
        )

        url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
        telegram_payload = {
            "chat_id": cfg.chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=telegram_payload, timeout=10.0)
            resp.raise_for_status()

    async def _send_email(
        self, name: str, cfg: NotificationConfig, payload: dict
    ) -> None:
        """Send notification via SMTP email."""
        if not cfg.smtp_host or not cfg.from_address or not cfg.to_addresses:
            raise ValueError(
                f"Email notification '{name}' missing smtp_host, from_address, "
                "or to_addresses"
            )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"SDC Agents: {payload['event']}"
        msg["From"] = cfg.from_address
        msg["To"] = ", ".join(cfg.to_addresses)

        # Plain text body
        plain = (
            f"SDC Agents: {payload['event']}\n\n"
            f"{payload['summary']}\n\n"
            f"Agent: {payload['details'].get('agent', '?')}\n"
            f"Tool: {payload['details'].get('tool', '?')}\n"
            f"Time: {payload['timestamp']}\n\n"
            f"Details:\n{json.dumps(payload['details'], indent=2, default=str)}"
        )
        msg.attach(MIMEText(plain, "plain"))

        # HTML body
        details_rows = "".join(
            f"<tr><td style='padding:4px 8px;font-weight:bold'>{k}</td>"
            f"<td style='padding:4px 8px'>{v}</td></tr>"
            for k, v in payload["details"].items()
        )
        html = (
            f"<h2>SDC Agents: {payload['event']}</h2>"
            f"<p>{payload['summary']}</p>"
            f"<table style='border-collapse:collapse;border:1px solid #ddd'>"
            f"{details_rows}</table>"
            f"<p style='color:#888;font-size:12px'>{payload['timestamp']}</p>"
        )
        msg.attach(MIMEText(html, "html"))

        def _smtp_send():
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
                server.starttls()
                if cfg.smtp_user and cfg.smtp_password:
                    server.login(cfg.smtp_user, cfg.smtp_password)
                server.sendmail(cfg.from_address, cfg.to_addresses, msg.as_string())

        await asyncio.to_thread(_smtp_send)
