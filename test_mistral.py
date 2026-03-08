import asyncio
import json
from llm_analyzer import MistralAnalyzer

async def test_mistral():
    print("Testing Mistral...")
    analyzer = MistralAnalyzer()
    posts = [{"id": "1", "text": "Hezbollah strikes IDF near Majdal Shams."}]
    res = await analyzer.extract_locations(json.dumps(posts))
    print("Result:", res)

asyncio.run(test_mistral())
