# WhatsApp Tracker - Server Deployment Guide

## Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **Python**: 3.8 or higher
- **RAM**: Minimum 2GB (4GB recommended for browser)
- **Display**: Not required (runs headless)

## Installation Steps

### 1. Prepare the Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
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
    xauth
```

### 2. Install the Application

```bash
# Clone or upload your project
cd /var/www
git clone https://github.com/your-repo/whatsapp-tracker.git
cd whatsapp-tracker

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 3. Configure Environment

```bash
# Edit .env file
nano .env
```

Add your Telegram credentials:
```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 4. Run with Systemd (Production)

```bash
# Create systemd service
sudo nano /etc/systemd/system/whatsapp-tracker.service
```

Add this content:
```ini
[Unit]
Description=WhatsApp Tracker
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/whatsapp-tracker
Environment="PATH=/var/www/whatsapp-tracker/venv/bin"
ExecStart=/var/www/whatsapp-tracker/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable whatsapp-tracker
sudo systemctl start whatsapp-tracker

# Check status
sudo systemctl status whatsapp-tracker
```

### 5. Run with Nginx (Optional)

```bash
# Install nginx
sudo apt install -y nginx

# Create nginx config
sudo nano /etc/nginx/sites-available/whatsapp-tracker
```

Add:
```nginx
server {
    listen 80;
    server_name your-server-ip;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/whatsapp-tracker /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## Important Notes

1. **Playwright requires display**: Set environment variable `PLAYWRIGHT_BROWSERS_PATH=0` or install browsers properly
2. **Session persistence**: The `whatsapp_session` folder stores browser session - backup this for persistence
3. **Port**: Default port is 5000, make sure it's open in firewall
4. **Screen recording**: For debugging, you may need to set `headless=False` temporarily

## Troubleshooting

```bash
# Check if port is open
sudo ufw allow 5000/tcp

# View logs
sudo journalctl -u whatsapp-tracker -f
```

## For Railway/Render/Heroku Deployment

This app uses Playwright which requires:
- A real browser (not available on serverless)
- Persistent filesystem

These platforms are **NOT recommended**. Use a VPS instead:
- DigitalOcean (starts at $4/month)
- Linode (starts at $5/month)
- Hetzner (starts at €3/month)