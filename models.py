import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Boolean
from database import Base

class DomainAudit(Base):
    __tablename__ = "domain_audits"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), index=True, nullable=False)
    company_name = Column(String(255), nullable=True)
    website = Column(String(500), nullable=True)
    contact_email = Column(String(255), nullable=True)
    
    overall_score = Column(Integer, default=50) # 0-100
    risk_level = Column(String(50), default="HIGH") # CRITICAL, HIGH, MODERATE, OPTIMAL
    inbox_placement_rate = Column(Integer, default=35) # e.g. 35%
    
    spf_status = Column(String(50), default="MISSING")
    spf_record = Column(Text, nullable=True)
    
    dkim_status = Column(String(50), default="MISSING")
    dkim_selector = Column(String(100), nullable=True)
    
    dmarc_status = Column(String(50), default="MISSING")
    dmarc_policy = Column(String(50), default="missing")
    dmarc_record = Column(Text, nullable=True)
    
    mx_provider = Column(String(100), default="Unknown")
    blacklist_status = Column(String(50), default="CLEAN")
    
    issues_json = Column(Text, default="[]") # JSON list of detected flaws
    fix_blueprint_json = Column(Text, default="[]") # JSON list of DNS records to add
    
    audit_token = Column(String(100), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), index=True, nullable=False)
    company_name = Column(String(255), nullable=False)
    contact_name = Column(String(255), nullable=True)
    contact_email = Column(String(255), index=True, nullable=False)
    phone = Column(String(100), nullable=True)
    
    status = Column(String(50), default="QUALIFIED") # QUALIFIED, CONTACTED, FOLLOWUP_1, FOLLOWUP_2, REPLIED_INTERESTED, WON, BOUNCED, UNSUBSCRIBED
    audit_id = Column(Integer, ForeignKey("domain_audits.id"), nullable=True)
    qualification_score = Column(Integer, default=85)
    deal_value = Column(Float, default=397.0)
    
    emails_sent_count = Column(Integer, default=0)
    last_contacted_at = Column(DateTime, nullable=True)
    next_followup_at = Column(DateTime, nullable=True)
    reply_sentiment = Column(String(50), nullable=True)
    
    paid_at = Column(DateTime, nullable=True)
    install_status = Column(String(50), default="PENDING")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class EmailLog(Base):
    __tablename__ = "email_logs"

    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True)
    domain = Column(String(255), nullable=True)
    sequence_stage = Column(String(50), default="INITIAL") # INITIAL, FOLLOWUP_1, FOLLOWUP_2, FOLLOWUP_3
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    recipient_email = Column(String(255), nullable=False)
    status = Column(String(50), default="SENT")
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)
    error_message = Column(Text, nullable=True)

class AgentEvent(Base):
    __tablename__ = "agent_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    level = Column(String(50), default="INFO")
    category = Column(String(50), default="SYSTEM")
    message = Column(String(500), nullable=False)
    details = Column(Text, nullable=True)
