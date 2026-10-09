import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "OmniDeliverability AI"
    APP_VERSION: str = "2.0.0"
    PORT: int = 8686
    HOST: str = "0.0.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = f"sqlite+aiosqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), 'deliverability_agent.db').replace(chr(92), '/')}"

    
    # Public URL
    PUBLIC_APP_URL: str = "http://127.0.0.1:8686"
    
    # Offering
    OFFERING_NAME: str = "24/7 B2B Inbound Deliverability & Domain Reputation Shield"
    OFFERING_DESCRIPTION: str = "Turnkey Google/Yahoo 2024+ DNS Authentication (SPF, DKIM, DMARC), Secondary Outbound Domain Isolation, and Spam Infiltration Prevention."
    DEFAULT_DEAL_VALUE: float = 1450.0 # AED 1,450
    INFRASTRUCTURE_DEAL_VALUE: float = 3650.0 # AED 3,650

    
    # Operator
    OPERATOR_NAME: str = "Athul raj"
    OPERATOR_TITLE: str = "Email Deliverability & Infrastructure Specialist"
    OPERATOR_EMAIL: str = "athulaisolutions@gmail.com"
    OPERATOR_TELEGRAM: str = "@dreamer_comrade"
    OPERATOR_WHATSAPP: str = ""

    
    # SMTP / Brevo
    SMTP_ENABLED: bool = True
    SMTP_HOST: str = "smtp-relay.brevo.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = "8722c3001@smtp-brevo.com"
    SMTP_PASSWORD: str = "" # Will read from env or database
    FROM_EMAIL: str = "athulaisolutions@gmail.com"
    FROM_NAME: str = "Athul - Deliverability Specialist"
    
    # Limits & Timing
    MAX_DAILY_EMAILS: int = 50
    AUDIT_FOLLOWUP_DAYS: int = 3
    AGENT_ENABLED: bool = True
    SIMULATION_MODE: bool = False
    HEALTH_PING_INTERVAL_MINUTES: int = 5
    
    # Notification Services
    NOTIFY_TELEGRAM: bool = True
    TELEGRAM_BOT_TOKEN: str = "8706330311:AAFpYrvU3kmVVQOHEkYvDHS5WwGQmA_t8yU"
    TELEGRAM_CHAT_ID: str = "@dreamer_comrade"
    
    # Inbound IMAP Polling (Gmail reply capture)
    IMAP_ENABLED: bool = True
    IMAP_HOST: str = "imap.gmail.com"
    IMAP_PORT: int = 993
    IMAP_USER: str = "athulaisolutions@gmail.com"
    IMAP_PASSWORD: str = ""
    IMAP_INTERVAL_MINUTES: int = 2
    
    # Heartbeat
    HEARTBEAT_ENABLED: bool = True
    HEARTBEAT_PING_URL: str = "https://hc-ping.com/demo-deliverability-uuid"

    # AI Copywriting
    GEMINI_API_KEY: str = ""
    AI_MODEL: str = "gemini-2.5-flash"
    
    class Config:
        env_file = ".env"
        extra = "allow"

VALID_DEFAULT_BREVO_KEY = os.environ.get("SMTP_PASSWORD", "")

settings = Settings()
if not settings.SMTP_PASSWORD or "lH8o2h" in settings.SMTP_PASSWORD or "aeRqkQRo" in settings.SMTP_PASSWORD:
    settings.SMTP_PASSWORD = VALID_DEFAULT_BREVO_KEY
if not settings.SMTP_USER or settings.SMTP_USER == "8722c3001@smtp-brevo.com":
    settings.SMTP_USER = "athulaisolutions@gmail.com"
    settings.FROM_EMAIL = "athulaisolutions@gmail.com"
    settings.SMTP_ENABLED = True

if os.environ.get("RENDER_EXTERNAL_URL"):
    settings.PUBLIC_APP_URL = os.environ.get("RENDER_EXTERNAL_URL").rstrip("/")

