import os
from dotenv import load_dotenv
import aiohttp
import asyncio

# Load environment variables
load_dotenv()

# API credentials
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_API_URL = 'https://api.mistral.ai/v1/chat/completions'

class MistralAnalyzer:
    """Handles analysis of relevant signals using Mistral AI"""
    def __init__(self):
        self.api_key = MISTRAL_API_KEY
        self.api_url = MISTRAL_API_URL
    
    async def analyze_signal(self, text, context=None):
        """Analyze a signal with Mistral AI"""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # Create a structured prompt with context if available
            system_prompt = '''
            You are an economic intelligence analyst specializing in Indian markets. 
            Analyze the given information and provide exactly these sections with these exact headings:
            
            1. SUMMARY: A concise explanation of the news/event
            2. SECTOR IMPACT: List specific sectors that will be affected (positive/negative)
            3. STOCK RECOMMENDATIONS: Name 2-3 specific Indian stocks that could be impacted
            4. CONFIDENCE: Rate your confidence in this analysis (Low/Medium/High)
            '''
            
            user_message = f"Context: {context if context else 'None'}\n\nText to analyze: {text}"
            
            payload = {
                'model': 'mistral-large-latest',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message}
                ]
            }
            
            import asyncio
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content']
                    else:
                        error_text = await response.text()
                        return f"Error from Mistral API: {error_text}"
        except Exception as e:
            return f"An error occurred during analysis: {e}"

    async def extract_locations(self, posts_json_str):
        """Extract explicit geographical locations per telegram post using Mistral"""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            system_prompt = '''
            You are a geopolitical intelligence analyst. Your objective is to extract geographical locations explicitly or implicitly mentioned in the provided JSON array of Telegram posts.
            Return ONLY a valid JSON object with this exact structure, mapping each post "id" exactly as provided in the input array to its extracted "locations".
            Do not summarize.
            {
                "results": [
                    {
                        "id": "<USE THE EXACT MATCHING ID FROM INPUT JSON>",
                        "locations": [
                            {"name": "Specific City or Region Name", "lat": 12.3456, "lng": 56.7890}
                        ]
                    }
                ]
            }
            CRITICAL RULES:
            1. The "id" MUST exactly match the "id" of the post you extracted the location from. Do NOT invent IDs or copy this example!
            2. You MUST estimate highly precise latitude and longitude coordinates. Do not just use generic country centers if a city, town, or base is mentioned. Use 4 decimal places for accuracy.
            3. You MUST deduce the region or country of militant groups if no city is named. For example, if Hezbollah is mentioned, add Lebanon/Israel border. If Houthis are mentioned, add Yemen/Red Sea. If IDF is mentioned, add Israel/Gaza.
            4. Only include an object in the "results" array if you found at least one location for that post. I expect you to find locations for at least half of the posts!
            '''
            
            payload = {
                'model': 'mistral-large-latest',
                'max_tokens': 8192,
                'response_format': {"type": "json_object"},
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': f"Posts to analyze: {posts_json_str}"}
                ]
            }
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['choices'][0]['message']['content']
                    else:
                        print(f"Error from Mistral: {await response.text()}")
                        return None
        except Exception as e:
            print(f"Mistral Error: {e}")
            return None