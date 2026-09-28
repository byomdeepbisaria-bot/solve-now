from google import genai
import os
import logging

logger = logging.getLogger(__name__)


def generate_embedding(text: str) -> list[float] | None:
    """
    Generates a 768-dimensional embedding using Gemini's text-embedding-004 model.

    If AI_API_KEY or GEMINI_API_KEY is set: calls Gemini API.
    If not set or API call fails: logs a warning and returns None (storing NULL in DB),
    allowing problem creation to succeed without crashing.
    """
    api_key = os.environ.get("AI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")

    if not api_key:
        logger.warning("Skipping embedding generation (no AI_API_KEY configured) — storing NULL")
        return None

    try:
        client = genai.Client(api_key=api_key)
        result = client.models.embed_content(
            model="text-embedding-004",
            contents=text[:8000],  # Truncate to model context limit
        )
        return result.embeddings[0].values
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        return None
