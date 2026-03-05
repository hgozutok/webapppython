from flask import Flask, render_template, request, jsonify, Response
from datetime import datetime
import json
from models import db, Contact, OnlineStatus
from whatsapp_service import WhatsAppService

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///whatsapp_tracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
whatsapp_service = WhatsAppService()

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
    contact = Contact.query.get_or_404(contact_id)
    statuses = OnlineStatus.query.filter_by(contact_id=contact_id).order_by(OnlineStatus.online_at.desc()).all()
    
    return jsonify({
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
    })

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
    print(f"Starting tracking for contact IDs: {contact_ids}")
    whatsapp_service.start_tracking(contact_ids)
    return jsonify({'success': True})

@app.route('/api/stop-tracking', methods=['POST'])
def stop_tracking():
    whatsapp_service.stop_tracking()
    return jsonify({'success': True})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)