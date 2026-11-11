FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CHROME=/usr/bin/chromium KIT_DIR=/opt/google-maps-scraper-kit
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium git \
    && git clone --depth 1 --branch v2.3.2 https://github.com/Mahanaicoach/google-maps-scraper-kit.git $KIT_DIR \
    && apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

ENV PORT=10000
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120
