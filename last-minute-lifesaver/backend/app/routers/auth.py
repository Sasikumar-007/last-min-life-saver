"""
Auth routes: Google OAuth login + token storage.

YOUR WORK:
  - GET /auth/login        -> redirect user to Google's OAuth consent screen
                              (scopes: calendar, gmail.readonly, gmail.send)
  - GET /auth/callback      -> exchange code for tokens, store in Firestore
                              under users/{uid}.google_tokens
  - GET /auth/me            -> return current user's profile

Use google-auth-oauthlib's Flow class. Store refresh_token securely in
Firestore (never send it to the frontend) - only short-lived access
tokens should ever leave the backend.
"""

import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.utils.firestore_client import db


router = APIRouter()

# OAuth scopes: Calendar (read/write) + Gmail (read + send)
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


def _create_flow() -> Flow:
    """Create a google-auth-oauthlib Flow from environment variables."""
    client_config = {
        "web": {
            "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
            "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/callback")],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8080/auth/callback"),
    )
    return flow


@router.get("/login")
def login():
    """
    Redirect user to Google's OAuth consent screen.
    Requests Calendar, Gmail, and profile scopes.
    access_type=offline ensures we get a refresh_token.
    """
    flow = _create_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # Force consent to always get refresh_token
    )
    return RedirectResponse(url=authorization_url)


@router.get("/callback")
def callback(code: str):
    """
    Handle the OAuth callback:
    1. Exchange authorization code for tokens
    2. Fetch user profile (email, name)
    3. Store tokens securely in Firestore (never sent to frontend)
    4. Redirect to the frontend dashboard
    """
    flow = _create_flow()
    flow.fetch_token(code=code)

    credentials = flow.credentials

    # Get user info from Google
    user_info_service = build("oauth2", "v2", credentials=credentials)
    user_info = user_info_service.userinfo().get().execute()

    uid = user_info.get("id")
    email = user_info.get("email", "")
    display_name = user_info.get("name", "")

    # Store user profile and tokens in Firestore
    # IMPORTANT: refresh_token is stored server-side only — never sent to frontend
    user_data = {
        "uid": uid,
        "email": email,
        "display_name": display_name,
        "google_tokens": {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "scopes": list(credentials.scopes) if credentials.scopes else SCOPES,
        },
    }
    db.collection("users").document(uid).set(user_data, merge=True)

    # Redirect to frontend dashboard with user_id as query param
    # (In production, you'd use a session cookie or JWT instead)
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    return RedirectResponse(url=f"{frontend_url}/?user_id={uid}")


@router.get("/me")
def me(user_id: str):
    """
    Return the logged-in user's profile from Firestore.
    Never includes google_tokens — those stay server-side.
    """
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id query parameter required")

    user_doc = db.collection("users").document(user_id).get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = user_doc.to_dict()

    # Strip sensitive token data before sending to frontend
    user_data.pop("google_tokens", None)

    return user_data
