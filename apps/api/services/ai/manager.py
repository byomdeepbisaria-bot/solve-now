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
            logger.warning(f"Failed to initialize primary provider {first_class.__name__}")
            
        try:
            self.fallback = second_class()
        except Exception as e:
            logger.warning(f"Failed to initialize fallback provider {second_class.__name__}")

        if not self.primary and not self.fallback:
            self.final_fallback = FallbackAIProvider()
        else:
            self.final_fallback = None

    def generate_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        # Try Primary
        if self.primary:
            try:
                return self.primary.generate_chat_response(prompt, system_prompt)
            except Exception as e:
                logger.warning(f"Primary provider failed: {e}")
                
        # Try Fallback
        if self.fallback:
            try:
                return self.fallback.generate_chat_response(prompt, system_prompt)
            except Exception as e:
                logger.error(f"Fallback provider also failed: {e}")
                raise RuntimeError("Both primary and fallback AI providers failed.")
                
        # Only use final fallback if no remote providers could even be initialized
        if self.final_fallback:
            return self.final_fallback.generate_chat_response(prompt, system_prompt)
            
        raise RuntimeError("No AI providers available.")
