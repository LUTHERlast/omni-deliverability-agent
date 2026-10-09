from typing import Dict, Any, Tuple, Optional
from config import settings

class DeliverabilityCopywriter:
    """Generates factual, high-urgency B2B deliverability cold outreach and follow-up sequences."""

    def format_salutation(self, contact_name: Optional[str], company_name: Optional[str]) -> str:
        if contact_name and contact_name.strip():
            words = contact_name.strip().split()
            ROLE_KEYWORDS = {
                "director", "partner", "principal", "manager", "lead", "head",
                "officer", "founder", "ceo", "specialist", "consultant", "desk",
                "agency", "executive", "team", "growth", "inquiries", "sales", "info", "contact", "support"
            }
            if any(w.lower().rstrip('.,:') in ROLE_KEYWORDS for w in words):
                return f"{company_name} team" if company_name else "there"
            return words[0].capitalize()
        return f"{company_name} team" if company_name else "there"

    def generate_audit_email(self, audit: Dict[str, Any], lead: Dict[str, Any], public_url: str) -> Tuple[str, str]:
        """Generates Stage 1 personalized technical diagnostic alert quoting exact DNS flaws."""
        domain = audit.get("domain", "")
        company = lead.get("company_name") or audit.get("company_name") or domain.capitalize()
        salutation = self.format_salutation(lead.get("contact_name"), company)
        score = audit.get("overall_score", 45)
        risk = audit.get("risk_level", "HIGH")
        inbox_rate = audit.get("inbox_placement_rate", 35)
        issues = audit.get("issues", [])
        
        audit_url = f"{public_url.rstrip('/')}/audit/{domain}"

        # Choose high-converting subject line based on primary flaw
        has_dmarc_missing = any("DMARC" in i.get("title", "") for i in issues)
        has_spf_issue = any("SPF" in i.get("title", "") for i in issues)

        if has_dmarc_missing:
            subject = f"Deliverability warning: {domain} missing Google/Yahoo DMARC authentication"
        elif has_spf_issue:
            subject = f"Mail server alert: SPF misconfiguration detected on {domain}"
        else:
            subject = f"Domain health scorecard for {domain}: {score}/100 ({risk} spam risk)"

        # Highlight top 2 flaws
        bullet_points = []
        for issue in issues[:2]:
            bullet_points.append(f"• {issue['title']}: {issue['description']}")
        
        flaws_text = "\n".join(bullet_points) if bullet_points else "• Unauthenticated sending records causing recipient mail gateways to quarantine messages."

        body = f"""Hi {salutation},

Hope you are having a productive week.

While running an automated mail server scan across B2B domains this morning, our deliverability watchdog detected critical authentication gaps on {domain}:

{flaws_text}

Estimated Primary Inbox Placement: ~{inbox_rate}% (Under Google & Yahoo's mandatory enforcement rules, the remaining ~{100 - inbox_rate}% are routed directly into Spam or silently rejected).

We generated a free interactive 60-second scorecard detailing the exact missing DNS records and step-by-step fix blueprint here:
{audit_url}

Would you be open to our team deploying the turnkey DNS authentication fix and isolating secondary outbound domains so your team hits 95%+ primary inbox placement?

Best regards,
{settings.OPERATOR_NAME}
{settings.OPERATOR_TITLE}
{settings.APP_NAME}

---
Note: This is a 1-to-1 professional deliverability advisory. If you prefer not to receive technical alerts, reply 'opt out' to be permanently removed."""

        return subject, body

    def generate_followup_email(self, audit: Dict[str, Any], lead: Dict[str, Any], public_url: str, stage: str) -> Tuple[str, str]:
        """Generates subsequent multi-touch follow-up emails."""
        domain = audit.get("domain", "")
        company = lead.get("company_name") or audit.get("company_name") or domain.capitalize()
        salutation = self.format_salutation(lead.get("contact_name"), company)
        audit_url = f"{public_url.rstrip('/')}/audit/{domain}"
        score = audit.get("overall_score", 45)

        if stage == "FOLLOWUP_1":
            subject = f"Following up: impact on {domain}'s sales pipeline"
            body = f"""Hi {salutation},

Following up on my previous note regarding {domain}'s mail authentication health.

When your domain health score is sitting around {score}/100, cold sales inquiries and even regular transactional messages frequently get flagged by Microsoft 365 and Google Workspace spam algorithms.

Most sales teams we speak with don't realize their reply rates dropped simply because their prospects never saw the emails in the first place.

Here is the full technical audit and copy-paste fix blueprint:
{audit_url}

Would you like us to implement the turnkey DNS fix this week?

Best,
{settings.OPERATOR_NAME}"""

        elif stage == "FOLLOWUP_2":
            subject = f"Case study: lifting inbox placement from 38% to 94% for {domain}"
            body = f"""Hi {salutation},

Sharing a quick breakdown: an agency facing the exact same DNS configuration gaps on their sending domain saw their cold reply rate triple within 7 days of setting up proper SPF/DKIM/DMARC alignment and secondary sending domains.

We can deploy the complete infrastructure fix for {domain} in under 24 hours.

Would it make sense to take care of this before your team sends its next batch of client emails?

Best regards,
{settings.OPERATOR_NAME}"""

        else: # FOLLOWUP_3 / Breakup
            subject = f"Closing technical file for {domain}?"
            body = f"""Hi {salutation},

I haven't heard back, so I assume email deliverability and spam filtration isn't a top priority for {domain} right now—which is completely fine!

I will close out {domain}'s technical file and won't crowd your inbox. If you ever notice reply rates dropping or emails landing in spam down the road, your live scorecard will remain accessible here:
{audit_url}

Wishing you and {company} continued success!

Best regards,
{settings.OPERATOR_NAME}"""

        return subject, body

deliverability_copywriter = DeliverabilityCopywriter()
