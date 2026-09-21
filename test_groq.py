import os
import sys
import asyncio
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'apps', 'api'))
os.chdir('apps/api')
load_dotenv()
os.environ["GROQ_MODEL"] = "openai/gpt-oss-20b"

from services.ai.groq import GroqProvider

async def test():
    try:
        provider = GroqProvider()
        res = provider.generate_chat_response("Explain binary search")
        print("Success:", res[:100])
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
