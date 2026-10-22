FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # model weights are downloaded once into this folder, which docker-compose mounts
    # from ./services/nlp/model_cache, so they are NOT baked into the image
    HF_HOME=/models

WORKDIR /app

# CPU-only PyTorch first, so sentence-transformers doesn't pull the multi-GB CUDA build
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install -r requirements.txt

# Code is also mounted from the host by docker-compose (hot reload); copying it makes the image runnable on its own
COPY app/ /app/

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
