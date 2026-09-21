import os
from core.config import settings
from .base import AIProvider
from .manager import ManagedAIProvider
from .fallback_provider import FallbackAIProvider

def get_ai_provider() -> AIProvider:
    api_key = settings.AI_API_KEY or settings.GEMINI_API_KEY or settings.GROQ_API_KEY or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    
    if not api_key:
        return FallbackAIProvider()

    return ManagedAIProvider()
