from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseCollector(ABC):
    """
    Abstract base interface for CTI document collectors.
    """
    
    @abstractmethod
    def fetch_new_documents(self) -> List[Dict[str, Any]]:
        """
        Fetch new documents from the source.
        
        Returns:
            List of normalized document dictionaries containing:
            - title (str)
            - content (str)
            - source_url (str)
            - published_at (datetime)
            - additional_metadata (dict)
        """
        pass

# TODO: Implement NVD, CISA, and Vendor Blog collectors inheriting from this base class
