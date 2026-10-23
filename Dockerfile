FROM mirror.gcr.io/library/python:3.10-slim

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y \
    ffmpeg \
    git \
    curl \
    unzip \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Deno for yt-dlp JavaScript support
RUN curl -fsSL https://deno.land/install.sh | sh

ENV PATH="/root/.deno/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .