import os
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramServiceSync:
    """Telegram Bot API wrapper using direct HTTP requests (no async)."""
    
    def __init__(self, token=None, chat_id=None):
        self.token = token or os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID')
        self.api_url = f"https://api.telegram.org/bot{self.token}" if self.token else None
    
    def is_configured(self):
        return bool(self.token and self.chat_id and self.api_url)
    
    def _make_request(self, method, data=None, files=None):
        """Make API request to Telegram."""
        if not self.is_configured():
            logger.warning("Telegram not configured")
            return None
        
        url = f"{self.api_url}/{method}"
        
        try:
            if files:
                response = requests.post(url, data=data, files=files, timeout=30)
            else:
                response = requests.post(url, json=data, timeout=30)
            
            result = response.json()
            if result.get('ok'):
                return result.get('result')
            else:
                logger.error(f"Telegram API error: {result.get('description')}")
                return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None
    
    def send_message(self, text, photo_path=None):
        """Send message or photo to Telegram."""
        if not self.is_configured():
            print("Telegram not configured")
            return False
        
        # Send photo with caption if photo exists
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                files = {'photo': f}
                data = {
                    'chat_id': self.chat_id,
                    'caption': text,
                    'parse_mode': 'HTML'
                }
                result = self._make_request('sendPhoto', data=data, files=files)
            
            # Clean up photo after sending
            try:
                os.remove(photo_path)
            except:
                pass
            
            if result:
                print(f"[TELEGRAM] Photo sent successfully")
                return True
            return False
        
        # Send just text message
        data = {
            'chat_id': self.chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        result = self._make_request('sendMessage', data=data)
        
        if result:
            print(f"[TELEGRAM] Message sent: {text[:50]}...")
            return True
        return False
    
    def notify_online(self, contact_name, screenshot_path=None, message=None):
        """Send notification when a contact goes online."""
        if message is None:
            message = f"🔔 <b>{contact_name}</b> şimdi online oldu!"
        
        return self.send_message(message, screenshot_path)