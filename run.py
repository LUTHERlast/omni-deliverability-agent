import sys
import uvicorn
from config import settings

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    print("=" * 65)
    print(f"[*] Launching {settings.APP_NAME} (Deliverability Engine)")
    print(f"[*] Dashboard & Command Center: http://127.0.0.1:{settings.PORT}")
    print(f"[*] Health & Diagnostic API:   http://127.0.0.1:{settings.PORT}/api/health")
    print(f"[*] Port:                      {settings.PORT}")
    print(f"[*] SMTP Relay Mode:           {'Real SMTP' if settings.SMTP_ENABLED else 'Simulation'}")
    import os
    port = int(os.environ.get("PORT", settings.PORT))
    host = os.environ.get("HOST", settings.HOST)
    uvicorn.run("web.app:app", host=host, port=port, reload=False)
