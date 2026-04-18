FROM python:3.12-slim

# ffmpeg + 한글 폰트 + 이모지 폰트 + Chromium 시스템 라이브러리 + Node 빌드용
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    curl \
    unzip \
    ca-certificates \
    libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libasound2 libpango-1.0-0 libcairo2 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Deno (yt-dlp YouTube JS 런타임)
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- --yes \
    && ln -s /usr/local/bin/deno /usr/bin/deno || true

# Node.js 20 + npm (Remotion 렌더링용)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Remotion 패키지 설치 (이미지 빌드 시 영구)
RUN if [ -f remotion/package.json ]; then \
      cd remotion && npm install --production --silent; \
    fi
