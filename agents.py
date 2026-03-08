import os
import asyncio
import json
import re
import aiohttp
from datetime import datetime
from dotenv import load_dotenv

from core_scrapers import GoogleRSSFeed, TelegramChannelScraper
from llm_analyzer import MistralAnalyzer

load_dotenv()

MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
MISTRAL_API_URL = 'https://api.mistral.ai/v1/chat/completions'

# ── Utility ──

def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text so the UI displays cleanly."""
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^[\-\*]{3,}$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\|.*\|$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\-\s\|]+$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


async def call_mistral(prompt: str, system_msg: str | None = None) -> str:
    """Call Mistral AI. Returns clean plain-text response."""
    default_system = (
        "You are an expert Indian stock market analyst. "
        "CRITICAL RULES: "
        "1) Never use markdown formatting like #, ##, **, ---, or tables. "
        "2) Write in clean plain text with numbered lists and line breaks. "
        "3) Be specific about stock names, sectors, and give actionable advice. "
        "4) ONLY analyze based on the news headlines provided. Do NOT make up data or use your training data. "
        "5) Always cite which headline you are referencing."
    )
    try:
        headers = {
            'Authorization': f'Bearer {MISTRAL_API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': 'mistral-large-latest',
            'messages': [
                {'role': 'system', 'content': system_msg or default_system},
                {'role': 'user', 'content': prompt}
            ]
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(MISTRAL_API_URL, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    raw = data['choices'][0]['message']['content']
                    return strip_markdown(raw)
                else:
                    error = await resp.text()
                    return f"API error ({resp.status}): {error[:200]}"
    except Exception as e:
        return f"Analysis unavailable: {e}"


async def broadcast(event: dict):
    """POST event to FastAPI webhook."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8000/api/webhook/agent_event", json=event
            ) as resp:
                if resp.status == 200:
                    print(f"  ✅ Broadcasted to dashboard")
    except Exception as e:
        print(f"  ⚠ Dashboard not reachable: {e}")


async def fetch_rss(topics: list, limit=5, hours=48) -> list:
    """Fetch news from multiple RSS topics."""
    articles = []
    for name, query in topics:
        src = GoogleRSSFeed(name=name, source_type="Financial", topic=query)
        try:
            data = await src.fetch_data(limit=limit, hours=hours)
            articles.extend(data)
        except Exception as e:
            print(f"  ⚠ RSS {name}: {e}")
    return articles


def deduplicate(articles: list) -> list:
    """Remove duplicate articles by title."""
    seen = set()
    out = []
    for a in articles:
        t = a.get('title', '').lower().strip()
        if t and t not in seen:
            seen.add(t)
            out.append(a)
    return out


def make_source_list(articles: list, limit: int = 5) -> list:
    """Build a list of source dicts for the frontend."""
    return [{
        "title": a.get('title', ''),
        "source": a.get('source', 'Google News'),
        "url": a.get('link', ''),
        "image": a.get('image', ''),
    } for a in articles[:limit]]


# ═══════════════════════════════════════
# Section definitions for Market Analyzer
# ═══════════════════════════════════════

ANALYSIS_SECTIONS = {
    'market_overview': {
        'prompt': (
            "Based ONLY on the following news headlines, analyze the current sentiment of the Indian stock market. "
            "Structure your response as:\n"
            "SENTIMENT: [Bullish/Bearish/Neutral] with a confidence score from 1-10\n"
            "KEY DRIVERS: List 3-4 main factors driving sentiment right now (cite headlines)\n"
            "MARKET MOOD: A 2-3 sentence summary of market mood\n"
            "RISK LEVEL: [Low/Medium/High] with reasoning\n"
            "Write in plain text only."
        ),
        'terms': ["Indian stock market today", "Sensex Nifty today", "Indian market sentiment"]
    },
    'global_impact': {
        'prompt': (
            "Based ONLY on these headlines, what global events are impacting Indian markets? "
            "Structure your response as:\n"
            "GLOBAL IMPACT SCORE: [1-10] how much global events are affecting India\n"
            "KEY EVENTS: List each event and its impact on India (cite specific headlines)\n"
            "AFFECTED SECTORS: Which Indian sectors are most affected and why\n"
            "OUTLOOK: Short-term impact assessment\n"
            "Write in plain text only."
        ),
        'terms': ["global markets impact India", "US Fed India stocks", "crude oil India market"]
    },
    'sectoral_analysis': {
        'prompt': (
            "Based ONLY on these headlines, rate each Indian sector's current performance on a scale of 1-10. "
            "You MUST include these sectors with a score:\n"
            "IT: [score]/10 - [1 line reason citing headline]\n"
            "Banking: [score]/10 - [1 line reason]\n"
            "Pharma: [score]/10 - [1 line reason]\n"
            "Auto: [score]/10 - [1 line reason]\n"
            "Energy: [score]/10 - [1 line reason]\n"
            "FMCG: [score]/10 - [1 line reason]\n"
            "Infrastructure: [score]/10 - [1 line reason]\n"
            "Metals: [score]/10 - [1 line reason]\n"
            "Then give 2-3 lines of overall sector analysis.\n"
            "Write in plain text only."
        ),
        'terms': ["Indian IT sector stocks", "Indian banking sector", "pharma auto energy India stocks"]
    },
    'fii_dii_data': {
        'prompt': (
            "Based ONLY on these headlines, analyze institutional investor activity. "
            "Structure:\n"
            "FII STANCE: [Buying/Selling/Mixed] - estimated flow direction\n"
            "DII STANCE: [Buying/Selling/Mixed] - estimated flow direction\n"
            "NET FLOW: Overall institutional money direction\n"
            "IMPACT: How this affects retail investors (cite headlines)\n"
            "SECTORS IN FOCUS: Where institutions are putting money\n"
            "Write in plain text only."
        ),
        'terms': ["FII DII data India today", "foreign institutional investors India", "mutual fund inflows India"]
    },
    'raw_materials': {
        'prompt': (
            "Based ONLY on these headlines, analyze commodity and raw material trends. "
            "For each major commodity, give direction:\n"
            "Crude Oil: [Up/Down/Stable] - impact on India\n"
            "Gold: [Up/Down/Stable] - impact\n"
            "Steel/Metals: [Up/Down/Stable] - impact\n"
            "Agricultural: [Up/Down/Stable] - impact\n"
            "Then 2-3 lines on which Indian stocks benefit or suffer.\n"
            "Write in plain text only."
        ),
        'terms': ["commodity prices India", "crude oil price impact India", "metal prices India"]
    },
    'company_performance': {
        'prompt': (
            "Based ONLY on these headlines, which companies are in the news for positive/negative reasons? "
            "List top 5 companies mentioned with:\n"
            "Company: [Action: Positive/Negative] - reason from headline\n"
            "Then 2-3 lines about overall corporate earnings trends.\n"
            "Write in plain text only."
        ),
        'terms': ["Indian company results quarterly", "stock picks India", "company performance India"]
    },
}


# ═══════════════════════════════════════
# AGENT 1: News Scanner (every 5 min)
# ═══════════════════════════════════════

async def news_scanner_cycle():
    print("\n🔍 [NEWS SCANNER] Starting cycle...")

    topics = [
        ("Stock Market", "Indian stock market today"),
        ("Economy", "India economy news"),
        ("Banking", "India banking RBI"),
        ("IT Tech", "India IT technology stocks"),
        ("Energy", "crude oil India energy"),
        ("Pharma", "pharma stocks India"),
        ("Auto", "automobile stocks India"),
        ("Infra", "infrastructure stocks India"),
        ("Global", "global markets impact"),
    ]

    all_articles = await fetch_rss(topics, limit=5, hours=24)
    unique = deduplicate(all_articles)[:20]

    if not unique:
        print("  ❌ No articles found")
        return

    headlines = "\n".join([f"- {a['title']} ({a.get('source', 'Unknown')})" for a in unique])

    prompt = f"""Here are {len(unique)} recent financial news headlines. Write a market summary covering:

1) What is happening in the markets right now (reference specific headlines)
2) Which sectors are being impacted and why
3) Overall market sentiment (bullish/bearish/mixed)
4) 3 key things investors should watch

Headlines:
{headlines}

IMPORTANT: Only reference information from these headlines. Do not use your training data. Write in plain text, no markdown."""

    summary = await call_mistral(prompt)

    news_items = [{
        "title": a['title'],
        "source": a.get('source', 'Google News'),
        "url": a.get('link', ''),
        "snippet": a.get('snippet', '')[:120],
        "image": a.get('image', ''),
        "timestamp": a.get('timestamp', datetime.now().isoformat())
    } for a in unique[:15]]

    await broadcast({
        "agent": "news_scanner",
        "title": "Market Update",
        "summary": summary,
        "news_items": news_items,
        "timestamp": datetime.now().isoformat()
    })

    print(f"  ✅ [NEWS SCANNER] {len(unique)} articles → summary broadcasted")


# ═══════════════════════════════════════
# AGENT 2: Market Analyzer (every 2 hr)
# ═══════════════════════════════════════

async def market_analyzer_cycle():
    print("\n📊 [MARKET ANALYZER] Starting comprehensive analysis...")

    results = {}

    for section_name, section_data in ANALYSIS_SECTIONS.items():
        display_name = section_name.replace('_', ' ').title()
        print(f"  📈 {display_name}...")

        articles = await fetch_rss(
            [(display_name, t) for t in section_data['terms']],
            limit=5, hours=48
        )

        if not articles:
            print(f"    ⚠ No data, skipping")
            continue

        news_text = "\n".join([
            f"- {a['title']} (Source: {a.get('source', 'Unknown')})"
            for a in articles[:10]
        ])

        prompt = f"""{section_data['prompt']}

News headlines to analyze:
{news_text}

IMPORTANT: Base your analysis ONLY on these headlines. Cite the headline you are referencing."""

        analysis = await call_mistral(prompt)
        sources = make_source_list(articles, limit=5)

        results[section_name] = {
            'timestamp': datetime.now().isoformat(),
            'analysis': analysis,
            'news_count': len(articles),
            'sources': sources,
        }

        await broadcast({
            "agent": "market_analyzer",
            "title": f"Market Analysis: {display_name}",
            "section": section_name,
            "summary": analysis[:1500],
            "sources": sources,
            "news_count": len(articles),
            "timestamp": datetime.now().isoformat()
        })

        await asyncio.sleep(2)

    try:
        with open('market_analysis.json', 'w') as f:
            json.dump(results, f, indent=2)
    except Exception:
        pass

    print(f"  ✅ [MARKET ANALYZER] Completed {len(results)} sections")


# ═══════════════════════════════════════
# AGENT 3: Opportunity Finder (every 2 hr)
# ═══════════════════════════════════════

async def opportunity_finder_cycle():
    print("\n💡 [OPPORTUNITY FINDER] Searching...")

    topics = [
        ("Undervalued", "undervalued stocks India"),
        ("Breakout", "breakout stocks India"),
        ("Growth", "high growth companies India"),
        ("Small Cap", "small cap mid cap stocks India"),
        ("IPO", "upcoming IPO India 2026"),
    ]

    articles = await fetch_rss(topics, limit=5, hours=48)
    unique = deduplicate(articles)[:15]

    market_ctx = ""
    try:
        if os.path.exists('market_analysis.json'):
            with open('market_analysis.json', 'r') as f:
                data = json.load(f)
            for key in ['market_overview', 'sectoral_analysis']:
                if key in data:
                    market_ctx += f"\n{data[key].get('analysis', '')[:400]}\n"
    except Exception:
        pass

    headlines = "\n".join([f"- {a['title']}" for a in unique])

    prompt = f"""Based on these news headlines and market context, identify TOP 5 INVESTMENT OPPORTUNITIES.

News:
{headlines}

Market Context:
{market_ctx[:1000]}

For each opportunity:
1. Stock/Company Name (specific like "HDFC Bank", "Tata Motors")
2. Action: BUY / ACCUMULATE / WATCH
3. Reasoning citing the headline
4. Risk Level: Low / Medium / High
5. Time Horizon

Also name ONE stock to AVOID.

IMPORTANT: Only cite information from these headlines. Write in plain text only."""

    analysis = await call_mistral(prompt)
    sources = make_source_list(unique, limit=5)

    await broadcast({
        "agent": "opportunity_finder",
        "title": "Investment Opportunities Found",
        "summary": analysis[:2000],
        "sources": sources,
        "source_count": len(unique),
        "timestamp": datetime.now().isoformat()
    })

    try:
        with open('opportunities.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'analysis': analysis,
                'sources': sources,
                'source_count': len(unique)
            }, f, indent=2)
    except Exception:
        pass

    print("  ✅ [OPPORTUNITY FINDER] Complete")


# ═══════════════════════════════════════
# AGENT 4: Trending Tracker (every 15 min)
# ═══════════════════════════════════════

async def trending_tracker_cycle():
    print("\n🔥 [TRENDING TRACKER] Scanning trends...")

    topics = [
        ("Market Today", "stock market India today"),
        ("Top Stocks", "top stocks India"),
        ("Market Movers", "stocks gainers losers India"),
        ("IPO News", "IPO India news"),
        ("Breaking", "breaking news stock market India"),
        ("Nifty", "Nifty 50 today"),
        ("Sensex", "Sensex today"),
    ]

    articles = await fetch_rss(topics, limit=6, hours=24)
    unique = deduplicate(articles)[:15]

    if not unique:
        # Fallback: try broader terms
        print("  ⚠ No trending data from first pass, trying broader terms...")
        fallback_topics = [
            ("Market", "India market"),
            ("Stocks", "stocks India"),
            ("Business", "business news India"),
        ]
        articles = await fetch_rss(fallback_topics, limit=8, hours=48)
        unique = deduplicate(articles)[:15]

    if not unique:
        print("  ❌ No trending data found even with fallback")
        await broadcast({
            "agent": "trending_tracker",
            "title": "Trending — Waiting for Data",
            "summary": "The trending tracker is waiting for fresh market news. This section will update automatically when new stories come in.",
            "trending_items": [],
            "timestamp": datetime.now().isoformat()
        })
        return

    headlines = "\n".join([f"- {a['title']} ({a.get('source', 'Unknown')})" for a in unique])

    prompt = f"""Based on these headlines, identify what is TRENDING in the market right now.

Headlines:
{headlines}

Write your response covering:
1) TOP 3 TRENDING TOPICS — what everyone is talking about (cite the headlines)
2) TRENDING STOCKS — which stocks are making moves and why
3) MARKET MOVERS — biggest gainers and losers
4) TREND OUTLOOK — which trends could have lasting impact

IMPORTANT: Only reference these headlines. Write in plain text, no markdown."""

    analysis = await call_mistral(prompt)

    trending_items = [{
        "title": a['title'],
        "source": a.get('source', 'Google News'),
        "url": a.get('link', ''),
        "image": a.get('image', ''),
        "timestamp": a.get('timestamp', datetime.now().isoformat())
    } for a in unique[:10]]

    await broadcast({
        "agent": "trending_tracker",
        "title": "What's Trending Now",
        "summary": analysis[:2000],
        "trending_items": trending_items,
        "timestamp": datetime.now().isoformat()
    })

    try:
        with open('trending.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'analysis': analysis,
                'items': trending_items
            }, f, indent=2)
    except Exception:
        pass

    print(f"  ✅ [TRENDING TRACKER] {len(unique)} items found")


# ═══════════════════════════════════════
# AGENT 5: Indian Market Tracker (every 10 min)
# ═══════════════════════════════════════

async def indian_market_tracker_cycle():
    print("\n🇮🇳 [INDIAN MARKET TRACKER] Tracking...")

    topics = [
        ("Nifty", "Nifty 50 today"),
        ("Sensex", "Sensex today"),
        ("Bank Nifty", "Bank Nifty today"),
        ("FII", "FII buying selling India today"),
        ("Stock Moves", "stocks big moves India today"),
        ("Rupee", "Indian rupee dollar"),
    ]

    articles = await fetch_rss(topics, limit=5, hours=12)
    unique = deduplicate(articles)[:15]

    if not unique:
        print("  ❌ No Indian market data found")
        return

    headlines = "\n".join([f"- {a['title']} ({a.get('source', 'Unknown')})" for a in unique])

    prompt = f"""Based on these headlines, give a live Indian market update.

{headlines}

Structure:
MARKET SNAPSHOT: Nifty/Sensex direction and key levels (cite headlines)
STOCKS IN FOCUS: 5 specific stocks making moves (cite headlines)
SECTOR HEAT: Which sectors are hot (green) and cold (red)
FII/DII: Institutional activity
RUPEE: Currency movement

IMPORTANT: Only cite these headlines. Write in plain text, no markdown."""

    analysis = await call_mistral(prompt)
    sources = make_source_list(unique, limit=5)

    market_items = [{
        "title": a['title'],
        "source": a.get('source', 'Google News'),
        "url": a.get('link', ''),
        "image": a.get('image', ''),
        "timestamp": a.get('timestamp', datetime.now().isoformat())
    } for a in unique[:10]]

    await broadcast({
        "agent": "indian_market_tracker",
        "title": "Indian Market Live Update",
        "summary": analysis[:2000],
        "sources": sources,
        "market_items": market_items,
        "timestamp": datetime.now().isoformat()
    })

    try:
        with open('indian_market.json', 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'analysis': analysis,
                'sources': sources,
                'items': market_items
            }, f, indent=2)
    except Exception:
        pass

    print("  ✅ [INDIAN MARKET TRACKER] Complete")


# ═══════════════════════════════════════
# AGENT 6: Telegram Scanner (Provides raw events to extraction webhook)
# ═══════════════════════════════════════
async def telegram_scanner_cycle():
    print("\n💬 [TELEGRAM RAW SCANNER] Fetching live intel...")
    try:
        channels = ["CIG_telegram", "idfofficial", "rnintel", "QudsNen", "wfwitness"]
        all_tg_data = []
        for ch in channels:
            try:
                tg_scraper = TelegramChannelScraper(name=ch, source_type="Telegram Intelligence", channel_slug=ch)
                data = await tg_scraper.fetch_data(limit=10, hours=48)
                if data:
                    all_tg_data.extend(data)
            except Exception as e:
                print(f"  ⚠ Error scraping {ch}: {e}")
                
        # Sort by timestamp descending to get the absolute newest intel across all channels
        all_tg_data.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        tg_data = all_tg_data[:25]  # Keep to 25 absolute latest so Mistral doesn't timeout
        
        if not tg_data:
            print("  ❌ No Telegram data found")
            return
            
        news_items = [{
            "title": a['title'],
            "source": a.get('source', 'Telegram'),
            "url": a.get('link', ''),
            "snippet": a.get('snippet', '')[:200],
            "image": a.get('image', ''),
            "telegram_post_id": a.get('telegram_post_id', ''),
            "timestamp": a.get('timestamp', datetime.now().isoformat())
        } for a in tg_data]
        
        # Package posts into a minimal JSON array for Mistral
        posts_for_ai = [{"id": a.get('telegram_post_id', ''), "text": a.get('snippet', '')} for a in tg_data if a.get('telegram_post_id')]
        posts_json_str = json.dumps(posts_for_ai)
        
        analyzer = MistralAnalyzer()
        geo_data_raw = await analyzer.extract_locations(posts_json_str)
        
        mistral_data = {"results": []}
        if geo_data_raw:
            try:
                clean_json = geo_data_raw.replace('```json', '').replace('```', '').strip()
                mistral_data = json.loads(clean_json)
            except Exception as e:
                print(f"  ❌ Error parsing Mistral JSON: {e}")
                
        # To maintain backwards compatibility of the payload (or if needed), we could join snippets as summary
        combined_text = " | ".join([a.get('snippet', '') for a in tg_data])
        
        event_payload = {
            "agent": "telegram_scanner",
            "title": "Telegram Intel Feed Update",
            "summary": combined_text, 
            "news_items": news_items,
            "mistral_analysis": mistral_data,
            "timestamp": datetime.now().isoformat()
        }
        await broadcast(event_payload)
        
        try:
            with open('telegram.json', 'w') as f:
                json.dump(event_payload, f, indent=2)
        except Exception:
            pass
        
        print(f"  ✅ [TELEGRAM RAW SCANNER] {len(tg_data)} intel messages broadcasted for geo-extraction")
    except Exception as e:
        print(f"  ❌ Telegram Scraper Error: {e}")

# ═══════════════════════════════════════
# Agent Status Tracking & Loops
# ═══════════════════════════════════════

agent_status = {
    "news_scanner":         {"status": "idle", "last_run": None, "cycle_count": 0},
    "market_analyzer":      {"status": "idle", "last_run": None, "cycle_count": 0},
    "opportunity_finder":   {"status": "idle", "last_run": None, "cycle_count": 0},
    "trending_tracker":     {"status": "idle", "last_run": None, "cycle_count": 0},
    "indian_market_tracker":{"status": "idle", "last_run": None, "cycle_count": 0},
    "telegram_scanner":     {"status": "idle", "last_run": None, "cycle_count": 0},
}

def get_agent_status():
    return agent_status

async def run_agent_loop(name: str, fn, interval_min: int):
    global agent_status
    await asyncio.sleep(5)
    while True:
        try:
            agent_status[name]["status"] = "active"
            await fn()
            agent_status[name]["last_run"] = datetime.now().isoformat()
            agent_status[name]["cycle_count"] += 1
            agent_status[name]["status"] = "idle"
        except Exception as e:
            print(f"❌ [{name.upper()}] Error: {e}")
            agent_status[name]["status"] = "error"
        print(f"⏳ [{name.upper()}] Next in {interval_min} min...")
        await asyncio.sleep(interval_min * 60)

async def start_all_agents():
    # Slightly offset the runtimes so we don't hit mistral/telegram rate limits at exactly the same time
    await asyncio.gather(
        run_agent_loop("news_scanner",          news_scanner_cycle,          interval_min=5),
        run_agent_loop("market_analyzer",       market_analyzer_cycle,       interval_min=30),
        run_agent_loop("opportunity_finder",    opportunity_finder_cycle,    interval_min=30),
        run_agent_loop("trending_tracker",      trending_tracker_cycle,      interval_min=15),
        run_agent_loop("indian_market_tracker", indian_market_tracker_cycle, interval_min=10),
        run_agent_loop("telegram_scanner",      telegram_scanner_cycle,      interval_min=5),
    )
