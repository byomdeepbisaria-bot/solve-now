import os
from google import genai
from google.genai import types
from core.config import settings
from .base import AIProvider

class GeminiProvider(AIProvider):
    def __init__(self):
        api_key = settings.AI_API_KEY or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("AI_API_KEY", "")
        if not api_key:
            raise ValueError("Gemini API key is not configured. Please set AI_API_KEY or GEMINI_API_KEY in .env")
        self.client = genai.Client(api_key=api_key)
        self.model = settings.AI_MODEL or "gemini-2.0-flash"

    def generate_chat_response(self, prompt: str, system_prompt: str = "") -> str:
        contents = prompt
        if system_prompt:
            contents = f"{system_prompt}\n\nUser: {prompt}"
            
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                ),
            )
            return response.text
        except Exception as e:
            # Fallback if API key is invalid or quota exceeded
            from .fallback_provider import FallbackAIProvider
            fallback = FallbackAIProvider()
            return fallback.generate_chat_response(prompt, system_prompt)
