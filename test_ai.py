import os
import sys
import asyncio
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd(), 'apps', 'api'))
os.chdir('apps/api')
load_dotenv()

from services.ai.manager import ManagedAIProvider

async def test():
    provider = ManagedAIProvider()
    print("Primary:", provider.primary)
    print("Fallback:", provider.fallback)
    
    try:
        res = provider.generate_chat_response("Explain binary search")
        print("Success:", res[:100])
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
