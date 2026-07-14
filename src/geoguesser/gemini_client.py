from __future__ import annotations

import os

from google import genai


def create_gemini_client() -> genai.Client:
    """Create a Gemini API client using an explicit API key, never implicit OAuth."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or api_key.startswith("your_"):
        raise RuntimeError(
            "GEMINI_API_KEY is required; set it in .env or the process environment"
        )
    return genai.Client(api_key=api_key)
