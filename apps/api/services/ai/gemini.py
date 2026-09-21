import os
import logging
from google import genai
from core.config import settings
from .base import AIProvider

logger = logging.getLogger(__name__)

class GeminiProvider(AIProvider):
    def __init__(self):
        # Prefer specific key, fallback to general AI_API_KEY
        self.api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY") or settings.AI_API_KEY
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        
        self.client = genai.Client(api_key=self.api_key)
        self.model = settings.GEMINI_MODEL or os.environ.get("GEMINI_MODEL") or settings.AI_MODEL or "gemini-2.5-flash"

    def generate_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        try:
            config = genai.types.GenerateContentConfig(
                temperature=0.2,
            )
            if system_prompt:
                config.system_instruction = system_prompt
                
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )

            if not response.text:
                raise RuntimeError("Gemini returned an empty response")

            return response.text

        except Exception as e:
            logger.error(f"Gemini API request failed.")
            raise RuntimeError(f"Gemini API Error: {str(e)}") from e
