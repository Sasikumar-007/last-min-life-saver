"""
Firestore client setup. Boilerplate only - import `db` wherever you
need Firestore access in your services/routers.

Local dev: set GOOGLE_APPLICATION_CREDENTIALS env var to your service
account JSON path.
Cloud Run: uses the attached service account automatically, no env var needed.
"""

import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        try:
            cred_dict = json.loads(service_account_json)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        except Exception:
            firebase_admin.initialize_app()
    else:
        firebase_admin.initialize_app()

db = firestore.client()

