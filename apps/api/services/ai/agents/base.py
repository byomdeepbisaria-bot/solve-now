import json
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Type, TypeVar, Any

T = TypeVar('T', bound=BaseModel)

class BaseAgent:
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def run(self, prompt: str, schema: Type[T], system_instruction: str = None) -> T:
        config_kwargs = {
            "response_mime_type": "application/json",
            "response_schema": schema
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
            
        config = types.GenerateContentConfig(**config_kwargs)
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        
        data = json.loads(response.text)
        return schema(**data)

