import os
import asyncio
import requests
import feedparser
import time
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API credentials
SERP_API_KEY = os.getenv("SERP_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

class WebScraper:
    """A robust web scraper for fetching and cleaning article content."""
    @staticmethod
    async def scrape_content(url: str, timeout: int = 10) -> str | None:
        """Asynchronously scrapes and cleans the text content of a given URL."""
        if not url:
            return None
            
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=timeout)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            for script_or_style in soup(['script', 'style', 'nav', 'footer', 'aside']):
                script_or_style.decompose()

            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)

            return text[:8000] # Limit for token budgets
        except Exception as e:
            print(f"Error scraping content from {url}: {e}")
            return None

class NewsSource:
    """Base class for all news sources"""
    def __init__(self, name, source_type):
        self.name = name
        self.source_type = source_type
        self.last_check = None
    
    async def fetch_data(self):
        """Fetch data from the source"""
        raise NotImplementedError("Subclasses must implement fetch_data()")
    
    def filter_by_date(self, articles, hours=24):
        """Filter articles to only include those within the specified hours"""
        current_time = datetime.now()
        filtered_articles = []
        
        for article in articles:
            try:
                article_time = datetime.fromisoformat(article['timestamp'])
                if article_time.tzinfo is not None:
                    article_time = article_time.replace(tzinfo=None)
                time_diff = current_time - article_time
                if time_diff.total_seconds() <= hours * 3600:
                    filtered_articles.append(article)
            except (ValueError, KeyError, TypeError):
                pass
        
        return filtered_articles

class GoogleRSSFeed(NewsSource):
    """Google RSS Feed data source"""
    def __init__(self, name, source_type, topic, country="IN", language="en"):
        super().__init__(name, source_type)
        self.topic = topic
        self.country = country
        self.language = language
        self.feed_url = self._build_feed_url()
    
    def _build_feed_url(self):
        base_url = "https://news.google.com/rss"
        if self.topic:
            formatted_topic = self.topic.replace(" ", "+")
            url = f"{base_url}/search?q={formatted_topic}&hl={self.language}&gl={self.country}&ceid={self.country}:{self.language}"
        else:
            url = f"{base_url}?hl={self.language}&gl={self.country}&ceid={self.country}:{self.language}"
        return url
    
    async def fetch_data(self, limit=20, hours=24):
        results = []
        try:
            feed = await asyncio.to_thread(feedparser.parse, self.feed_url)
            for entry in feed.entries:
                timestamp = datetime.now().isoformat()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    timestamp = datetime.fromtimestamp(time.mktime(entry.published_parsed)).isoformat()
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    timestamp = datetime.fromtimestamp(time.mktime(entry.updated_parsed)).isoformat()
                
                # Extract thumbnail image from description HTML or media content
                image_url = ''
                description_text = ''
                if hasattr(entry, 'description') and entry.description:
                    try:
                        soup = BeautifulSoup(entry.description, 'html.parser')
                        img_tag = soup.find('img')
                        if img_tag and img_tag.get('src'):
                            image_url = img_tag['src']
                        description_text = soup.get_text(strip=True)
                    except Exception:
                        description_text = entry.description
                
                # Also check media_content (some RSS feeds use this)
                if not image_url and hasattr(entry, 'media_content'):
                    for media in entry.media_content:
                        if 'url' in media:
                            image_url = media['url']
                            break
                
                # Check enclosures
                if not image_url and hasattr(entry, 'enclosures'):
                    for enc in entry.enclosures:
                        if enc.get('type', '').startswith('image'):
                            image_url = enc.get('href', enc.get('url', ''))
                            break
                
                results.append({
                    'title': entry.title,
                    'snippet': description_text or entry.title,
                    'link': entry.link,
                    'source': entry.get('source', {}).get('title', 'Google News'),
                    'source_type': self.source_type,
                    'topic': self.topic,
                    'image': image_url,
                    'timestamp': timestamp
                })
        except Exception as e:
            print(f"Error fetching Google RSS data for topic '{self.topic}': {e}")
            
        self.last_check = datetime.now()
        filtered = self.filter_by_date(results, hours)
        return filtered[:limit]

class SerpNewsSearch(NewsSource):
    """News search using SERP API - specifically google_news engine"""
    def __init__(self, name, source_type, query_templates):
        super().__init__(name, source_type)
        self.query_templates = query_templates
        self.api_key = SERP_API_KEY
    
    async def fetch_data(self, limit=5, hours=24):
        results = []
        for query in self.query_templates:
            try:
                formatted_query = query.format(date=datetime.now().strftime('%B %Y'))
                params = {
                    'api_key': self.api_key,
                    'q': formatted_query,
                    'engine': 'google_news',
                    'num': limit,
                    'gl': 'in'
                }
                response = await asyncio.to_thread(requests.get, 'https://serpapi.com/search', params=params)
                data = response.json()
                
                if 'news_results' in data:
                    for result in data['news_results']:
                        timestamp = datetime.now().isoformat()
                        if 'date' in result:
                            try:
                                timestamp = datetime.strptime(result['date'], '%Y-%m-%d %H:%M:%S').isoformat()
                            except (ValueError, TypeError):
                                try:
                                    timestamp = datetime.strptime(result['date'], '%b %d, %Y').isoformat()
                                except:
                                    pass
                                    
                        results.append({
                            'title': result.get('title', ''),
                            'snippet': result.get('snippet', ''),
                            'link': result.get('link', ''),
                            'source': result.get('source', ''),
                            'source_type': self.source_type,
                            'query': formatted_query,
                            'timestamp': timestamp
                        })
            except Exception as e:
                print(f"Error fetching SERP news data: {e}")
                
        self.last_check = datetime.now()
        return self.filter_by_date(results, hours)

class SerpOrganicSearch(NewsSource):
    """Organic google search using SERP API - for general article finding"""
    def __init__(self, name, source_type, query_templates):
        super().__init__(name, source_type)
        self.query_templates = query_templates
        self.api_key = SERP_API_KEY
    
    async def fetch_data(self, limit=5):
        results = []
        for query in self.query_templates:
            try:
                formatted_query = query.format(date=datetime.now().strftime('%B %Y'))
                params = {
                    'api_key': self.api_key,
                    'q': formatted_query,
                    'engine': 'google',
                    'num': limit,
                    'gl': 'us'
                }
                response = await asyncio.to_thread(requests.get, 'https://serpapi.com/search', params=params)
                data = response.json()
                
                if 'organic_results' in data:
                    for result in data['organic_results']:
                        results.append({
                            'title': result.get('title', ''),
                            'snippet': result.get('snippet', ''),
                            'link': result.get('link', ''),
                            'source': result.get('source', 'Google Search'),
                            'source_type': self.source_type,
                            'query': formatted_query,
                            'timestamp': datetime.now().isoformat()
                        })
            except Exception as e:
                print(f"Error fetching SERP organic data: {e}")
                
        self.last_check = datetime.now()
        return results

class NewsAPISource(NewsSource):
    """NewsAPI.org data source"""
    def __init__(self, name, source_type, categories=None, countries=None):
        super().__init__(name, source_type)
        self.api_key = NEWS_API_KEY
        self.categories = categories or ['business', 'technology', 'health']
        self.countries = countries or ['in']
        
    async def fetch_data(self, limit=20, hours=24):
        results = []
        try:
            for country in self.countries:
                for category in self.categories:
                    params = {
                        'apiKey': self.api_key,
                        'country': country,
                        'category': category,
                        'pageSize': limit
                    }
                    response = await asyncio.to_thread(requests.get, 'https://newsapi.org/v2/top-headlines', params=params)
                    data = response.json()
                    
                    if data.get('status') == 'ok' and 'articles' in data:
                        for article in data['articles']:
                            results.append({
                                'title': article.get('title', ''),
                                'snippet': article.get('description', ''),
                                'link': article.get('url', ''),
                                'source': article.get('source', {}).get('name', ''),
                                'source_type': self.source_type,
                                'category': category,
                                'timestamp': article.get('publishedAt', datetime.now().isoformat())
                            })
        except Exception as e:
            print(f"Error fetching News API data: {e}")
            
        self.last_check = datetime.now()
        return self.filter_by_date(results, hours)

class TelegramChannelScraper(NewsSource):
    """Scrapes public posts from a Telegram channel using web preview."""
    def __init__(self, name, source_type, channel_slug="CIG_telegram"):
        super().__init__(name, source_type)
        self.channel_slug = channel_slug

    async def fetch_data(self, limit=50, hours=24):
        results = []
        base_url = f"https://t.me/s/{self.channel_slug}"
        current_url = base_url
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        
        try:
            while len(results) < limit:
                response = await asyncio.to_thread(requests.get, current_url, headers=headers, timeout=10)
                if response.status_code != 200:
                    break
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                messages = soup.find_all('div', class_='tgme_widget_message')
                if not messages:
                    break
                    
                # Process latest messages first on this page
                page_results = []
                for msg in reversed(messages):
                    if len(results) + len(page_results) >= limit:
                        break
                        
                    post_url = msg.get('data-post', '')
                    post_id = post_url.split('/')[-1] if post_url else ''
                    
                    text_div = msg.find('div', class_='tgme_widget_message_text')
                    if not text_div: continue
                    text = text_div.get_text(separator=' ', strip=True)
                    if len(text) < 10: continue
                        
                    time_wrap = msg.find('a', class_='tgme_widget_message_date')
                    timestamp = datetime.now().isoformat()
                    if time_wrap:
                        time_tag = time_wrap.find('time')
                        if time_tag and time_tag.get('datetime'):
                            timestamp = time_tag.get('datetime')
                            
                    page_results.append({
                        'title': f"Intel Update from {self.channel_slug}",
                        'snippet': text,
                        'link': f"https://t.me/{self.channel_slug}/{post_id}" if post_id else base_url,
                        'source': f"Telegram: {self.channel_slug}",
                        'telegram_post_id': post_id,
                        'source_type': self.source_type,
                        'timestamp': timestamp,
                        'image': ''
                    })
                
                results.extend(page_results)
                
                if len(results) >= limit:
                    break
                    
                oldest_post_url = messages[0].get('data-post', '')
                if not oldest_post_url:
                    break
                    
                oldest_id = oldest_post_url.split('/')[-1]
                if not oldest_id.isdigit():
                    break
                    
                current_url = f"{base_url}?before={oldest_id}"
                
        except Exception as e:
            print(f"Error fetching Telegram data from {current_url}: {e}")
            
        self.last_check = datetime.now()
        return self.filter_by_date(results, hours)
