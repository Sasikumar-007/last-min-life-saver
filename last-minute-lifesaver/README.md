# Last-Minute Life Saver

An AI agent that proactively plans, replans, and takes action on your
deadlines — instead of just reminding you about them.

## Structure

```
backend/    FastAPI app, deployed to Cloud Run
  app/
    main.py            App entrypoint, router wiring (boilerplate)
    routers/           HTTP route definitions (boilerplate)
      auth.py          Google OAuth login flow
      tasks.py         Task extraction + listing
      plan.py          Plan generation + fetch
      drift.py         Drift check endpoint (called by Cloud Scheduler)
    services/          >>> YOUR AGENT LOGIC GOES HERE <<<
      extraction.py    Raw text -> structured tasks (Gemini)
      planner.py       Tasks + Calendar free/busy -> ranked schedule
      drift.py         Detect drift, call Gemini w/ function-calling tools
      tools.py         Tool implementations: reprioritize, move_event,
                        draft_email, send_draft, notify
    models/schemas.py  Pydantic models matching the Firestore schema
    utils/             Firestore + Gemini client setup (boilerplate)

frontend/   React + Vite + Tailwind, deployed to Firebase Hosting
  src/
    pages/Dashboard.jsx   Main screen: plan view, chat input, drift trigger
    pages/Login.jsx       Google sign-in
    services/api.js       Backend API wrapper (fill in fetch calls)
    services/firebase.js  Firebase client config
```

## Local setup

### Backend
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY, OAuth credentials
uvicorn app.main:app --reload --port 8080
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## What to build, in order

1. **Firestore schema** — confirm collections: `users`, `tasks`,
   `fixed_events`, `plans`, `action_log` (see `models/schemas.py`).
2. **Auth** — `routers/auth.py`: Google OAuth with Calendar + Gmail scopes.
3. **Extraction** — `services/extraction.py`: Gemini call that turns raw
   text into structured tasks. Test against a real syllabus/email.
4. **Planner** — `services/planner.py`: pull Calendar free/busy, rank
   tasks, write tentative events back to Calendar.
5. **Tools** — `services/tools.py`: implement each function-calling tool.
6. **Drift loop** — `services/drift.py`: the centerpiece. Compare plan vs
   reality, let Gemini decide which tool(s) to call, log every decision.
7. **Frontend wiring** — `services/api.js`, `pages/Dashboard.jsx`.
8. **Deploy** — Cloud Run (backend) + Firebase Hosting (frontend).

## Deployment (Google Cloud)

```bash
# Backend -> Cloud Run
cd backend
gcloud run deploy lifesaver-backend --source . --region us-central1 --allow-unauthenticated

# Frontend -> Firebase Hosting
cd frontend
npm run build
firebase deploy --only hosting
```

## Cloud Scheduler (for the proactive drift loop)

```bash
gcloud scheduler jobs create http drift-check \
  --schedule="0 */4 * * *" \
  --uri="https://YOUR_CLOUD_RUN_URL/drift/check" \
  --http-method=POST
```
