FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# Python-Abhängigkeiten zuerst installieren
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Passende Chromium-Version samt Linux-Abhängigkeiten installieren
RUN python -m playwright install --with-deps chromium

# Anwendung kopieren
COPY . .

# Benötigte Verzeichnisse anlegen
RUN mkdir -p /app/data \
    /app/uploads \
    /app/playwright_profile \
    /app/storage

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]