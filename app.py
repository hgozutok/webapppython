from flask import Flask, render_template, request, jsonify, Response
from datetime import datetime
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from models import db, Contact, OnlineStatus
from whatsapp_service import WhatsAppService
from telegram_service import TelegramServiceSync

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whatsapp_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
whatsapp_service = WhatsAppService()

# Telegram Service - environment variable'dan al
telegram_service = None

def get_telegram_config():
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    return bot_token, chat_id

def on_contact_online(contact_info):
    """Contact online olduğunda Telegram bildirimi gönder"""
    global telegram_service
    print(f"[TELEGRAM DEBUG] on_contact_online called with: {contact_info}")
    
    def send_notification():
        """Ayrı thread'de çalıştır"""
        global telegram_service
        print(f"[TELEGRAM DEBUG] send_notification started")
        
        if telegram_service is None:
            bot_token, chat_id = get_telegram_config()
            print(f"[TELEGRAM DEBUG] bot_token={bot_token}, chat_id={chat_id}")
            if bot_token and chat_id:
                telegram_service = TelegramServiceSync(bot_token, chat_id)
        
        if telegram_service:
            try:
                name = contact_info.get('name', 'Bilinmiyor')
                phone = contact_info.get('phone', '')
                screenshot_path = contact_info.get('screenshot_path')
                print(f"[TELEGRAM DEBUG] Sending notification for {name}, screenshot: {screenshot_path}")
                
                message = f"🚨 *{name}* çevrimiçi oldu!\n📱 Tel: {phone}"
                telegram_service.notify_online(name, screenshot_path, message)
                print(f"[TELEGRAM] Bildirim gönderildi: {name}")
            except Exception as e:
                print(f"[TELEGRAM ERROR] {e}")
        else:
            print("[TELEGRAM ERROR] telegram_service is None - not configured?")
    
    # Telegram bildirimini ayrı thread'de çalıştır
    import threading
    notification_thread = threading.Thread(target=send_notification, daemon=True)
    notification_thread.start()

# WhatsApp Service'e callback ata
whatsapp_service.on_online_callback = on_contact_online

# Status change callback for database operations (runs in main Flask thread)
import queue

def setup_status_callback():
    """Set up callback to handle database operations from tracking loop"""
    status_queue = queue.Queue()
    
    def handle_status_changes():
        """Process status changes in main thread to avoid greenlet issues"""
        while True:
            try:
                msg = status_queue.get(timeout=1)
                
                if msg.get('type') == 'get_contacts':
                    # Get contact info from DB and send back
                    response_queue = msg.get('response_queue')
                    contact_ids = msg.get('contact_ids', [])
                    
                    with app.app_context():
                        contacts = Contact.query.filter(Contact.id.in_(contact_ids)).all()
                        contacts_data = [{'id': c.id, 'name': c.name, 'phone': c.phone} for c in contacts]
                        response_queue.put(contacts_data)
                        
                elif msg.get('type') == 'status_change':
                    # Update database with status change
                    contact_id = msg.get('contact_id')
                    is_online = msg.get('is_online')
                    timestamp = msg.get('timestamp')
                    contact_name = msg.get('contact_name')
                    
                    with app.app_context():
                        contact = Contact.query.get(contact_id)
                        if contact:
                            contact.is_online = is_online
                            
                            if is_online:
                                contact.last_online_at = timestamp
                                status = OnlineStatus(
                                    contact_id=contact.id,
                                    online_at=timestamp,
                                    offline_at=None,
                                    duration_seconds=0
                                )
                                db.session.add(status)
                            else:
                                if contact.last_online_at:
                                    duration = (timestamp - contact.last_online_at).total_seconds()
                                    contact.total_online_seconds += duration
                                    contact.last_offline_at = timestamp
                                    
                                    status = OnlineStatus(
                                        contact_id=contact.id,
                                        online_at=contact.last_online_at,
                                        offline_at=timestamp,
                                        duration_seconds=duration
                                    )
                                    db.session.add(status)
                            
                            db.session.commit()
                            print(f"[DB] Updated {contact_name} -> is_online={is_online}")
                            
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[ERROR] Status callback error: {e}")
                import traceback
                traceback.print_exc()
    
    # Start the status handler thread
    import threading
    handler_thread = threading.Thread(target=handle_status_changes, daemon=True)
    handler_thread.start()
    
    return status_queue

# Set up the status callback queue
status_change_queue = setup_status_callback()

# Set the callback on WhatsApp service
def status_change_callback(msg):
    status_change_queue.put(msg)

whatsapp_service.on_status_change_callback = status_change_callback

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/contacts', methods=['GET'])
def get_contacts():
    contacts = Contact.query.all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'phone': c.phone,
        'is_online': c.is_online,
        'last_online_at': c.last_online_at.isoformat() if c.last_online_at else None,
        'last_offline_at': c.last_offline_at.isoformat() if c.last_offline_at else None,
        'total_online_seconds': c.total_online_seconds,
        'created_at': c.created_at.isoformat() if c.created_at else None
    } for c in contacts])

@app.route('/api/contacts', methods=['POST'])
def add_contact():
    data = request.json
    contact = Contact(
        name=data['name'],
        phone=data['phone'],
        is_online=False,
        total_online_seconds=0
    )
    db.session.add(contact)
    db.session.commit()
    return jsonify({'id': contact.id, 'name': contact.name, 'phone': contact.phone})

@app.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
def delete_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    OnlineStatus.query.filter_by(contact_id=contact_id).delete()
    db.session.delete(contact)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/contacts/<int:contact_id>', methods=['PUT'])
def update_contact(contact_id):
    contact = Contact.query.get_or_404(contact_id)
    data = request.json
    
    if 'name' in data:
        contact.name = data['name']
    if 'phone' in data:
        contact.phone = data['phone']
    
    db.session.commit()
    return jsonify({
        'id': contact.id,
        'name': contact.name,
        'phone': contact.phone
    })

@app.route('/api/status', methods=['POST'])
def update_status():
    data = request.json
    contact = Contact.query.get_or_404(data['contact_id'])
    
    contact.is_online = data['is_online']
    if data['is_online']:
        contact.last_online_at = datetime.now()
    else:
        if contact.last_online_at:
            duration = (datetime.now() - contact.last_online_at).total_seconds()
            contact.total_online_seconds += duration
            contact.last_offline_at = datetime.now()
            
            status = OnlineStatus(
                contact_id=contact.id,
                online_at=contact.last_online_at,
                offline_at=datetime.now(),
                duration_seconds=duration
            )
            db.session.add(status)
    
    db.session.commit()
    return jsonify({'success': True, 'status': data['is_online'], 'contact_name': contact.name})

@app.route('/api/whatsapp/connect', methods=['POST'])
def connect_whatsapp():
    try:
        result = whatsapp_service.connect()
        print(f"Connect result: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"Connect error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/whatsapp/qr', methods=['GET'])
def get_qr():
    qr = whatsapp_service.get_qr()
    return jsonify({'qr': qr})

@app.route('/api/whatsapp/disconnect', methods=['POST'])
def disconnect_whatsapp():
    whatsapp_service.disconnect()
    return jsonify({'success': True})

@app.route('/api/whatsapp/status', methods=['GET'])
def whatsapp_status():
    return jsonify({'connected': whatsapp_service.is_connected()})

@app.route('/api/whatsapp/manual-connect', methods=['POST'])
def manual_connect():
    whatsapp_service.connected = True
    return jsonify({'success': True, 'connected': True})

@app.route('/api/statistics/<int:contact_id>', methods=['GET'])
def get_statistics(contact_id):
    try:
        contact = Contact.query.get_or_404(contact_id)
        statuses = OnlineStatus.query.filter_by(contact_id=contact_id).order_by(OnlineStatus.online_at.desc()).all()
        
        return jsonify({
            'contact': {
                'name': contact.name,
                'phone': contact.phone,
                'total_online_seconds': contact.total_online_seconds
            },
            'history': [{
                'online_at': s.online_at.isoformat() if s.online_at else None,
                'offline_at': s.offline_at.isoformat() if s.offline_at else None,
                'duration_seconds': s.duration_seconds
            } for s in statuses]
        })
    except Exception as e:
        print(f"Error getting statistics: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/<int:contact_id>', methods=['GET'])
def export_data(contact_id):
    format_type = request.args.get('format', 'json')
    contact = Contact.query.get_or_404(contact_id)
    statuses = OnlineStatus.query.filter_by(contact_id=contact_id).order_by(OnlineStatus.online_at.desc()).all()
    
    data = {
        'contact': {
            'name': contact.name,
            'phone': contact.phone,
            'total_online_seconds': contact.total_online_seconds
        },
        'history': [{
            'online_at': s.online_at.isoformat(),
            'offline_at': s.offline_at.isoformat(),
            'duration_seconds': s.duration_seconds
        } for s in statuses]
    }
    
    if format_type == 'csv':
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Online At', 'Offline At', 'Duration (seconds)'])
        for s in statuses:
            writer.writerow([s.online_at, s.offline_at, s.duration_seconds])
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename={contact.name}_online_history.csv'
        return response
    
    return jsonify(data)

@app.route('/api/start-tracking', methods=['POST'])
def start_tracking():
    data = request.json
    contact_ids = data.get('contact_ids', [])
    use_dom = data.get('use_dom', True)
    use_image = data.get('use_image', True)
    print(f"Starting tracking for contact IDs: {contact_ids}, DOM: {use_dom}, Image: {use_image}")
    whatsapp_service.start_tracking(contact_ids, use_dom, use_image)
    return jsonify({'success': True})

@app.route('/api/stop-tracking', methods=['POST'])
def stop_tracking():
    whatsapp_service.stop_tracking()
    return jsonify({'success': True})

@app.route('/api/telegram/config', methods=['GET'])
def get_telegram_config_api():
    """Mevcut Telegram config durumunu döndür"""
    bot_token, chat_id = get_telegram_config()
    return jsonify({
        'configured': bool(bot_token and chat_id),
        'has_token': bool(bot_token),
        'has_chat_id': bool(chat_id)
    })

@app.route('/api/telegram/config', methods=['POST'])
def set_telegram_config():
    """Telegram config ayarla"""
    data = request.json
    bot_token = data.get('bot_token')
    chat_id = data.get('chat_id')
    
    if not bot_token or not chat_id:
        return jsonify({'success': False, 'message': 'bot_token ve chat_id gerekli'})
    
    # Environment variable olarak kaydet
    os.environ['TELEGRAM_BOT_TOKEN'] = bot_token
    os.environ['TELEGRAM_CHAT_ID'] = chat_id
    
    # Global telegram_service'i yeniden oluştur
    global telegram_service
    telegram_service = TelegramServiceSync(bot_token, chat_id)
    
    print(f"[TELEGRAM] Konfigürasyon güncellendi")
    return jsonify({'success': True, 'message': 'Telegram ayarlandı'})

@app.route('/api/telegram/test', methods=['POST'])
def test_telegram():
    """Telegram bağlantısını test et"""
    global telegram_service
    
    if telegram_service is None:
        bot_token, chat_id = get_telegram_config()
        if bot_token and chat_id:
            telegram_service = TelegramServiceSync(bot_token, chat_id)
    
    if telegram_service is None:
        return jsonify({'success': False, 'message': 'Telegram ayarlanmamış'})
    
    try:
        result = telegram_service.send_message("✅ WhatsApp Tracker bağlantısı başarılı!")
        return jsonify({'success': True, 'message': 'Test mesajı gönderildi'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)