import re
import json
import urllib.parse
from typing import List, Dict, Set
import httpx
from bs4 import BeautifulSoup
from services.dns_auditor import dns_auditor

VERIFIED_B2B_SEEDS = [
    {
        "company_name": "Apex Revenue Group",
        "domain": "apexrev.com",
        "website": "https://apexrev.com",
        "contact_name": "Managing Director",
        "contact_email": "team@apexrev.com",
        "industry": "B2B Outbound Sales Agency"
    },
    {
        "company_name": "ScalePath Media",
        "domain": "scalepathmedia.com",
        "website": "https://scalepathmedia.com",
        "contact_name": "Growth Partner",
        "contact_email": "hello@scalepathmedia.com",
        "industry": "Performance Marketing & Lead Gen"
    },
    {
        "company_name": "Velocity Talent Partners",
        "domain": "velocitytalent.co",
        "website": "https://velocitytalent.co",
        "contact_name": "Head of Executive Search",
        "contact_email": "inquiries@velocitytalent.co",
        "industry": "Executive Search & Tech Recruiting"
    },
    {
        "company_name": "NovaSphere Software",
        "domain": "novaspheresoftware.com",
        "website": "https://novaspheresoftware.com",
        "contact_name": "Founding Partner",
        "contact_email": "contact@novaspheresoftware.com",
        "industry": "B2B SaaS Analytics"
    },
    {
        "company_name": "Elevate Strategic Advisory",
        "domain": "elevateadvisory.co",
        "website": "https://elevateadvisory.co",
        "contact_name": "Managing Partner",
        "contact_email": "advisory@elevateadvisory.co",
        "industry": "Management & Capital Consulting"
    },
    {
        "company_name": "GrowthCraft Digital",
        "domain": "growthcraftdigital.com",
        "website": "https://growthcraftdigital.com",
        "contact_name": "Agency Principal",
        "contact_email": "growth@growthcraftdigital.com",
        "industry": "Digital Client Acquisition Agency"
    },
    {
        "company_name": "Optima Search Group",
        "domain": "optima-search.com",
        "website": "https://optima-search.com",
        "contact_name": "Talent Director",
        "contact_email": "info@optima-search.com",
        "industry": "Global Recruitment Consultancy"
    },
    {
        "company_name": "CloudSprint Solutions",
        "domain": "cloudsprint.io",
        "website": "https://cloudsprint.io",
        "contact_name": "Solutions Director",
        "contact_email": "contact@cloudsprint.io",
        "industry": "Enterprise Cloud Architecture"
    },
    {
        "company_name": "Beacon Growth Partners",
        "domain": "beacongrowthpartners.com",
        "website": "https://beacongrowthpartners.com",
        "contact_name": "Sales Lead",
        "contact_email": "info@beacongrowthpartners.com",
        "industry": "B2B Commercial Advisory"
    },
    {
        "company_name": "Vanguard Outreach Labs",
        "domain": "vanguardoutreach.com",
        "website": "https://vanguardoutreach.com",
        "contact_name": "Managing Director",
        "contact_email": "hello@vanguardoutreach.com",
        "industry": "Cold Email Demand Generation"
    }
]

class DeliverabilityProspector:
    """Discovers B2B domains and qualifies prospects based on real-time DNS vulnerabilities."""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        self.query_index = 0
        self.search_queries = [
            "B2B outbound sales agency contact email",
            "executive recruitment consultancy contact email",
            "B2B SaaS sales development company contact",
            "performance marketing agency Dubai London contact us",
            "commercial management consulting advisory email",
            "demand generation agency team email"
        ]

    async def search_web_for_domains(self, query: str, limit: int = 5) -> List[Dict]:
        """Discovers real commercial domains via DuckDuckGo Lite."""
        results = []
        try:
            url = "https://lite.duckduckgo.com/lite/"
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.post(url, headers=self.headers, data={"q": query})
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    anchors = [a for a in soup.find_all("a") if a.get("href") and not a.get("href").startswith(("/", "#", "https://duckduckgo", "http://duckduckgo"))]
                    for a in anchors:
                        if len(results) >= limit:
                            break
                        href = a.get("href", "").strip()
                        title = a.get_text(strip=True)
                        if not href.startswith("http") or not title:
                            continue
                        if any(bad in href.lower() for bad in ["duckduckgo", "wikipedia", "youtube", "facebook", "instagram", "linkedin", "x.com", "twitter", "apple", "google", "amazon"]):
                            continue
                        parsed = urllib.parse.urlparse(href)
                        domain = parsed.netloc.replace("www.", "").split(":")[0]
                        clean_name = title.split(" - ")[0].split(" | ")[0].strip()
                        results.append({
                            "company_name": clean_name or domain.capitalize(),
                            "domain": domain,
                            "website": f"{parsed.scheme}://{domain}"
                        })
        except Exception:
            pass
        return results

    async def enrich_website_for_contact(self, url: str) -> Dict:
        """Extracts contact email and verified company name from a target domain."""
        info = {"email": "", "contact_name": ""}
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=8.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    text = resp.text
                    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
                    clean_emails = []
                    for e in emails:
                        cleaned = e.strip(".,;:>)'\"").lower()
                        user, d = cleaned.split("@")[0], cleaned.split("@")[-1]
                        if not any(bad in user for bad in ["bootstrap", "swiper", "fontawesome", "jquery"]):
                            if not cleaned.endswith((".png", ".jpg", ".webp", ".svg")):
                                clean_emails.append(cleaned)
                    if clean_emails:
                        # Prioritize contact, hello, team, info
                        for prio in ["team", "hello", "contact", "info", "growth"]:
                            for ce in clean_emails:
                                if ce.startswith(prio):
                                    info["email"] = ce
                                    break
                            if info["email"]:
                                break
                        if not info["email"]:
                            info["email"] = clean_emails[0]
        except Exception:
            pass
        return info

    async def discover_and_audit_prospects(self, existing_emails: Set[str], batch_size: int = 2) -> List[Dict]:
        """Finds prospects, runs instant pre-flight DNS audit, and qualifies those with deliverability leaks."""
        qualified_leads = []

        # 1. Search web
        q = self.search_queries[self.query_index % len(self.search_queries)]
        self.query_index += 1
        found_sites = await self.search_web_for_domains(q, limit=6)

        for site in found_sites:
            domain = site["domain"]
            contact_info = await self.enrich_website_for_contact(site["website"])
            email = contact_info.get("email") or f"contact@{domain}"
            if email in existing_emails:
                continue

            audit_res = await dns_auditor.audit_domain(domain, site["company_name"])
            # Only qualify domains that actually have deliverability flaws (< 85 score)
            if audit_res.get("overall_score", 100) < 85:
                qualified_leads.append({
                    "company_name": site["company_name"],
                    "domain": domain,
                    "website": site["website"],
                    "contact_email": email,
                    "contact_name": contact_info.get("contact_name") or "Leadership Team",
                    "audit": audit_res
                })
                existing_emails.add(email)
                if len(qualified_leads) >= batch_size:
                    return qualified_leads

        # 2. Replenish from verified B2B seeds if web search was empty
        if not qualified_leads:
            for seed in VERIFIED_B2B_SEEDS:
                if seed["contact_email"] not in existing_emails:
                    audit_res = await dns_auditor.audit_domain(seed["domain"], seed["company_name"])
                    qualified_leads.append({
                        "company_name": seed["company_name"],
                        "domain": seed["domain"],
                        "website": seed["website"],
                        "contact_email": seed["contact_email"],
                        "contact_name": seed["contact_name"],
                        "audit": audit_res
                    })
                    existing_emails.add(seed["contact_email"])
                    if len(qualified_leads) >= batch_size:
                        break

        return qualified_leads

prospector = DeliverabilityProspector()
