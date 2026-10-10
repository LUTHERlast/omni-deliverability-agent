# 🛡️ OmniDeliverability AI

**Autonomous B2B Cold Email Deliverability, Domain Authentication & DNS Infrastructure Agent**

---

## ⚡ Core Capabilities
1. **Autonomous Lead Discovery**: Continuously discovers active B2B companies, SaaS platforms, recruitment agencies, and consulting firms.
2. **Instant Programmatic DNS Auditing**: Inspects SPF syntax, Google/Yahoo 2024 DMARC policies, DKIM alignment, and MX mail servers in <500ms using `dnspython` and DNS-over-HTTPS.
3. **Dynamic Interactive Scorecards**: Generates public, client-facing scorecards at `/audit/{domain}` with radial score meters, critical vulnerability warnings, and exact DNS fix blueprints.
4. **1-Click Async Checkout**: Clients authorize turnkey deployment directly at `/checkout/{domain}` with instant invoice issuance at `/invoice/{id}`.
5. **Unified Master Fleet Integration**: Fully connects to `/master` multi-agent portfolio dashboard.
6. **Pure AED Financial Accounting**: All deal sizes, pipelines, and invoices standardized in UAE Dirhams (**AED 1,450** for Primary Domain Sprint, **AED 3,650** for Full Outbound Infrastructure).

---

## 🚀 Cloud Deployment (Render & Web)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/LUTHERlast/omni-deliverability-agent)

This repository includes a turnkey `render.yaml` Blueprint.

### 1. One-Click Instant Deployment
1. Click the **Deploy to Render** button above, or open:  
   👉 **[https://render.com/deploy?repo=https://github.com/LUTHERlast/omni-deliverability-agent](https://render.com/deploy?repo=https://github.com/LUTHERlast/omni-deliverability-agent)**
2. Select **New + -> Blueprint** or **New Web Service**.
3. Render will automatically detect `render.yaml` and configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python run.py`
   - **Health Check Path**: `/api/health`
4. Set your environment variable:
   - `SMTP_PASSWORD`: `<your-brevo-smtp-key>` (Brevo API key from Brevo SMTP Settings)

---

## 💻 Local Quickstart

```bash
# Install dependencies
pip install -r requirements.txt

# Launch Agent Daemon
python run.py
```

* **Command Center Dashboard**: [http://127.0.0.1:8686](http://127.0.0.1:8686)
* **Unified Master Fleet Dashboard**: [http://127.0.0.1:8686/master](http://127.0.0.1:8686/master)
* **Live Domain Audit Scorecard**: [http://127.0.0.1:8686/audit/apexrev.com](http://127.0.0.1:8686/audit/apexrev.com)
* **System Health Endpoint**: [http://127.0.0.1:8686/api/health](http://127.0.0.1:8686/api/health)
