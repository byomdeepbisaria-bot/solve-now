from google import genai
import os
import logging

logger = logging.getLogger(__name__)


def _get_api_key() -> str:
    """
    Returns the AI API key. Raises ValueError in production if not set.
    Never silently falls back to a dummy value in production.
    """
    key = os.environ.get("AI_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
    environment = os.environ.get("ENVIRONMENT", "development")

    if not key:
        if environment == "production":
            raise ValueError(
                "AI_API_KEY is required in production. "
                "Set the AI_API_KEY environment variable."
            )
        else:
            logger.warning(
                "AI_API_KEY is not set. Embedding generation will return zero vectors. "
                "Duplicate detection and knowledge search will be degraded. "
                "Set AI_API_KEY in .env for full functionality."
            )
    return key


def generate_embedding(text: str) -> list[float] | None:
    """
    Generates a 768-dimensional embedding using Gemini's text-embedding-004 model.

    Returns None in development when no API key is configured.
    Raises ValueError in production if no API key is set.
    """
    api_key = _get_api_key()

    if not api_key:
        # Development-only degraded mode — store NULL instead of zero vector
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
        if os.environ.get("ENVIRONMENT") == "production":
            raise
        # Development fallback — log and return None
        return None
