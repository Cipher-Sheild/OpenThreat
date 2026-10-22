import requests
from datetime import datetime
from typing import List, Dict, Any
import hashlib

from collectors.base_collector import BaseCollector

class CISACollector(BaseCollector):
    def __init__(self):
        self.last_error = None
        # Official CISA KEV public JSON feed
        self.feed_url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
        
    def fetch_new_documents(self, limit: int = 10, known_ids=None) -> List[Dict[str, Any]]:
        """
        Fetches the latest Known Exploited Vulnerabilities from CISA.
        """
        try:
            response = requests.get(self.feed_url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            # Sort vulnerabilities by date added (newest first)
            vulnerabilities = data.get("vulnerabilities", [])
            vulnerabilities.sort(key=lambda x: x.get("dateAdded", ""), reverse=True)
            
            docs = []
            for item in vulnerabilities[:limit]:
                cve_id = item.get("cveID")
                vendor = item.get("vendorProject", "Unknown")
                product = item.get("product", "Unknown")
                desc = item.get("shortDescription", "")
                action = item.get("requiredAction", "")
                
                # Combine fields to give the NLP model rich context
                full_content = f"Vulnerability {cve_id} in {vendor} {product}. {desc} Required Action: {action}."
                
                doc = {
                    "title": f"CISA KEV: {cve_id}",
                    "content": full_content,
                    "source_url": self.feed_url,
                    "published_at": item.get("dateAdded"),
                    "external_id": f"cisa_{cve_id}",
                    "source_name": "CISA_KEV",
                    "source_type": "json_feed"
                }
                docs.append(doc)
                
            return docs
            
        except Exception as e:
            self.last_error = 'CISA request failed; check connectivity.'
            print(f"Error fetching from CISA KEV: {e}")
            return []
