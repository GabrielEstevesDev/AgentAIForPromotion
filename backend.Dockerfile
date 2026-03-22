FROM python:3.11-slim

# System deps for SQLite, chromadb build
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and seed database
COPY backend/ ./backend/
COPY docs/ ./docs/
COPY dev.db ./dev.db

# Create directories for runtime data
RUN mkdir -p backend/charts backend/chroma_db /app/data

# Entrypoint seeds dev.db into the persistent volume, then runs whatever CMD is passed
COPY backend-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8001

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001"]
