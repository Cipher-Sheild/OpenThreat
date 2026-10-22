from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://openthreat:openthreat_dev_pass@localhost:5432/openthreat_db")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Qdrant Vector Database ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

EMBEDDING_DIM = 768
COLLECTION_NAME = 'document_embeddings'
qdrant = QdrantClient(url=os.getenv('QDRANT_URL', f'http://{QDRANT_HOST}:{QDRANT_PORT}'), timeout=10)

def ensure_vector_collection():
    collections = qdrant.get_collections().collections
    if not any(c.name == COLLECTION_NAME for c in collections):
        qdrant.create_collection(collection_name=COLLECTION_NAME,
                                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE))
