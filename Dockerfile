FROM python:3.11-slim

# Tesseract with Arabic language data — needed for the bot's Arabic OCR.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-ara \
        tesseract-ocr-eng \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.txt

COPY app.py webhook_server.py ./

# Render/Railway inject $PORT; default to 8080 for local docker runs.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn webhook_server:fastapi_app --host 0.0.0.0 --port ${PORT}"]
