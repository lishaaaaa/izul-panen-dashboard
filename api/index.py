from serverless_wsgi import handle_request
from app import app as flask_app

# Vercel akan memanggil fungsi ini
def handler(event, context):
    return handle_request(flask_app, event, context)
