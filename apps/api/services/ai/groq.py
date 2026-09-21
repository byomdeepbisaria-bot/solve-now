import os
import logging
from groq import Groq
from core.config import settings
from .base import AIProvider

logger = logging.getLogger(__name__)

class GroqProvider(AIProvider):
    def __init__(self):
        # Prefer specific key, fallback to general AI_API_KEY
        self.api_key = settings.GROQ_API_KEY or os.environ.get("GROQ_API_KEY") or settings.AI_API_KEY
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
            
        self.client = Groq(api_key=self.api_key)
        self.model = settings.GROQ_MODEL or os.environ.get("GROQ_MODEL") or "llama3-8b-8192"

    def generate_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
            )

            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("Groq returned an empty response")

            return content

        except Exception as e:
            logger.error(f"Groq API request failed.")
            raise RuntimeError(f"Groq API Error: {str(e)}") from e
