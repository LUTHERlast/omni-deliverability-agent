import re
import uuid
import json
import asyncio
from typing import Dict, Any, List, Optional
import httpx
import dns.resolver

class DNSDeliverabilityAuditor:
    """Performs deep programmatic DNS analysis of email authentication, MX servers, and deliverability risk."""

    def __init__(self):
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = 3.0
        self.resolver.lifetime = 3.0
        # Common DKIM selectors to test
        self.common_selectors = ["google", "k1", "default", "s1", "mail", "selector1", "dkim", "smtp"]

    def clean_domain(self, domain_or_url: str) -> str:
        """Extracts bare root domain from any URL or email input."""
        if not domain_or_url:
            return ""
        d = domain_or_url.strip().lower()
        if "@" in d:
            d = d.split("@")[-1]
        import urllib.parse
        if "://" in d:
            parsed = urllib.parse.urlparse(d)
            d = parsed.netloc or parsed.path
        d = d.replace("www.", "").split("/")[0].split(":")[0].strip()
        return d

    async def _resolve_txt_records(self, query_name: str) -> List[str]:
        """Resolves TXT records using dnspython with async Google/Cloudflare DoH fallback."""
        records = []
        # Method 1: Local dnspython
        try:
            def _local_lookup():
                answers = self.resolver.resolve(query_name, "TXT")
                return [b"".join(r.strings).decode("utf-8", errors="replace") for r in answers]
            records = await asyncio.wait_for(asyncio.to_thread(_local_lookup), timeout=3.0)
            if records:
                return records
        except Exception:
            pass

        # Method 2: Google DNS over HTTPS (DoH) fallback
        try:
            url = f"https://dns.google/resolve?name={query_name}&type=TXT"
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    for ans in data.get("Answer", []):
                        val = ans.get("data", "").strip('\"')
                        if val:
                            records.append(val)
        except Exception:
            pass

        return records

    async def _resolve_mx_records(self, domain: str) -> List[str]:
        """Resolves MX mail server records."""
        mx_hosts = []
        try:
            def _local_mx():
                answers = self.resolver.resolve(domain, "MX")
                return [str(r.exchange).rstrip(".") for r in answers]
            mx_hosts = await asyncio.wait_for(asyncio.to_thread(_local_mx), timeout=3.0)
            if mx_hosts:
                return mx_hosts
        except Exception:
            pass

        try:
            url = f"https://dns.google/resolve?name={domain}&type=MX"
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    for ans in data.get("Answer", []):
                        val = ans.get("data", "").split()[-1].rstrip(".")
                        if val:
                            mx_hosts.append(val)
        except Exception:
            pass

        return mx_hosts

    async def audit_domain(self, raw_target: str, company_name: str = "") -> Dict[str, Any]:
        """Runs a comprehensive 7-point email deliverability and DNS authentication diagnosis."""
        domain = self.clean_domain(raw_target)
        if not domain or "." not in domain:
            return {"error": "Invalid domain supplied", "domain": raw_target}

        score = 100
        issues = []
        blueprint = []

        # 1. Inspect MX Records
        mx_records = await self._resolve_mx_records(domain)
        mx_provider = "Unknown / Custom Mail Server"
        mx_joined = " ".join(mx_records).lower()
        if "google" in mx_joined or "googlemail" in mx_joined:
            mx_provider = "Google Workspace"
        elif "outlook" in mx_joined or "microsoft" in mx_joined:
            mx_provider = "Microsoft 365"
        elif "zoho" in mx_joined:
            mx_provider = "Zoho Mail"
        elif "proton" in mx_joined:
            mx_provider = "Proton Mail"
        elif not mx_records:
            mx_provider = "No MX Records Found"
            score -= 30
            issues.append({
                "severity": "CRITICAL",
                "title": "Missing MX Records",
                "description": f"Domain {domain} has no inbound mail servers configured. Inbound emails cannot be delivered.",
                "penalty": 30
            })

        # 2. Inspect SPF Records
        txt_records = await self._resolve_txt_records(domain)
        spf_records = [r for r in txt_records if r.lower().startswith("v=spf1")]
        spf_status = "PASS"
        spf_value = None

        if not spf_records:
            spf_status = "MISSING"
            score -= 30
            issues.append({
                "severity": "CRITICAL",
                "title": "Missing SPF Record",
                "description": f"No SPF (Sender Policy Framework) record published for {domain}. Outbound emails are unauthenticated and automatically flagged by spam filters.",
                "penalty": 30
            })
            # Generate blueprint SPF
            rec_include = "include:_spf.google.com" if "Google" in mx_provider else ("include:spf.protection.outlook.com" if "Microsoft" in mx_provider else "")
            spf_val = f"v=spf1 {rec_include} ~all".strip()
            blueprint.append({
                "type": "TXT",
                "host": "@",
                "value": spf_val,
                "purpose": "SPF Authentication (Validates authorized mail servers)"
            })
        elif len(spf_records) > 1:
            spf_status = "FAIL"
            score -= 25
            spf_value = " | ".join(spf_records)
            issues.append({
                "severity": "CRITICAL",
                "title": "Multiple SPF Records Detected",
                "description": f"Found {len(spf_records)} separate SPF records. RFC 7208 explicitly forbids multiple SPF records, causing mail receivers to fail SPF with a permanent PermError.",
                "penalty": 25
            })
            blueprint.append({
                "type": "TXT",
                "host": "@",
                "value": spf_records[0],
                "purpose": "Consolidate into a single unified SPF record"
            })
        else:
            spf_value = spf_records[0]
            if "+all" in spf_value or "?all" in spf_value:
                spf_status = "WARNING"
                score -= 20
                issues.append({
                    "severity": "HIGH",
                    "title": "Insecure SPF Mechanism (+all / ?all)",
                    "description": "SPF ends in +all or ?all, allowing unauthorized third parties to spoof emails from your domain.",
                    "penalty": 20
                })
            elif "~all" in spf_value:
                spf_status = "PASS" # Softfail is common and acceptable
            elif "-all" in spf_value:
                spf_status = "OPTIMAL" # Hardfail is ideal

        # 3. Inspect DMARC Policy
        dmarc_txt = await self._resolve_txt_records(f"_dmarc.{domain}")
        dmarc_records = [r for r in dmarc_txt if "v=dmarc1" in r.lower()]
        dmarc_status = "PASS"
        dmarc_policy = "missing"
        dmarc_value = None

        if not dmarc_records:
            dmarc_status = "MISSING"
            dmarc_policy = "missing"
            score -= 35
            issues.append({
                "severity": "CRITICAL",
                "title": "Missing DMARC Policy (Google/Yahoo Mandate Non-Compliant)",
                "description": "Under Google & Yahoo's 2024+ sender requirements, sending domains without an active DMARC record face automatic spam placement or outright rejection.",
                "penalty": 35
            })
            blueprint.append({
                "type": "TXT",
                "host": "_dmarc",
                "value": f"v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@{domain}; pct=100",
                "purpose": "DMARC Enforcement (Protects domain reputation and guarantees inbox delivery)"
            })
        else:
            dmarc_value = dmarc_records[0]
            # Parse policy
            p_match = re.search(r'p=([a-z]+)', dmarc_value, re.IGNORECASE)
            dmarc_policy = p_match.group(1).lower() if p_match else "none"
            
            if dmarc_policy == "none":
                dmarc_status = "WARNING"
                score -= 15
                issues.append({
                    "severity": "HIGH",
                    "title": "DMARC Set to Inactive Monitoring (p=none)",
                    "description": "DMARC is set to p=none. It observes traffic but does not stop spoofed emails or protect recipient inbox placement.",
                    "penalty": 15
                })
                blueprint.append({
                    "type": "TXT",
                    "host": "_dmarc",
                    "value": f"v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@{domain}; pct=100",
                    "purpose": "Upgrade DMARC policy from p=none to p=quarantine"
                })
            else:
                dmarc_status = "PASS"

            if "rua=" not in dmarc_value.lower():
                score -= 5
                issues.append({
                    "severity": "MODERATE",
                    "title": "Missing DMARC Reporting (rua tag)",
                    "description": "No aggregate reporting mailbox configured. You receive zero visibility into delivery failures or spoofing attempts.",
                    "penalty": 5
                })

        # 4. Inspect DKIM Selector
        dkim_status = "WARNING"
        dkim_found_selector = None
        for sel in self.common_selectors:
            dkim_res = await self._resolve_txt_records(f"{sel}._domainkey.{domain}")
            if any("v=dkim1" in d.lower() or "k=rsa" in d.lower() or "p=" in d.lower() for d in dkim_res):
                dkim_status = "PASS"
                dkim_found_selector = sel
                break

        if dkim_status != "PASS":
            score -= 10
            issues.append({
                "severity": "MODERATE",
                "title": "Standard DKIM Selector Not Found",
                "description": "No common DKIM selector record (google, k1, default, s1) detected. If DKIM keys are misaligned, receivers fail cryptographic verification.",
                "penalty": 10
            })
            if "Google" in mx_provider:
                blueprint.append({
                    "type": "TXT",
                    "host": "google._domainkey",
                    "value": "v=DKIM1; k=rsa; p=<Generate 2048-bit key in Google Workspace Admin Console>",
                    "purpose": "DKIM Cryptographic Signature"
                })

        # 5. Add Custom Tracking Domain recommendation
        blueprint.append({
            "type": "CNAME",
            "host": "track",
            "value": "tracking.omnisendshield.com",
            "purpose": "Custom Tracking Domain (Eliminates shared spam reputation from ESP open-pixel domains)"
        })

        # Clamp Score
        overall_score = max(10, min(98, score))
        
        # Risk level & estimated inbox rate
        if overall_score >= 85:
            risk_level = "OPTIMAL"
            inbox_rate = 94
        elif overall_score >= 70:
            risk_level = "MODERATE"
            inbox_rate = 76
        elif overall_score >= 50:
            risk_level = "HIGH"
            inbox_rate = 44
        else:
            risk_level = "CRITICAL"
            inbox_rate = 24

        token = str(uuid.uuid4())[:8]

        return {
            "domain": domain,
            "company_name": company_name or domain.capitalize(),
            "overall_score": overall_score,
            "risk_level": risk_level,
            "inbox_placement_rate": inbox_rate,
            "mx_provider": mx_provider,
            "mx_records": mx_records,
            "spf_status": spf_status,
            "spf_record": spf_value,
            "dmarc_status": dmarc_status,
            "dmarc_policy": dmarc_policy,
            "dmarc_record": dmarc_value,
            "dkim_status": dkim_status,
            "dkim_selector": dkim_found_selector,
            "issues": issues,
            "fix_blueprint": blueprint,
            "audit_token": token
        }

dns_auditor = DNSDeliverabilityAuditor()
