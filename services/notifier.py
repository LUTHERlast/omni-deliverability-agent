import datetime
from typing import Optional, Dict
import httpx
from config import settings
from database import AsyncSessionLocal
from models import AgentEvent

class NotificationDispatcher:
    """Delivers real-time notifications to Athul via Telegram bot (@dreamer_comrade)."""

    def __init__(self):
        self.telegram_bot_token = settings.TELEGRAM_BOT_TOKEN
        self.telegram_chat_id = settings.TELEGRAM_CHAT_ID

    async def notify_all(self, title: str, message: str, level: str = "INFO", category: str = "NOTIFICATION"):
        """Broadcasts notification across Telegram and records event in SQLite."""
        # 1. Log event into SQLite
        try:
            async with AsyncSessionLocal() as session:
                event = AgentEvent(
                    level=level,
                    category=category,
                    message=f"[{title}] {message[:250]}",
                    details=message
                )
                session.add(event)
                await session.commit()
        except Exception:
            pass

        # 2. Telegram Bot
        if settings.NOTIFY_TELEGRAM and self.telegram_bot_token and self.telegram_chat_id:
            await self._send_telegram(f"*{title}*\n\n{message}")

    async def _send_telegram(self, text: str):
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    # Retry without Markdown in case formatting characters triggered parse errors
                    payload["parse_mode"] = ""
                    await client.post(url, json=payload)
        except Exception as e:
            print(f"[Telegram Dispatch Error]: {e}")

    async def alert_new_audit(self, domain: str, score: int, risk: str, issues_count: int, company: str = None):
        """Notification when a new domain DNS vulnerability scan completes."""
        title = f"🛡️ OmniDeliverability: DNS Audit Complete for {domain}"
        comp_str = f" ({company})" if company else ""
        msg = (
            f"• *Domain:* {domain}{comp_str}\n"
            f"• *Health Score:* {score}/100\n"
            f"• *Risk Level:* {risk}\n"
            f"• *Vulnerabilities Detected:* {issues_count}\n"
            f"• *Public Scorecard:* {settings.PUBLIC_APP_URL}/audit/{domain}\n\n"
            f"Diagnostic outreach ready for delivery."
        )
        await self.notify_all(title, msg, level="INFO", category="DNS_AUDIT")

    async def alert_outreach_sent(self, domain: str, company: str, contact_email: str, stage: str = "INITIAL"):
        """Notification when a diagnostic audit email is dispatched to a prospect."""
        title = f"📨 OmniDeliverability: Pitch Dispatched to {company}"
        msg = (
            f"• *Company:* {company}\n"
            f"• *Domain:* {domain}\n"
            f"• *Recipient:* {contact_email}\n"
            f"• *Stage:* {stage}\n"
            f"• *Sender:* {settings.FROM_EMAIL}\n"
            f"• *Scorecard Sent:* {settings.PUBLIC_APP_URL}/audit/{domain}"
        )
        await self.notify_all(title, msg, level="SUCCESS", category="OUTREACH")

    async def alert_hot_reply(self, company: str, contact: str, reply_text: str, sentiment: str, suggested_reply: str):
        """High-urgency notification when a lead responds to our DNS audit pitch."""
        title = f"🔥 HOT LEAD ALERT: {company} Replied to Deliverability Pitch!"
        msg = (
            f"• *Company:* {company} ({contact})\n"
            f"• *Sentiment:* {sentiment}\n"
            f"• *Their Reply:*\n\"{reply_text}\"\n\n"
            f"• *Recommended Fix & Blueprint:*\n{suggested_reply}\n\n"
            f"Action: Step in to finalize domain setup or send invoice!"
        )
        await self.notify_all(title, msg, level="HOT", category="HOT_REPLY")

    async def alert_payment(self, company: str, amount: float, invoice_id: str):
        """High-value alert when a client pays for DNS Shield installation."""
        title = f"💰 REVENUE WON: AED {amount:,.2f} from {company}!"
        msg = (
            f"• *Client:* {company}\n"
            f"• *Amount Paid:* AED {amount:,.2f}\n"
            f"• *Service:* Turnkey DNS Authentication & Deliverability Shield\n"
            f"• *Invoice ID:* {invoice_id}\n\n"
            f"Agent is ready to generate and deploy DNS blueprint."
        )
        await self.notify_all(title, msg, level="SUCCESS", category="PAYMENT")

notifier = NotificationDispatcher()
