FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    CHROME_PATH=/usr/bin/chromium

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        ffmpeg \
        # ===== Pillow =====
        libjpeg62-turbo \
        libpng16-16 \
        libfreetype6 \
        zlib1g \
        # ===== Шрифты для PIL (кириллица) =====
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-color-emoji \
        # ===== Chromium для nodriver =====
        chromium \
        chromium-driver \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

RUN groupadd --system --gid 10001 bot \
    && useradd --system --uid 10001 --gid bot --home-dir /app bot \
    && mkdir --parents /app/data \
    && chown --recursive bot:bot /app

COPY --chown=bot:bot main.py search_ranking.py ./

USER bot

VOLUME ["/app/data"]

CMD ["python", "main.py"]
