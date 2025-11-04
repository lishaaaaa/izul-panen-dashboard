# api/index.py
import os
from serverless_wsgi import handle_request
from app import app  # pastikan di app.py ada: app = Flask(__name__)

# tulis kredensial SA ke path dari ENV (Vercel: /tmp)
CREDS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/service_account.json")
JSON_ENV = os.getenv("GOOGLE_CREDENTIALS_JSON")
if JSON_ENV and not os.path.exists(CREDS_PATH):
    os.makedirs(os.path.dirname(CREDS_PATH), exist_ok=True)
    with open(CREDS_PATH, "w", encoding="utf-8") as f:
        f.write(JSON_ENV)

def handler(request, context):
    return handle_request(app, request, context)
