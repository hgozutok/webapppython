FROM python:3.12-slim

# Install system dependencies for Playwright and build tools
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    xauth \
    xvfb \
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-wqy-zenhei \
    nginx \
    && rm -rf /var/lib/apt/lists/*

# Pre-install greenlet (needed by SQLAlchemy)
RUN pip install --no-cache-dir --force-reinstall greenlet

# Set environment variables for Playwright
ENV PLAYWRIGHT_DISABLE_ASYNCIO=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (without system deps - install manually)
RUN playwright install chromium

# Copy application files
COPY . .

# Expose ports
EXPOSE 5000 80

# Run the application with explicit host binding using xvfb for Playwright and nginx
CMD ["sh", "-c", "rm -f /tmp/.X99-lock && Xvfb :99 -screen 0 1280x720x24 -ac +extension GLX +render -noreset & nginx && python -u app.py --host 0.0.0.0"]