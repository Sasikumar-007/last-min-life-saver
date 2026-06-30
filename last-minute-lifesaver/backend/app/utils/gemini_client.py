"""
Gemini client setup. Boilerplate only.

Set GEMINI_API_KEY in your .env (get one from Google AI Studio).
Import `model` in extraction.py / planner.py / drift.py and call
model.generate_content(...) with your own prompts + function schemas.
"""

import os
import google.generativeai as genai

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# TODO: pick your model - "gemini-2.0-flash" is fast/cheap, good for
# extraction; consider a stronger model for the planner/drift reasoning
# if you need better judgment calls.
model = genai.GenerativeModel("gemini-flash-latest")
