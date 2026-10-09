import ssl
import smtplib
import asyncio
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from config import settings
from models import Lead, EmailLog, AgentEvent, DomainAudit
from services.ai_copywriter import deliverability_copywriter
from services.notifier import notifier

def text_to_html_email(body_text: str) -> str:
    """Converts plain text email into clean, mobile-responsive, beautifully formatted HTML."""
    paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    html_parts = []
    for p in paragraphs:
        if p.startswith("---"):
            html_parts.append('<hr style="border:none; border-top: 1px solid #e2e8f0; margin: 24px 0;">')
        elif p.startswith("Note:"):
            html_parts.append(f'<p style="font-size: 12px; color: #718096; line-height: 1.5; margin: 8px 0;">{p}</p>')
        elif p.startswith("http://") or p.startswith("https://"):
            html_parts.append(f'<p style="margin: 16px 0;"><a href="{p}" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; font-size: 14px;">View Live Domain Health Scorecard &rarr;</a></p>')
        else:
            formatted = p.replace("\n", "<br>")
            # Highlight audit links inside text
            if "http://" in formatted or "https://" in formatted:
                import re
                formatted = re.sub(r'(https?://[^\s<]+)', r'<a href="\1" style="color: #2563eb; font-weight: 600; text-decoration: underline;">\1</a>', formatted)
            html_parts.append(f'<p style="font-size: 15px; color: #1a202c; line-height: 1.6; margin: 0 0 16px 0;">{formatted}</p>')

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #ffffff; padding: 24px; color: #1a202c; max-width: 600px; margin: 0 auto;">
{''.join(html_parts)}
</body>
</html>"""

class OutreachEngine:
    """Handles email dispatching, sequence escalation, rate limits, and SMTP delivery."""

    def __init__(self):
        self.last_sent_time = None

    async def can_send_more_today(self, db: AsyncSession) -> bool:
        """Check if daily outbound limits have been reached."""
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(EmailLog.id)).where(EmailLog.sent_at >= today_start)
        res = await db.execute(stmt)
        count = res.scalar() or 0
        return count < settings.MAX_DAILY_EMAILS

    def _send_smtp_raw(self, to_email: str, subject: str, body: str, html_body: str = None) -> Tuple[bool, str]:
        """Synchronous robust SMTP sender with automatic port 465 SSL / 587 STARTTLS fallback and rich HTML support."""
        if not settings.SMTP_ENABLED or not settings.SMTP_USER:
            return True, "Simulation: SMTP disabled (dry-run mode)"

        password = (settings.SMTP_PASSWORD or "").replace(" ", "").strip()
        user = (settings.SMTP_USER or "").strip()
        from_addr = (settings.FROM_EMAIL or user).strip()
        from_name = (settings.FROM_NAME or settings.OPERATOR_NAME).strip()

        # Check for Brevo REST API Key (xkeysib-...) for instant firewall/port bypass
        if password.startswith("xkeysib-"):
            try:
                import json
                import urllib.request
                payload = {
                    "sender": {"name": from_name, "email": from_addr},
                    "to": [{"email": to_email}],
                    "subject": subject,
                    "textContent": body
                }
                if html_body:
                    payload["htmlContent"] = html_body

                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    "https://api.brevo.com/v3/smtp/email",
                    data=req_data,
                    headers={
                        "api-key": password,
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    }
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status in [200, 201, 202]:
                        return True, "Successfully dispatched via Brevo API"
            except Exception as e:
                err_detail = str(e)
                if hasattr(e, "read"):
                    try:
                        err_detail += f" - Response: {e.read().decode('utf-8')}"
                    except Exception:
                        pass
                return False, f"Brevo API Error: {err_detail}"

        msg = MIMEMultipart("alternative")
        msg['From'] = f"{from_name} <{from_addr}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        context = ssl.create_default_context()

        try:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, 465, timeout=15, context=context)
            server.login(user, password)
            server.send_message(msg)
            server.quit()
            return True, "Successfully dispatched via SMTP SSL (465)"
        except Exception:
            try:
                server = smtplib.SMTP(settings.SMTP_HOST, 587, timeout=15)
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(user, password)
                server.send_message(msg)
                server.quit()
                return True, "Successfully dispatched via SMTP STARTTLS (587)"
            except Exception as e:
                return False, f"SMTP Error: {str(e)}"

    def validate_and_sanitize_email(self, email: str) -> Tuple[bool, str, str]:
        """Validates recipient format, excludes demo/placeholder strings, and checks DNS host availability to prevent bounces."""
        import socket
        import re

        if not email or "@" not in email:
            return False, "", "Invalid email format"

        cleaned = re.sub(r'^(u003e|<|&lt;|">|")', '', email.strip()).rstrip('.,;:>')
        if "@" not in cleaned:
            return False, "", "Malformed email after cleaning"

        user, domain = cleaned.split("@", 1)
        domain = domain.lower().strip()
        user = user.lower().strip()

        if user in ["you", "user", "test", "name", "email", "placeholder", "demo", "sample", "yourname"]:
            return False, cleaned, f"Template placeholder username '{user}'"

        if any(p in domain for p in ["-demo", ".demo.", "example.", "website.com", "domain.com", "test.com", "placeholder."]):
            return False, cleaned, f"Placeholder/demo domain '{domain}'"

        try:
            socket.gethostbyname(domain)
        except Exception:
            return False, cleaned, f"Domain '{domain}' does not exist in DNS (would hard bounce)"

        return True, cleaned, "Valid"

    async def send_initial_outreach(self, lead: Lead, audit: DomainAudit, db: AsyncSession) -> Tuple[bool, str]:
        """Dispatches Stage 1 Initial Deliverability Diagnostic Pitch."""
        if lead.status in ["BOUNCED", "UNSUBSCRIBED"]:
            return False, f"Skipped: Lead {lead.company_name} is marked as {lead.status}"

        if not await self.can_send_more_today(db):
            return False, "Daily email limit reached."

        is_valid, cleaned_email, reason = self.validate_and_sanitize_email(lead.contact_email)
        lead.contact_email = cleaned_email or lead.contact_email

        import json
        audit_dict = {
            "domain": audit.domain,
            "company_name": audit.company_name,
            "overall_score": audit.overall_score,
            "risk_level": audit.risk_level,
            "inbox_placement_rate": audit.inbox_placement_rate,
            "issues": json.loads(audit.issues_json or "[]")
        }
        lead_dict = {
            "company_name": lead.company_name,
            "contact_name": lead.contact_name,
            "domain": lead.domain
        }

        subject, body = deliverability_copywriter.generate_audit_email(audit_dict, lead_dict, settings.PUBLIC_APP_URL)
        html_body = text_to_html_email(body)

        if not is_valid:
            success, msg = True, f"Simulated: {reason}"
            log_status = "SIMULATED"
        elif settings.SIMULATION_MODE or not settings.SMTP_ENABLED:
            success, msg = True, "Simulated outbound email sent successfully."
            log_status = "SIMULATED"
        else:
            existing_send = (await db.execute(
                select(func.count(EmailLog.id)).where(
                    EmailLog.recipient_email == cleaned_email,
                    EmailLog.status == "SENT"
                )
            )).scalar() or 0
            if existing_send > 0:
                return False, f"Duplicate safeguard: already emailed {cleaned_email} in this campaign"

            success, msg = await asyncio.to_thread(self._send_smtp_raw, cleaned_email, subject, body, html_body)
            log_status = "SENT" if success else "FAILED"

        email_log = EmailLog(
            lead_id=lead.id,
            domain=lead.domain,
            sequence_stage="INITIAL",
            subject=subject,
            body=body,
            recipient_email=lead.contact_email,
            status=log_status,
            error_message=msg if not success else None
        )
        db.add(email_log)

        if success:
            lead.status = "CONTACTED"
            lead.emails_sent_count = (lead.emails_sent_count or 0) + 1
            lead.last_contacted_at = datetime.datetime.utcnow()
            lead.next_followup_at = datetime.datetime.utcnow() + datetime.timedelta(days=settings.AUDIT_FOLLOWUP_DAYS)
            
            event = AgentEvent(
                level="SUCCESS",
                category="OUTREACH",
                message=f"Dispatched deliverability audit alert to {lead.contact_name or 'team'} at {lead.domain}",
                details=f"Subject: {subject} | Score: {audit.overall_score}/100"
            )
            db.add(event)
            try:
                await notifier.alert_outreach_sent(lead.domain, lead.company_name, lead.contact_email, "INITIAL")
            except Exception:
                pass
        else:
            event = AgentEvent(
                level="ERROR",
                category="OUTREACH",
                message=f"Failed to dispatch audit to {lead.domain}: {msg}"
            )
            db.add(event)

        await db.commit()
        return success, msg

    async def send_followup_outreach(self, lead: Lead, audit: DomainAudit, db: AsyncSession) -> Tuple[bool, str]:
        """Dispatches automated multi-stage follow-up."""
        if lead.status in ["BOUNCED", "UNSUBSCRIBED"]:
            return False, f"Skipped: Lead {lead.company_name} is marked as {lead.status}"

        if not await self.can_send_more_today(db):
            return False, "Daily email limit reached."

        current_status = lead.status
        if current_status == "CONTACTED":
            next_stage = "FOLLOWUP_1"
            next_status = "FOLLOWUP_1"
            next_days = 3
        elif current_status == "FOLLOWUP_1":
            next_stage = "FOLLOWUP_2"
            next_status = "FOLLOWUP_2"
            next_days = 4
        elif current_status == "FOLLOWUP_2":
            next_stage = "FOLLOWUP_3"
            next_status = "FOLLOWUP_3"
            next_days = None
        else:
            return False, f"Lead not eligible for follow-up (status: {current_status})"

        import json
        audit_dict = {
            "domain": audit.domain,
            "company_name": audit.company_name,
            "overall_score": audit.overall_score,
            "risk_level": audit.risk_level,
            "inbox_placement_rate": audit.inbox_placement_rate,
            "issues": json.loads(audit.issues_json or "[]")
        }
        lead_dict = {
            "company_name": lead.company_name,
            "contact_name": lead.contact_name,
            "domain": lead.domain
        }

        subject, body = deliverability_copywriter.generate_followup_email(audit_dict, lead_dict, settings.PUBLIC_APP_URL, next_stage)
        html_body = text_to_html_email(body)

        is_valid, cleaned_email, reason = self.validate_and_sanitize_email(lead.contact_email)
        lead.contact_email = cleaned_email or lead.contact_email

        if not is_valid:
            success, msg = True, f"Simulated {next_stage}: {reason}"
            log_status = "SIMULATED"
        elif settings.SIMULATION_MODE or not settings.SMTP_ENABLED:
            success, msg = True, f"Simulated {next_stage} email sent successfully."
            log_status = "SIMULATED"
        else:
            success, msg = await asyncio.to_thread(self._send_smtp_raw, cleaned_email, subject, body, html_body)
            log_status = "SENT" if success else "FAILED"

        email_log = EmailLog(
            lead_id=lead.id,
            domain=lead.domain,
            sequence_stage=next_stage,
            subject=subject,
            body=body,
            recipient_email=lead.contact_email,
            status=log_status,
            error_message=msg if not success else None
        )
        db.add(email_log)

        if success:
            lead.status = next_status
            lead.emails_sent_count = (lead.emails_sent_count or 0) + 1
            lead.last_contacted_at = datetime.datetime.utcnow()
            lead.next_followup_at = datetime.datetime.utcnow() + datetime.timedelta(days=next_days) if next_days else None
            try:
                await notifier.alert_outreach_sent(lead.domain, lead.company_name, lead.contact_email, next_stage)
            except Exception:
                pass
        await db.commit()
        return success, msg

outreach_engine = OutreachEngine()
