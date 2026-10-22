import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "OpenThreat Platform API"
    VERSION: str = "1.0.0"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+psycopg2://openthreat:openthreat_dev_pass@postgres:5432/openthreat_db")
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://qdrant:6333")
    
    # Services
    NLP_SERVICE_URL: str = os.getenv("NLP_SERVICE_URL", "http://nlp-service:8000")
    
    # External APIs
    NVD_API_KEY: str = os.getenv("NVD_API_KEY", "")
    INGEST_INTERVAL_SECONDS: int = 300
    NLP_TIMEOUT_SECONDS: int = 180
    AUTO_INGEST: bool = True
    CORS_ORIGINS: str = 'http://localhost:4000,http://127.0.0.1:4000'
    
settings = Settings()
