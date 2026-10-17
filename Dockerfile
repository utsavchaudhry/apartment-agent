# --- dashboard -----------------------------------------------------------
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- agent + API ---------------------------------------------------------
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent/ ./agent/
COPY --from=web /web/dist ./web/dist

ENV DATA_DIR=/data PYTHONUNBUFFERED=1 TZ=Europe/Berlin
VOLUME /data
EXPOSE 8080
WORKDIR /app/agent
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')"
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
