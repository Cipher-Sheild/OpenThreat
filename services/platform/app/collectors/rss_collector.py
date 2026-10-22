import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any
import hashlib
import re
from html import unescape
from bs4 import BeautifulSoup
from core.dates import iso_date

from collectors.base_collector import BaseCollector

class RSSCollector(BaseCollector):
    def __init__(self):
        self.last_error = None
        # High-verbosity, narrative-heavy threat intelligence feeds
        self.feeds = [
            {"name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/"},
            {"name": "The_Hacker_News", "url": "https://feeds.feedburner.com/TheHackersNews"},
            {"name": "KrebsOnSecurity", "url": "https://krebsonsecurity.com/feed/"}
        ]
        
    def _clean_html(self, raw_html: str) -> str:
        """Removes HTML tags from RSS description fields."""
        cleanr = re.compile('<.*?>')
        cleantext = re.sub(cleanr, '', raw_html)
        return unescape(cleantext).strip()

    def _article_text(self, html: str) -> str:
        """Extract an article body, never unrelated paragraphs from the whole page."""
        soup = BeautifulSoup(html, 'html.parser')
        body = soup.select_one('[itemprop="articleBody"], .articleBody, .article-body, .post-body, .entry-content, article')
        if body is None:
            return ''
        for noise in body.select('script, style, nav, aside, footer, form, .related, .related-posts, .newsletter, .advertisement, .ad'):
            noise.decompose()
        paragraphs = [p.get_text(' ', strip=True) for p in body.find_all(['p', 'li', 'h2', 'h3'])]
        return '\n\n'.join(p for p in paragraphs if len(p) > 20)

    def fetch_new_documents(self, limit: int = 15, known_ids=None) -> List[Dict[str, Any]]:
        """
        Fetches the latest blog posts from cybersecurity RSS feeds.
        These provide the verbose, narrative text needed to test complex Relation Extraction.
        """
        docs = []
        
        for feed in self.feeds:
            try:
                # Add headers to avoid basic bot blocks
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                response = requests.get(feed["url"], headers=headers, timeout=10)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                
                # Standard RSS 2.0 parsing
                items = root.findall('.//item')
                
                count = 0
                for item in items:
                    if count >= limit:
                        break
                        
                    title = item.findtext('title', 'Unknown Title')
                    link = item.findtext('link', feed["url"])
                    ext_id = hashlib.md5(link.encode('utf-8')).hexdigest()
                    if known_ids and f'rss_{ext_id}' in known_ids:
                        continue
                    description = item.findtext('description', '')
                    pub_date = iso_date(item.findtext('pubDate'))
                    
                    # Fetch the full article HTML
                    try:
                        article_resp = requests.get(link, headers=headers, timeout=5)
                        article_resp.raise_for_status()
                        article_text = self._article_text(article_resp.text)
                        if article_text:
                            full_content = f"{title}.\n\n" + article_text
                        else:
                            clean_desc = self._clean_html(description)
                            full_content = f"{title}. {clean_desc}"
                    except Exception as e:
                        clean_desc = self._clean_html(description)
                        full_content = f"{title}. {clean_desc}"
                    
                    # Generate a reproducible ID based on the URL
                    ext_id = hashlib.md5(link.encode('utf-8')).hexdigest()
                    
                    doc = {
                        "title": title[:200], # truncate if extremely long
                        "content": full_content,
                        "source_url": link,
                        "published_at": pub_date,
                        "external_id": f"rss_{ext_id}",
                        "source_name": feed["name"],
                        "source_type": "rss_feed"
                    }
                    docs.append(doc)
                    count += 1
                    
            except Exception as e:
                self.last_error = 'One or more RSS feeds could not be fetched.'
                print(f"Error fetching RSS feed {feed['name']}: {e}")
                continue
                
        return docs
