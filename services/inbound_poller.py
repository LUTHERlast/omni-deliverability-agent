import re
import email
import imaplib
import datetime
from email.header import decode_header
from typing import Optional, Dict
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import AsyncSessionLocal
from models import Lead, AgentEvent, EmailLog
from services.notifier import notifier

PUBLIC_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk",
    "hotmail.com", "outlook.com", "live.com", "icloud.com",
    "mail.com", "aol.com", "zoho.com", "protonmail.com"
}

def clean_email_address(raw_from: str) -> str:
    """Extracts raw email address from sender header."""
    if not raw_from:
        return ""
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw_from)
    if match:
        return match.group(0).lower().strip()
    return raw_from.strip().lower()

def clean_reply_body(raw_body: str) -> str:
    """Strips email headers, previous quoting (> ...), and signatures to extract the client's actual response."""
    if not raw_body:
        return ""
    lines = raw_body.strip().splitlines()
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if re.search(r'^(On\s+.*wrote:|-+Original Message-+|>|From:\s+|Date:\s+)', stripped, re.IGNORECASE):
            break
        clean_lines.append(line)
    result = "\n".join(clean_lines).strip()
    return result if result else raw_body.strip()

def decode_mime_header(header_value: str) -> str:
    """Safely decodes encoded MIME email subject and headers."""
    if not header_value:
        return ""
    try:
        decoded_parts = decode_header(header_value)
        subject_parts = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                subject_parts.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                subject_parts.append(str(part))
        return "".join(subject_parts)
    except Exception:
        return str(header_value)

def analyze_deliverability_reply_sentiment(text: str) -> Dict:
    """Analyzes prospect sentiment specifically regarding email deliverability & DNS fixes."""
    lower = text.lower()
    
    if any(k in lower for k in ["unsubscribe", "remove me", "stop emailing", "opt out", "spam"]):
        return {
            "sentiment": "UNSUBSCRIBE",
            "recommended_action": "Mark lead as unsubscribed; immediately halt sequences."
        }
    
    if any(k in lower for k in ["not interested", "no thanks", "dont need", "don't need", "not looking"]):
        return {
            "sentiment": "NOT_INTERESTED",
            "recommended_action": "Mark lead as lost; archive prospect."
        }
    
    if any(k in lower for k in ["how much", "price", "cost", "send invoice", "fix this", "help us", "interested", "lets talk", "let's talk", "details", "call me", "call us", "whatsapp", "meeting", "what do you charge"]):
        return {
            "sentiment": "INTERESTED",
            "recommended_action": "Hot prospect! Send invoice and offer 1-click DNS record deployment.",
            "suggested_reply": "Share DNS fix blueprint and AED 1,450 checkout link for turnkey setup within 2 hours."
        }
        
    return {
        "sentiment": "INTERESTED",
        "recommended_action": "Review client inquiry and respond with domain diagnostic blueprint.",
        "suggested_reply": "Clarify current DNS provider (Cloudflare, GoDaddy, Google) to prepare deployment."
    }

async def find_matching_lead(session: AsyncSession, sender_email: str, subject: str = "") -> Optional[Lead]:
    """Finds matching lead by email, corporate domain, or company name."""
    clean_sender = clean_email_address(sender_email)
    if not clean_sender or "@" not in clean_sender:
        return None

    # Stage 1: Exact email match
    stmt = select(Lead).where(func.lower(Lead.contact_email) == clean_sender)
    res = await session.execute(stmt)
    lead = res.scalars().first()
    if lead:
        return lead

    # Stage 2: Corporate domain match
    user_part, domain_part = clean_sender.split("@", 1)
    if domain_part not in PUBLIC_EMAIL_DOMAINS:
        stmt_domain = select(Lead).where(
            or_(
                func.lower(Lead.contact_email).like(f"%@{domain_part}"),
                func.lower(Lead.domain) == domain_part.lower()
            )
        )
        res_domain = await session.execute(stmt_domain)
        lead = res_domain.scalars().first()
        if lead:
            return lead

    return None

async def process_inbound_reply(
    session: AsyncSession,
    sender: str,
    subject: str,
    body: str,
    source: str = "WEBHOOK"
) -> Dict:
    """Core processor: parses inbound reply, updates lead status, and dispatches Telegram notification."""
    clean_sender = clean_email_address(sender)
    clean_subject = decode_mime_header(subject).strip()
    clean_text = clean_reply_body(body).strip()
    if not clean_text:
        clean_text = body.strip() or "Confirmed (No body content)"

    sender_domain = clean_sender.split("@")[-1] if "@" in clean_sender else ""
    system_ignore_domains = {"google.com", "googlemail.com", "accounts.google.com", "brevo.com", "brevosend.com", "mailin.fr"}
    if (
        clean_sender.startswith(("no-reply@", "noreply@", "mailer-daemon@", "postmaster@", "notifications@"))
        or sender_domain in system_ignore_domains
    ):
        return {"status": "IGNORED", "reason": f"System message from {clean_sender}"}

    lead = await find_matching_lead(session, clean_sender, clean_subject)

    if not lead:
        # Create new lead so no client response is lost
        domain = sender_domain if sender_domain not in PUBLIC_EMAIL_DOMAINS else "unknown-domain.com"
        comp_name = domain.split(".")[0].capitalize() if domain not in PUBLIC_EMAIL_DOMAINS else f"Prospect ({clean_sender})"
        lead = Lead(
            domain=domain,
            company_name=comp_name,
            contact_email=clean_sender,
            status="QUALIFIED",
            qualification_score=90,
            deal_value=settings.DEFAULT_DEAL_VALUE
        )
        session.add(lead)
        await session.commit()
        await session.refresh(lead)

    analysis = analyze_deliverability_reply_sentiment(clean_text)
    sentiment = analysis.get("sentiment", "INTERESTED")
    now_utc = datetime.datetime.utcnow()

    lead.reply_sentiment = sentiment
    lead.next_followup_at = None  # Halt automated cold sequences immediately

    is_hot = sentiment in ["INTERESTED", "MEETING_REQUESTED", "QUESTION"]
    if is_hot:
        lead.status = "REPLIED_INTERESTED"
    elif sentiment == "UNSUBSCRIBE":
        lead.status = "UNSUBSCRIBED"
    elif sentiment == "NOT_INTERESTED":
        lead.status = "LOST"

    # Event log
    event = AgentEvent(
        level="HOT" if is_hot else "INFO",
        category="INBOUND_REPLY",
        message=f"🔥 Deliverability Reply from {lead.company_name} ({clean_sender})!",
        details=f"Subject: {clean_subject}\nReply: {clean_text}\nSentiment: {sentiment}"
    )
    session.add(event)

    # Email log
    email_log = EmailLog(
        lead_id=lead.id,
        domain=lead.domain,
        recipient_email=clean_sender,
        subject=clean_subject or f"Re: Deliverability Audit - {lead.domain}",
        body=clean_text,
        sequence_stage="INBOUND_REPLY",
        status="RECEIVED",
        sent_at=now_utc
    )
    session.add(email_log)
    await session.commit()
    await session.refresh(lead)

    # Dispatch to Athul's Telegram
    if is_hot:
        try:
            await notifier.alert_hot_reply(
                company=lead.company_name,
                contact=clean_sender,
                reply_text=clean_text,
                sentiment=sentiment,
                suggested_reply=analysis.get("suggested_reply", "Send invoice and DNS blueprint async.")
            )
        except Exception as e:
            print(f"[Notifier Warning]: {e}")

    return {
        "status": "PROCESSED",
        "lead_id": lead.id,
        "sentiment": sentiment,
        "is_hot": is_hot
    }

class InboundEmailPoller:
    """Polls IMAP server for client replies."""

    async def poll_once(self) -> int:
        if not settings.IMAP_ENABLED or not settings.IMAP_PASSWORD:
            return 0

        processed_count = 0
        try:
            mail = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
            mail.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
            mail.select("INBOX")

            # Search unseen emails
            status, messages = mail.search(None, '(UNSEEN)')
            if status != "OK" or not messages[0]:
                mail.close()
                mail.logout()
                return 0

            mail_ids = messages[0].split()
            for msg_id in mail_ids[-10:]: # Process last 10 unseen
                status, msg_data = mail.fetch(msg_id, '(RFC822)')
                if status != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        sender = msg.get("From", "")
                        subject = msg.get("Subject", "")
                        
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

                        async with AsyncSessionLocal() as session:
                            res = await process_inbound_reply(session, sender, subject, body, source="IMAP")
                            if res.get("status") == "PROCESSED":
                                processed_count += 1

            mail.close()
            mail.logout()
        except Exception as e:
            print(f"[IMAP Poller Error]: {e}")

        return processed_count

inbound_poller = InboundEmailPoller()
