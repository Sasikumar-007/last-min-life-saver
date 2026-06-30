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
    # Safe guard: if GOOGLE_APPLICATION_CREDENTIALS points to a file that doesn't exist,
    # delete it from os.environ to prevent the Google auth library from crashing.
    if "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
        cred_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
        if not os.path.exists(cred_path):
            del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

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

from google.cloud import firestore as g_firestore
app = firebase_admin.get_app()
project_id = getattr(app, "project_id", None) or os.environ.get("GOOGLE_CLOUD_PROJECT")
g_cred = app.credential.get_credential() if app.credential else None
db = g_firestore.Client(project=project_id, database=os.environ.get("FIREBASE_DATABASE_ID", "sasikumar007"), credentials=g_cred)

