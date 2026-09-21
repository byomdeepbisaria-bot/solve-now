import os
import sys
from groq import Groq
from dotenv import load_dotenv

load_dotenv('apps/api/.env')
client = Groq(api_key=os.environ["GROQ_API_KEY"])
print([m.id for m in client.models.list().data])
