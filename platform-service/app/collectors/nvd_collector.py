import requests
from datetime import datetime
from typing import List, Dict, Any
import time

from collectors.base_collector import BaseCollector
from core.config import settings

class NVDCollector(BaseCollector):
    def __init__(self):
        self.last_error = None
        self.base_url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
        self.api_key = settings.NVD_API_KEY
        
    def fetch_new_documents(self, limit: int = 5, known_ids=None) -> List[Dict[str, Any]]:
        """
        Fetches the latest CVEs from the NVD API.
        We strictly limit this to avoid rate limits, even with an API key.
        """
        headers = {}
        if self.api_key:
            headers["apiKey"] = self.api_key
            
        from datetime import datetime, timedelta
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=7)
        
        params = {
            "resultsPerPage": min(2000, max(limit, 200)),
            "pubStartDate": start_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "pubEndDate": end_date.strftime("%Y-%m-%dT%H:%M:%S.000")
        }
        
        try:
            response = requests.get(self.base_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            docs = []
            records = sorted(data.get('vulnerabilities', []), key=lambda item: item.get('cve', {}).get('published', ''), reverse=True)
            for item in records[:limit]:
                cve = item.get("cve", {})
                cve_id = cve.get("id")
                
                # Extract English description
                descriptions = cve.get("descriptions", [])
                desc_text = next((d.get("value") for d in descriptions if d.get("lang") == "en"), "")
                
                # Build normalized document dict
                doc = {
                    "title": cve_id,
                    "content": f"{cve_id}. {desc_text}",
                    "source_url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                    "published_at": cve.get("published"),
                    "external_id": cve_id,
                    "source_name": "NVD",
                    "source_type": "api_feed"
                }
                docs.append(doc)
                
            return docs
            
        except Exception as e:
            self.last_error = 'NVD request failed; check connectivity or API configuration.'
            print(f"Error fetching from NVD: {e}")
            return []
