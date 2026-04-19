FROM python:3.12-slim

# ffmpeg + 한글 폰트 + 이모지 폰트 + Chromium 시스템 라이브러리 + Node 빌드용
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    fonts-nanum \
    fonts-nanum-extra \
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

# ─ 한글 폰트 일괄 다운로드 (Pretendard + 기업 무료 폰트) ─
# 각 폰트는 공개 GitHub·CDN 미러에서 가져옴 (재배포 허용된 라이선스만)
RUN mkdir -p /opt/korean-fonts && cd /opt/korean-fonts \
    # Pretendard 9 weights (OFL 1.1, orioncactus/pretendard)
    && for w in Thin ExtraLight Light Regular Medium SemiBold Bold ExtraBold Black; do \
         curl -sL -o "Pretendard-$w.otf" \
           "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/public/static/Pretendard-$w.otf" || true; \
       done \
    # 여기어때 잘난체 (무료 상업이용)
    && curl -sL -o "JalnanGothic.ttf" \
         "https://cdn.jsdelivr.net/gh/fonts-archive/JalnanGothic/JalnanGothic.ttf" || true \
    # 배달의민족 도현·주아·한나·연성·기랑해랑·을지로체 (OFL, BMHANNAPro 등)
    && curl -sL -o "BMDOHYEON.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/BMDOHYEON/BMDOHYEON.ttf" || true \
    && curl -sL -o "BMJUA.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/BMJUA/BMJUA.ttf" || true \
    && curl -sL -o "BMHANNAPro.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/BMHANNAPro/BMHANNAPro.ttf" || true \
    && curl -sL -o "BMYEONSUNG.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/BMYEONSUNG/BMYEONSUNG.ttf" || true \
    && curl -sL -o "BMEULJIRO.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/BMEULJIRO/BMEULJIRO.ttf" || true \
    # G마켓 산스 Bold (무료 상업용)
    && curl -sL -o "GmarketSansTTFBold.ttf" \
         "https://cdn.jsdelivr.net/gh/fonts-archive/GmarketSans/GmarketSansTTFBold.ttf" || true \
    && curl -sL -o "GmarketSansTTFMedium.ttf" \
         "https://cdn.jsdelivr.net/gh/fonts-archive/GmarketSans/GmarketSansTTFMedium.ttf" || true \
    # 에스코어드림 9 weights
    && for w in 1 2 3 4 5 6 7 8 9; do \
         curl -sL -o "SCoreDream-${w}.otf" \
           "https://cdn.jsdelivr.net/gh/fonts-archive/SCoreDream/SCDream${w}.otf" || true; \
       done \
    # Cafe24 시리즈
    && curl -sL -o "Cafe24Dangdanghae.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/Cafe24Dangdanghae/Cafe24Dangdanghae.ttf" || true \
    && curl -sL -o "Cafe24Ssurround.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/Cafe24Ssurround/Cafe24Ssurround.ttf" || true \
    && curl -sL -o "Cafe24Ohsquare.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/Cafe24Ohsquare/Cafe24Ohsquare.ttf" || true \
    && curl -sL -o "Cafe24Syongsyong.ttf" "https://cdn.jsdelivr.net/gh/fonts-archive/Cafe24Syongsyong/Cafe24Syongsyong.ttf" || true \
    # tvN 즐거운이야기
    && curl -sL -o "tvN_EnjoyStoryB.ttf" \
         "https://cdn.jsdelivr.net/gh/fonts-archive/tvN_EnjoyStory/tvN_EnjoyStoryB.ttf" || true \
    # 메이플스토리 Bold
    && curl -sL -o "Maplestory_Bold.ttf" \
         "https://cdn.jsdelivr.net/gh/fonts-archive/Maplestory/Maplestory_OTF_Bold.otf" || true \
    # 교보한 스토리 가벼운체
    && curl -sL -o "KyoboHandwriting2020.ttf" \
         "https://cdn.jsdelivr.net/gh/fonts-archive/KyoboHandwriting2020/KyoboHandwriting2020A.ttf" || true \
    # 학교안심 곧은샘
    && curl -sL -o "SchoolSafetyBareunSam.ttf" \
         "https://cdn.jsdelivr.net/gh/fonts-archive/SchoolSafety/SchoolSafetyBareunSam.ttf" || true \
    # 실패한 작은 파일(404 응답 등) 제거 — 10KB 미만 삭제
    && find /opt/korean-fonts -type f -size -10000c -delete \
    && ls -la /opt/korean-fonts | head -60

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Remotion 패키지 설치 (이미지 빌드 시 영구)
RUN if [ -f remotion/package.json ]; then \
      cd remotion && npm install --production --silent; \
    fi
