import asyncio
from core_scrapers import GoogleRSSFeed

async def test():
    src = GoogleRSSFeed(name='Nifty', source_type='Financial', topic='Nifty 50 today')
    print('Fetching:', src.feed_url)
    data = await src.fetch_data(limit=5, hours=12)
    print('Filtered Length:', len(data))
    
    import feedparser
    feed = feedparser.parse(src.feed_url)
    raw = feed.entries
    print('Raw Length:', len(raw))
    if raw:
        print('First item date:', getattr(raw[0], 'published', 'None'))

asyncio.run(test())
