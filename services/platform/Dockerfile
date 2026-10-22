FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (needed for psycopg2, etc.)
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The code will be mounted from the host in docker-compose for dev
COPY app/ /app/
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
