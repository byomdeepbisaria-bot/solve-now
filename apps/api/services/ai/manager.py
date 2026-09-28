import logging
from .base import AIProvider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .fallback_provider import FallbackAIProvider
from core.config import settings

logger = logging.getLogger(__name__)


class ManagedAIProvider(AIProvider):
    def __init__(self):
        self.primary = None
        self.fallback = None

        provider_preference = settings.AI_PROVIDER.lower()

        if provider_preference == "groq":
            first_class, second_class = GroqProvider, GeminiProvider
        else:
            first_class, second_class = GeminiProvider, GroqProvider

        try:
            self.primary = first_class()
        except Exception as e:
            logger.warning(f"Failed to initialize primary provider {first_class.__name__}: {e}")

        try:
            self.fallback = second_class()
        except Exception as e:
            logger.warning(f"Failed to initialize fallback provider {second_class.__name__}: {e}")

    def generate_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        # Try Primary cloud provider
        if self.primary:
            try:
                return self.primary.generate_chat_response(prompt, system_prompt)
            except Exception as e:
                logger.warning(f"Primary AI provider failed: {e}")

        # Try Secondary cloud provider
        if self.fallback:
            try:
                return self.fallback.generate_chat_response(prompt, system_prompt)
            except Exception as e:
                logger.warning(f"Secondary AI provider failed: {e}")

        # Fallback to deterministic FallbackAIProvider — prevents 500 crashes
        # when external cloud API keys are unconfigured or unreachable.
        logger.info("Using FallbackAIProvider for AI response generation.")
        return FallbackAIProvider().generate_chat_response(prompt, system_prompt)
