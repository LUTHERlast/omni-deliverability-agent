import json
import asyncio
import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, func, and_

from config import settings
from database import AsyncSessionLocal
from models import Lead, DomainAudit, EmailLog, AgentEvent
from services.prospector import prospector
from services.outreach import outreach_engine
from services.notifier import notifier
from services.inbound_poller import inbound_poller

scheduler = AsyncIOScheduler()

async def job_prospecting_and_auditing() -> dict:
    """Autonomous Loop 1: Finds B2B prospects, audits DNS records, qualifies leaks, and dispatches diagnostic alert."""
    if not settings.AGENT_ENABLED:
        return {"status": "SKIPPED", "reason": "Agent paused"}

    async with AsyncSessionLocal() as session:
        # Get existing emails
        res = await session.execute(select(Lead.contact_email))
        existing_emails = set(res.scalars().all())

        new_candidates = await prospector.discover_and_audit_prospects(existing_emails, batch_size=2)
        dispatched_count = 0

        for cand in new_candidates:
            audit_data = cand["audit"]
            
            # Save DomainAudit record
            domain_audit = DomainAudit(
                domain=cand["domain"],
                company_name=cand["company_name"],
                website=cand.get("website"),
                contact_email=cand["contact_email"],
                overall_score=audit_data.get("overall_score", 50),
                risk_level=audit_data.get("risk_level", "HIGH"),
                inbox_placement_rate=audit_data.get("inbox_placement_rate", 35),
                spf_status=audit_data.get("spf_status", "MISSING"),
                spf_record=audit_data.get("spf_record"),
                dkim_status=audit_data.get("dkim_status", "MISSING"),
                dkim_selector=audit_data.get("dkim_selector"),
                dmarc_status=audit_data.get("dmarc_status", "MISSING"),
                dmarc_policy=audit_data.get("dmarc_policy", "missing"),
                dmarc_record=audit_data.get("dmarc_record"),
                mx_provider=audit_data.get("mx_provider", "Unknown"),
                issues_json=json.dumps(audit_data.get("issues", [])),
                fix_blueprint_json=json.dumps(audit_data.get("fix_blueprint", [])),
                audit_token=audit_data.get("audit_token")
            )
            session.add(domain_audit)
            await session.commit()
            await session.refresh(domain_audit)

            # Save Lead record
            lead = Lead(
                domain=cand["domain"],
                company_name=cand["company_name"],
                contact_name=cand.get("contact_name"),
                contact_email=cand["contact_email"],
                status="QUALIFIED",
                audit_id=domain_audit.id,
                qualification_score=audit_data.get("overall_score", 50),
                deal_value=settings.DEFAULT_DEAL_VALUE
            )
            session.add(lead)
            await session.commit()
            await session.refresh(lead)

            # Log discovery event
            event = AgentEvent(
                level="INFO",
                category="DNS_AUDIT",
                message=f"Audited {cand['domain']} -> Score: {domain_audit.overall_score}/100 ({domain_audit.risk_level})",
                details=f"Provider: {domain_audit.mx_provider} | Inbox Rate: {domain_audit.inbox_placement_rate}%"
            )
            session.add(event)
            await session.commit()

            # Trigger Telegram alert for domain audit
            try:
                await notifier.alert_new_audit(
                    domain=domain_audit.domain,
                    score=domain_audit.overall_score,
                    risk=domain_audit.risk_level,
                    issues_count=len(audit_data.get("issues", [])),
                    company=domain_audit.company_name
                )
            except Exception:
                pass

            # Dispatch initial diagnostic pitch
            success, _ = await outreach_engine.send_initial_outreach(lead, domain_audit, session)
            if success:
                dispatched_count += 1

        return {
            "status": "SUCCESS",
            "audited_count": len(new_candidates),
            "dispatched_count": dispatched_count
        }


async def job_followup_cycle() -> int:
    """Autonomous Loop 2: Scans for leads due for scheduled follow-ups."""
    if not settings.AGENT_ENABLED:
        return 0

    now = datetime.datetime.utcnow()
    dispatched_count = 0
    async with AsyncSessionLocal() as session:
        stmt = select(Lead).where(
            and_(
                Lead.status.in_(["CONTACTED", "FOLLOWUP_1", "FOLLOWUP_2"]),
                Lead.next_followup_at != None,
                Lead.next_followup_at <= now
            )
        ).limit(5)
        res = await session.execute(stmt)
        leads_due = res.scalars().all()

        for lead in leads_due:
            audit = await session.get(DomainAudit, lead.audit_id)
            if audit:
                success, _ = await outreach_engine.send_followup_outreach(lead, audit, session)
                if success:
                    dispatched_count += 1
                await asyncio.sleep(2)

    return dispatched_count

async def job_inbound_polling() -> int:
    """Autonomous Loop 3: Checks Gmail/IMAP inbox for client replies and auto-logs them."""
    if not settings.AGENT_ENABLED or not settings.IMAP_ENABLED:
        return 0
    return await inbound_poller.poll_once()

def start_scheduler():
    """Initializes and runs autonomous background cron cycles."""
    import datetime
    now = datetime.datetime.now()

    # 1. Lead prospecting & auditing (fires at 15s, then every 10 mins)
    scheduler.add_job(
        job_prospecting_and_auditing,
        "interval",
        minutes=10,
        next_run_time=now + datetime.timedelta(seconds=15),
        id="job_prospecting_audit",
        replace_existing=True,
        misfire_grace_time=120
    )

    # 2. Automated Follow-up sequences (fires at 45s, then every 15 mins)
    scheduler.add_job(
        job_followup_cycle,
        "interval",
        minutes=15,
        next_run_time=now + datetime.timedelta(seconds=45),
        id="job_followups",
        replace_existing=True,
        misfire_grace_time=120
    )

    # 3. Autonomous Inbound reply poller (fires every 2 mins)
    scheduler.add_job(
        job_inbound_polling,
        "interval",
        minutes=settings.IMAP_INTERVAL_MINUTES,
        next_run_time=now + datetime.timedelta(seconds=30),
        id="job_inbound_polling",
        replace_existing=True,
        misfire_grace_time=60
    )

    if not scheduler.running:
        scheduler.start()
        print("[Deliverability Scheduler] Autonomous Scheduler started with immediate execution on startup!")

