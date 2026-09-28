from google import genai
import os
import logging

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """
    Returns the AI API key.
    Degrades gracefully in both development and production if not set.
    """
    key = os.environ.get("AI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    environment = os.environ.get("ENVIRONMENT", "development")

    if not key:
        logger.warning(
            f"[{environment}] AI_API_KEY is not set. Embedding generation will return None. "
            "Duplicate detection and knowledge search will be degraded. "
            "Set AI_API_KEY in Render environment variables for full functionality."
        )
    return key


def generate_embedding(text: str) -> list[float] | None:
    """
    Generates a 768-dimensional embedding using Gemini's text-embedding-004 model.

    Returns None when no API key is configured or if generation fails.
    """
    api_key = _get_api_key()

    if not api_key:
        logger.warning("Skipping embedding generation (no API key configured) — storing NULL")
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
        # Graceful fallback in production and development — log and return None
        return None
