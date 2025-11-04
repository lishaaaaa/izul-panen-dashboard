import os, sys, traceback
from serverless_wsgi import handle_request

def _ensure_creds():
    p = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/service_account.json")
    j = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if j and not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(j)

def handler(request, context):
    try:
        _ensure_creds()
        from app import app  # lazy import biar errornya keliatan jelas di logs
        return handle_request(app, request, context)
    except Exception as e:
        print("🔥 Serverless crash in handler:", e, file=sys.stderr)
        traceback.print_exc()
        return {"statusCode": 500, "body": "Internal error. Check Runtime Logs."}
