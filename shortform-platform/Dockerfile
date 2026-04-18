FROM python:3.12-slim

# ffmpeg + 한글/이모지 폰트 + (Deno: yt-dlp JS 런타임용) curl/unzip
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-nanum fonts-nanum-extra \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Deno (yt-dlp YouTube JS 런타임)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- --yes \
    && ln -s /usr/local/bin/deno /usr/bin/deno || true

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
