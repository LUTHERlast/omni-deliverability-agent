import os
import json
import datetime
from fastapi import FastAPI, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from config import settings
from database import get_db, init_db
from models import Lead, DomainAudit, EmailLog, AgentEvent
from services.dns_auditor import dns_auditor
from services.scheduler import start_scheduler, job_prospecting_and_auditing

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

BASE_DIR = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
static_dir = os.path.join(BASE_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

START_TIME = datetime.datetime.utcnow()

from services.master_routes import master_router
app.include_router(master_router)

@app.on_event("startup")
async def startup_event():
    await init_db()
    start_scheduler()


@app.get("/api/ping")
@app.get("/api/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health verification endpoint."""
    total_audits = (await db.execute(select(func.count(DomainAudit.id)))).scalar() or 0
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar() or 0
    return {
        "status": "HEALTHY",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "port": settings.PORT,
        "database": "CONNECTED",
        "total_audits": total_audits,
        "total_leads": total_leads,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

@app.get("/", response_class=HTMLResponse)
async def dashboard_view(request: Request, db: AsyncSession = Depends(get_db)):
    """Executive Deliverability Command Center Dashboard."""
    # Compute KPIs
    total_audits = (await db.execute(select(func.count(DomainAudit.id)))).scalar() or 0
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar() or 0
    
    # Critical risk count (< 50 score)
    critical_risks = (await db.execute(select(func.count(DomainAudit.id)).where(DomainAudit.overall_score < 50))).scalar() or 0
    
    # Emails sent
    emails_sent = (await db.execute(select(func.count(EmailLog.id)).where(EmailLog.status == "SENT"))).scalar() or 0
    
    # Pipeline value
    pipeline_val = (await db.execute(select(func.sum(Lead.deal_value)).where(Lead.status.in_(["QUALIFIED", "CONTACTED", "FOLLOWUP_1", "FOLLOWUP_2"])))).scalar() or 0.0

    # Recent Leads
    leads_res = await db.execute(select(Lead).order_by(desc(Lead.id)).limit(15))
    leads = leads_res.scalars().all()

    # Lead audits mapping
    audit_ids = [l.audit_id for l in leads if l.audit_id]
    audits_map = {}
    if audit_ids:
        aud_res = await db.execute(select(DomainAudit).where(DomainAudit.id.in_(audit_ids)))
        for a in aud_res.scalars().all():
            audits_map[a.id] = a

    # Recent Events
    events_res = await db.execute(select(AgentEvent).order_by(desc(AgentEvent.id)).limit(8))
    events = events_res.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "settings": settings,
            "total_audits": total_audits,
            "total_leads": total_leads,
            "critical_risks": critical_risks,
            "emails_sent": emails_sent,
            "pipeline_val": pipeline_val,
            "leads": leads,
            "audits_map": audits_map,
            "events": events
        }
    )

@app.get("/audit/{domain}", response_class=HTMLResponse)
async def public_audit_scorecard(domain: str, request: Request, db: AsyncSession = Depends(get_db)):
    """High-converting public interactive Domain Health Scorecard."""
    clean_dom = dns_auditor.clean_domain(domain)
    
    # Check if existing audit exists
    stmt = select(DomainAudit).where(DomainAudit.domain == clean_dom).order_by(desc(DomainAudit.id))
    existing = (await db.execute(stmt)).scalars().first()

    if not existing:
        # Run real-time audit on the fly
        audit_data = await dns_auditor.audit_domain(clean_dom)
        existing = DomainAudit(
            domain=clean_dom,
            company_name=clean_dom.capitalize(),
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
        db.add(existing)
        await db.commit()
        await db.refresh(existing)

    issues = json.loads(existing.issues_json or "[]")
    blueprint = json.loads(existing.fix_blueprint_json or "[]")

    return templates.TemplateResponse(
        request=request,
        name="audit_scorecard.html",
        context={
            "settings": settings,
            "audit": existing,
            "issues": issues,
            "blueprint": blueprint
        }
    )

@app.get("/checkout/{domain}", response_class=HTMLResponse)
async def checkout_view(domain: str, request: Request, tier: str = "primary", db: AsyncSession = Depends(get_db)):
    """Turnkey asynchronous Checkout & Order Authorization page."""
    clean_dom = dns_auditor.clean_domain(domain)
    
    # Check existing audit or run quick scan
    stmt = select(DomainAudit).where(DomainAudit.domain == clean_dom).order_by(desc(DomainAudit.id))
    audit = (await db.execute(stmt)).scalars().first()
    if not audit:
        audit_data = await dns_auditor.audit_domain(clean_dom)
        audit = DomainAudit(
            domain=clean_dom,
            company_name=clean_dom.capitalize(),
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
        db.add(audit)
        await db.commit()
        await db.refresh(audit)
        
    # Check existing lead
    lead_stmt = select(Lead).where(Lead.domain == clean_dom).order_by(desc(Lead.id))
    lead = (await db.execute(lead_stmt)).scalars().first()
    
    return templates.TemplateResponse(
        request=request,
        name="checkout.html",
        context={
            "settings": settings,
            "domain": clean_dom,
            "tier": tier if tier in ["primary", "outbound"] else "primary",
            "audit": audit,
            "lead": lead
        }
    )

@app.post("/api/checkout/complete")
async def api_checkout_complete(request: Request, db: AsyncSession = Depends(get_db)):
    """Processes async checkout, registers won revenue, and alerts Athul on Telegram."""
    data = await request.json()
    domain = dns_auditor.clean_domain(data.get("domain", ""))
    tier = data.get("tier", "primary")
    amount = float(data.get("amount", settings.DEFAULT_DEAL_VALUE))
    company_name = data.get("company_name", "").strip() or domain.split(".")[0].capitalize()
    contact_name = data.get("contact_name", "").strip()
    contact_email = data.get("contact_email", "").strip()
    dns_provider = data.get("dns_provider", "Cloudflare")
    payment_method = data.get("payment_method", "CARD")
    
    if not domain or not contact_email:
        return JSONResponse({"status": "ERROR", "message": "Domain and Contact Email are required"}, status_code=400)
        
    # Find or create Lead
    stmt = select(Lead).where(Lead.domain == domain).order_by(desc(Lead.id))
    lead = (await db.execute(stmt)).scalars().first()
    now_utc = datetime.datetime.utcnow()
    
    if not lead:
        audit_stmt = select(DomainAudit).where(DomainAudit.domain == domain).order_by(desc(DomainAudit.id))
        audit = (await db.execute(audit_stmt)).scalars().first()
        lead = Lead(
            domain=domain,
            company_name=company_name,
            contact_name=contact_name,
            contact_email=contact_email,
            status="WON",
            deal_value=amount,
            audit_id=audit.id if audit else None,
            paid_at=now_utc,
            install_status="QUEUED"
        )
        db.add(lead)
    else:
        lead.company_name = company_name
        if contact_name:
            lead.contact_name = contact_name
        lead.contact_email = contact_email
        lead.status = "WON"
        lead.deal_value = amount
        lead.paid_at = now_utc
        lead.install_status = "QUEUED"
        
    await db.commit()
    await db.refresh(lead)
    
    invoice_num = f"INV-DELIV-{lead.id:04d}"
    package_name = "Full Outbound Infrastructure (AED 3,650)" if tier == "outbound" else "Primary Domain Sprint (AED 1,450)"
    
    # Log Agent Event
    event = AgentEvent(
        level="HOT",
        category="ORDER_WON",
        message=f"💰 REVENUE WON: AED {amount:,.2f} from {company_name} ({domain}) for {package_name}!",
        details=f"Invoice: {invoice_num} | Contact: {contact_email} | DNS Host: {dns_provider} | Payment: {payment_method}"
    )
    db.add(event)
    await db.commit()
    
    # Send Telegram alert to Athul
    from services.notifier import notifier
    try:
        tg_msg = (
            f"• *Domain:* {domain}\n"
            f"• *Company:* {company_name}\n"
            f"• *Contact:* {contact_name or 'N/A'} ({contact_email})\n"
            f"• *Package:* {package_name}\n"
            f"• *Amount:* AED {amount:,.2f}\n"
            f"• *DNS Host:* {dns_provider}\n"
            f"• *Payment Method:* {payment_method}\n"
            f"• *Invoice ID:* {invoice_num}\n\n"
            f"Action: Review blueprint & authorize DNS propagation."
        )
        await notifier.notify_all(f"💰 CLIENT ORDER PAID: AED {amount:,.2f}", tg_msg, level="HOT", category="PAYMENT")
    except Exception as e:
        print(f"[Notifier Order Alert Warning]: {e}")
        
    return JSONResponse({
        "status": "SUCCESS",
        "lead_id": lead.id,
        "invoice_num": invoice_num,
        "amount": amount
    })

@app.post("/api/audit-now")
async def api_audit_now(request: Request):
    """Real-time live DNS inspector API for dashboard and programmatic lookups."""
    data = await request.json()
    raw_domain = data.get("domain", "")
    if not raw_domain:
        return JSONResponse({"error": "Domain is required"}, status_code=400)
    
    result = await dns_auditor.audit_domain(raw_domain)
    return JSONResponse(result)

@app.post("/api/actions/prospect-now")
async def api_prospect_now():
    """Manual trigger for autonomous discovery & auditing cycle."""
    res = await job_prospecting_and_auditing()
    return JSONResponse(res)

@app.get("/invoice/{lead_id}", response_class=HTMLResponse)
async def invoice_view(lead_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Checkout & invoice page for turnkey deliverability settlement."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        return HTMLResponse("<h1>Invoice Not Found</h1>", status_code=404)
    
    audit = await db.get(DomainAudit, lead.audit_id) if lead.audit_id else None

    return templates.TemplateResponse(
        request=request,
        name="invoice.html",
        context={
            "settings": settings,
            "lead": lead,
            "audit": audit,
            "invoice_num": f"INV-DELIV-{lead.id:04d}"
        }
    )


@app.get("/api/stats")
async def api_stats(db: AsyncSession = Depends(get_db)):
    """Unified metrics endpoint consumed by the Master Portfolio Dashboard."""
    total_leads = (await db.execute(select(func.count(Lead.id)))).scalar() or 0
    pipeline_val = (await db.execute(
        select(func.sum(Lead.deal_value)).where(Lead.status.in_(["QUALIFIED", "CONTACTED", "FOLLOWUP_1", "FOLLOWUP_2", "REPLIED_INTERESTED"]))
    )).scalar() or 0.0
    active_leads_count = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status.in_(["QUALIFIED", "CONTACTED", "FOLLOWUP_1", "FOLLOWUP_2"]))
    )).scalar() or 0
    actual_revenue = (await db.execute(
        select(func.sum(Lead.deal_value)).where(Lead.status.in_(["WON", "PAID"]))
    )).scalar() or 0.0
    contacted_count = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status.in_(["CONTACTED", "FOLLOWUP_1", "FOLLOWUP_2"]))
    )).scalar() or 0
    hot_leads_count = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status.in_(["REPLIED_INTERESTED", "WON"]))
    )).scalar() or 0
    won_count = (await db.execute(
        select(func.count(Lead.id)).where(Lead.status.in_(["WON", "PAID"]))
    )).scalar() or 0
    paid_count = (await db.execute(
        select(func.count(Lead.id)).where(Lead.paid_at != None)
    )).scalar() or 0
    total_emails = (await db.execute(
        select(func.count(EmailLog.id)).where(EmailLog.status == "SENT")
    )).scalar() or 0
    total_audits = (await db.execute(select(func.count(DomainAudit.id)))).scalar() or 0
    critical_risks = (await db.execute(
        select(func.count(DomainAudit.id)).where(DomainAudit.overall_score < 50)
    )).scalar() or 0
    
    uptime_sec = int((datetime.datetime.utcnow() - START_TIME).total_seconds())
    uptime_human = str(datetime.timedelta(seconds=uptime_sec))

    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "port": settings.PORT,
        "currency": "AED",
        "currency_symbol": "AED",
        "total_leads": total_leads,
        "pipeline_value": pipeline_val,
        "active_leads_count": active_leads_count,
        "actual_revenue": actual_revenue,
        "contacted_count": contacted_count,
        "followups_count": 0,
        "hot_leads_count": hot_leads_count,
        "won_count": won_count,
        "paid_count": paid_count,
        "total_emails": total_emails,
        "total_audits": total_audits,
        "critical_risks": critical_risks,
        "agent_enabled": settings.AGENT_ENABLED,
        "simulation_mode": settings.SIMULATION_MODE,
        "heartbeat_status": "OK",
        "last_ping_time": datetime.datetime.utcnow().isoformat(),
        "latency_ms": 8.5,
        "uptime": uptime_human
    }

@app.get("/api/events")
async def api_events(limit: int = 15, db: AsyncSession = Depends(get_db)):
    """Recent event feed for master portfolio aggregation."""
    res = await db.execute(select(AgentEvent).order_by(desc(AgentEvent.id)).limit(limit))
    events = res.scalars().all()
    return [
        {
            "id": e.id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else "",
            "level": e.level,
            "category": e.category,
            "message": e.message,
            "details": e.details
        }
        for e in events
    ]

@app.post("/api/actions/followups-now")
async def api_followups_now():
    """Manual trigger for autonomous follow-up sequences."""
    from services.scheduler import job_followup_cycle
    count = await job_followup_cycle()
    return JSONResponse({"status": "SUCCESS", "dispatched_count": count})

@app.post("/api/webhooks/inbound-reply")
@app.post("/api/webhooks/brevo")
async def webhook_inbound_reply(request: Request, db: AsyncSession = Depends(get_db)):
    """Inbound email webhook listener for Brevo or IMAP dispatchers."""
    data = await request.json()
    sender = data.get("sender") or data.get("From") or (data.get("items", [{}])[0].get("from", {}).get("email") if "items" in data else "")
    subject = data.get("subject") or data.get("Subject") or ""
    body = data.get("body") or data.get("text") or data.get("textContent") or ""
    
    from services.inbound_poller import process_inbound_reply
    result = await process_inbound_reply(db, sender=str(sender), subject=str(subject), body=str(body), source="BREVO_WEBHOOK")
    return JSONResponse(result)

@app.post("/api/leads/{lead_id}/simulate-reply")
async def simulate_lead_reply(lead_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Simulates an inbound response to verify auto-replies, notifications, and pipeline transitions."""
    data = await request.json()
    reply_text = data.get("reply_text", "We reviewed the DNS audit. Our IT team confirmed the DMARC record is missing. Please send the fix blueprint and invoice.")
    lead = await db.get(Lead, lead_id)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    
    from services.inbound_poller import process_inbound_reply
    res = await process_inbound_reply(
        db,
        sender=lead.contact_email,
        subject=f"Re: Deliverability Audit - {lead.domain}",
        body=reply_text,
        source="DASHBOARD_SIMULATION"
    )
    return JSONResponse(res)

@app.post("/api/leads/{lead_id}/mark-paid")
async def mark_lead_paid(lead_id: int, db: AsyncSession = Depends(get_db)):
    """Marks invoice paid and triggers automated Telegram confirmation."""
    lead = await db.get(Lead, lead_id)
    if not lead:
        return JSONResponse({"error": "Lead not found"}, status_code=404)
    
    lead.status = "WON"
    lead.paid_at = datetime.datetime.utcnow()
    lead.install_status = "INSTALLED"
    
    from services.notifier import notifier
    await notifier.alert_payment(company=lead.company_name, amount=lead.deal_value, invoice_id=f"INV-DELIV-{lead.id:04d}")
    await db.commit()
    return JSONResponse({"status": "SUCCESS", "lead_id": lead.id, "amount": lead.deal_value})

