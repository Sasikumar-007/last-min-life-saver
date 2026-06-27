"""
Firestore client setup. Boilerplate only - import `db` wherever you
need Firestore access in your services/routers.

Local dev: set GOOGLE_APPLICATION_CREDENTIALS env var to your service
account JSON path.
Cloud Run: uses the attached service account automatically, no env var needed.
"""

import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()
