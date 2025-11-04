# api/index.py
import os, sys, traceback
from serverless_wsgi import handle_request
from app import app

def _ensure_creds():
    p = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/service_account.json")
    j = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if j and not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(j)

# minimal health biar gampang ping
try:
    @app.get("/health")
    def _health(): return "ok", 200
except Exception:
    pass

def handler(request, context):
    try:
        _ensure_creds()
        return handle_request(app, request, context)
    except Exception as e:
        print("🔥 Serverless crash:", e, file=sys.stderr)
        traceback.print_exc()
        return {"statusCode": 500, "body": "Internal error. Check Runtime Logs."}

