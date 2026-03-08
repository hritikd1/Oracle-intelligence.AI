import asyncio
import json
import re
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import os

app = FastAPI(title="Stock Intelligence System API")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"🔌 Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"🔌 Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)

manager = ConnectionManager()

# ── Geo Events Storage ──

CITY_COORDS = {
    "mumbai": (19.076, 72.8777), "delhi": (28.6139, 77.2090), "new delhi": (28.6139, 77.2090),
    "bangalore": (12.9716, 77.5946), "bengaluru": (12.9716, 77.5946), "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639), "hyderabad": (17.385, 78.4867), "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714), "jaipur": (26.9124, 75.7873), "lucknow": (26.8467, 80.9462),
    "kabul": (34.5553, 69.2075), "tehran": (35.6892, 51.3890), "baghdad": (33.3152, 44.3661),
    "dubai": (25.2048, 55.2708), "riyadh": (24.7136, 46.6753), "doha": (25.2854, 51.5310),
    "islamabad": (33.6844, 73.0479), "karachi": (24.8607, 67.0011), "lahore": (31.5204, 74.3587),
    "beijing": (39.9042, 116.4074), "shanghai": (31.2304, 121.4737), "hong kong": (22.3193, 114.1694),
    "tokyo": (35.6762, 139.6503), "singapore": (1.3521, 103.8198), "seoul": (37.5665, 126.978),
    "taipei": (25.033, 121.5654), "sydney": (33.8688, 151.2093), "moscow": (55.7558, 37.6173),
    "kyiv": (50.4501, 30.5234), "kiev": (50.4501, 30.5234), "minsk": (53.9006, 27.5590),
    "london": (51.5074, -0.1278), "paris": (48.8566, 2.3522), "berlin": (52.52, 13.405),
    "rome": (41.9028, 12.4964), "madrid": (40.4168, -3.7038), "brussels": (50.8503, 4.3517),
    "amsterdam": (52.3676, 4.9041), "zurich": (47.3769, 8.5417), "vienna": (48.2082, 16.3738),
    "new york": (40.7128, -74.006), "washington": (38.9072, -77.0369), "los angeles": (34.0522, -118.2437),
    "chicago": (41.8781, -87.6298), "san francisco": (37.7749, -122.4194), "houston": (29.7604, -95.3698),
    "toronto": (43.6532, -79.3832), "ottawa": (45.4215, -75.6972),
    "gaza": (31.5, 34.47), "tel aviv": (32.0853, 34.7818), "jerusalem": (31.7683, 35.2137),
    "beirut": (33.8938, 35.5018), "damascus": (33.5138, 36.2765), "amman": (31.9454, 35.9284),
    "cairo": (30.0444, 31.2357), "nairobi": (1.2921, 36.8219), "lagos": (6.5244, 3.3792),
    "johannesburg": (-26.2041, 28.0473), "cape town": (-33.9249, 18.4241),
    "sao paulo": (-23.5505, -46.6333), "buenos aires": (-34.6037, -58.3816),
    "mexico city": (19.4326, -99.1332), "lima": (-12.0464, -77.0428),
    "bangkok": (13.7563, 100.5018), "jakarta": (-6.2088, 106.8456),
    "kuala lumpur": (3.139, 101.6869), "hanoi": (21.0278, 105.8342),
    "iran": (32.4279, 53.688), "israel": (31.0461, 34.8516), "ukraine": (48.3794, 31.1656),
    "russia": (61.524, 105.3188), "china": (35.8617, 104.1954), "india": (20.5937, 78.9629),
    "usa": (37.0902, -95.7129), "japan": (36.2048, 138.2529), "germany": (51.1657, 10.4515),
    "france": (46.2276, 2.2137), "uk": (55.3781, -3.436), "saudi arabia": (23.8859, 45.0792),
    "turkey": (38.9637, 35.2433), "yemen": (15.5527, 48.5164), "syria": (34.8021, 38.9968),
    "sudan": (12.8628, 30.2176), "pakistan": (30.3753, 69.3451),
    "wall street": (40.7069, -74.0089), "sensex": (19.076, 72.8777), "nifty": (19.076, 72.8777),
}

geo_events: list = []


def extract_geo_events(event: dict):
    """Extract locations from Mistral analysis and create geo events."""
    found = []
    
    if event.get("agent") != "telegram_scanner":
        return found
        
    mistral_data = event.get("mistral_analysis")
    if not mistral_data:
        return found
        
    results = mistral_data.get("results", [])
    news_items = event.get("news_items", [])
    
    for res in results:
        post_id = res.get("id")
        locations = res.get("locations", [])
        
        # Match back to the original news item
        matching_item = next((item for item in news_items if item.get("telegram_post_id") == post_id), {})
        
        # Determine severity blindly since we are no longer using Mistral for summary
        text = (matching_item.get('title', '') + ' ' + matching_item.get('snippet', '')).lower()
        severity = 'medium'
        if any(w in text for w in ['bomb', 'attack', 'kill', 'war', 'strike', 'missile', 'terror', 'explosion']):
            severity = 'critical'
        elif any(w in text for w in ['crash', 'crisis', 'collapse', 'emergency', 'conflict', 'sanctions']):
            severity = 'high'
        elif any(w in text for w in ['tension', 'risk', 'warning', 'volatil', 'decline', 'fall']):
            severity = 'medium'
        
        for loc in locations:
            if isinstance(loc, dict) and 'lat' in loc and 'lng' in loc:
                city = loc.get('name', 'Unknown Location')
                lat, lng = loc.get('lat'), loc.get('lng')
                
                try:
                    lat, lng = float(lat), float(lng)
                except (ValueError, TypeError):
                    continue
                    
                # Use a stable ID so React's Leaflet mapping doesn't destroy the DOM iframes every 5 seconds
                stable_id = f"tg-{post_id}" if post_id else str(uuid.uuid4())[:8]

                    
                # Clean up "Telegram: channel_name" to just "channel_name" for the embed slug
                raw_source = matching_item.get('source', 'CIG_telegram')
                clean_slug = raw_source.replace('Telegram: ', '') if isinstance(raw_source, str) else 'CIG_telegram'

                geo_event = {
                    'id': stable_id,
                    'lat': lat,
                    'lng': lng,
                    'city': str(city).title(),
                    'country': '',
                    'headline': matching_item.get('title', 'Telegram Intel Update'),
                    'summary': matching_item.get('snippet', ''),
                    'telegram_post_id': post_id,
                    'source': clean_slug,
                    'url': matching_item.get('url', ''),
                    'severity': severity,
                    'timestamp': matching_item.get('timestamp', event.get('timestamp', '')),
                }
                found.append(geo_event)
                
                # Only extract ONE primary location per post to prevent duplicate news tags clustering the map
                break
            
    return found


# ── REST Endpoints ──

@app.get("/api/status")
async def get_status():
    return {"status": "online", "system": "Stock Intelligence System"}

@app.get("/api/agents/status")
async def get_agent_status():
    """Return the live status of all AI agents."""
    try:
        from agents import get_agent_status
        return get_agent_status()
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/market/analysis")
async def get_market_analysis():
    """Return the latest market analysis JSON."""
    try:
        if os.path.exists("market_analysis.json"):
            with open("market_analysis.json", "r") as f:
                return json.load(f)
        return {"status": "no data yet — agents are still running their first cycle"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/opportunities")
async def get_opportunities():
    """Return the latest investment opportunities."""
    try:
        if os.path.exists("opportunities.json"):
            with open("opportunities.json", "r") as f:
                return json.load(f)
        return {"status": "no opportunities yet — agent is still running"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/trending")
async def get_trending():
    """Return the latest trending data."""
    try:
        if os.path.exists("trending.json"):
            with open("trending.json", "r") as f:
                return json.load(f)
        return {"status": "no trending data yet"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/telegram/status")
async def get_telegram_status():
    """Return the latest telegram intel data."""
    try:
        if os.path.exists("telegram.json"):
            with open("telegram.json", "r") as f:
                return json.load(f)
        return {"status": "no telegram data yet"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/indian-market")
async def get_indian_market():
    """Return the latest Indian market tracker data."""
    try:
        if os.path.exists("indian_market.json"):
            with open("indian_market.json", "r") as f:
                return json.load(f)
        return {"status": "no market data yet"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/geo/events")
async def get_geo_events():
    """Return all geo-tagged events for the globe map."""
    return geo_events[-20:]  # Limit initial load to 20 latest events


# ── Webhook (agents POST here to broadcast to UI) ──

@app.post("/api/webhook/agent_event")
async def agent_event(event: dict):
    """Agents POST their insights here. Broadcasts to all WebSocket clients."""
    # Extract geo events from the news
    new_geo = extract_geo_events(event)
    if new_geo:
        # Filter duplicates by ID before extending
        incoming_ids = {g['id'] for g in new_geo}
        geo_events[:] = [g for g in geo_events if g['id'] not in incoming_ids]
        
        geo_events.extend(new_geo)
        
        # Enforce exactly 20 latest map events system-wide
        geo_events[:] = sorted(geo_events, key=lambda x: x['timestamp'])[-20:]
        
        # Also broadcast ENTIRE array to frontend
        await manager.broadcast({"type": "geo_events_update", "events": geo_events})

    await manager.broadcast(event)
    return {"status": "broadcasted", "clients": len(manager.active_connections)}


# ── WebSocket ──

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

