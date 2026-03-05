let contacts = [];
let whatsappConnected = false;
let tracking = false;
let refreshInterval = null;
let contactStatuses = {};

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}h ${minutes}m ${secs}s`;
    } else if (minutes > 0) {
        return `${minutes}m ${secs}s`;
    } else {
        return `${secs}s`;
    }
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString('tr-TR');
}

function formatRelativeTime(dateString) {
    if (!dateString) return 'Bilinmiyor';
    
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    
    if (minutes < 1) return 'Az önce';
    if (minutes < 60) return `${minutes} dakika önce`;
    if (hours < 24) return `${hours} saat önce`;
    if (days < 7) return `${days} gün önce`;
    
    return formatDate(dateString);
}

function sendNotification(title, body) {
    if ('Notification' in window) {
        if (Notification.permission === 'granted') {
            new Notification(title, {
                body: body,
                icon: '/static/icon.png'
            });
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    new Notification(title, {
                        body: body,
                        icon: '/static/icon.png'
                    });
                }
            });
        }
    }
}

async function loadContacts() {
    try {
        const response = await fetch('/api/contacts');
        const newContacts = await response.json();
        
        newContacts.forEach(newContact => {
            const oldContact = contacts.find(c => c.id === newContact.id);
            
            if (oldContact) {
                if (oldContact.is_online !== newContact.is_online) {
                    if (newContact.is_online) {
                        sendNotification('🟢 Online!', `${newContact.name} şu an çevrimiçi!`);
                        console.log(`${newContact.name} is now ONLINE`);
                    } else {
                        sendNotification('🔴 Çevrimdışı', `${newContact.name} çevrimdışı oldu`);
                        console.log(`${newContact.name} is now OFFLINE`);
                    }
                }
            }
        });
        
        contacts = newContacts;
        renderContacts();
    } catch (error) {
        console.error('Error loading contacts:', error);
    }
}

function renderContacts() {
    const grid = document.getElementById('contacts-grid');
    
    if (contacts.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📱</div>
                <h3>Henüz takip edilen numara yok</h3>
                <p>Numara eklemek için sağ alttaki + butonuna tıklayın</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = contacts.map(contact => `
        <div class="contact-card" id="contact-${contact.id}">
            <div class="contact-header">
                <div>
                    <div class="contact-name">${contact.name}</div>
                    <div class="contact-phone">${contact.phone}</div>
                </div>
            </div>
            
            <div class="online-status">
                <div class="online-dot ${contact.is_online ? 'online' : ''}"></div>
                <div class="online-text">${contact.is_online ? 'Çevrimiçi' : 'Çevrimdışı'}</div>
            </div>
            
            <div class="stats-section">
                <div class="stat-row">
                    <span>Son Online:</span>
                    <span class="stat-value">${contact.is_online ? 'Şu an' : formatRelativeTime(contact.last_online_at)}</span>
                </div>
                ${!contact.is_online && contact.last_offline_at ? `
                <div class="stat-row">
                    <span>Son Çevrimdışı:</span>
                    <span class="stat-value">${formatRelativeTime(contact.last_offline_at)}</span>
                </div>
                ` : ''}
                <div class="stat-row">
                    <span>Toplam Süre:</span>
                    <span class="stat-value">${formatDuration(contact.total_online_seconds)}</span>
                </div>
            </div>
            
            <div class="action-buttons">
                <button class="action-btn stats-btn" onclick="showStatistics(${contact.id})">📊 İstatistikler</button>
                <button class="action-btn edit-btn" onclick="editContact(${contact.id})">✏️ Düzenle</button>
                <button class="action-btn delete-btn" onclick="deleteContact(${contact.id})">🗑️ Sil</button>
            </div>
        </div>
    `).join('');
}

function openModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

async function addContact() {
    const name = document.getElementById('contact-name').value;
    const phone = document.getElementById('contact-phone').value;
    
    if (!name || !phone) {
        alert('Lütfen tüm alanları doldurun');
        return;
    }
    
    try {
        const response = await fetch('/api/contacts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, phone })
        });
        
        if (response.ok) {
            closeModal('add-modal');
            document.getElementById('contact-name').value = '';
            document.getElementById('contact-phone').value = '';
            loadContacts();
        }
    } catch (error) {
        console.error('Error adding contact:', error);
    }
}

async function deleteContact(id) {
    if (!confirm('Bu numarayı silmek istediğinizden emin misiniz?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/contacts/${id}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadContacts();
        }
    } catch (error) {
        console.error('Error deleting contact:', error);
    }
}

async function editContact(id) {
    const contact = contacts.find(c => c.id === id);
    if (!contact) {
        alert('Kişi bulunamadı');
        return;
    }
    
    document.getElementById('edit-contact-id').value = contact.id;
    document.getElementById('edit-contact-name').value = contact.name;
    document.getElementById('edit-contact-phone').value = contact.phone;
    
    openModal('edit-modal');
}

async function saveEditContact() {
    const id = parseInt(document.getElementById('edit-contact-id').value);
    const name = document.getElementById('edit-contact-name').value;
    const phone = document.getElementById('edit-contact-phone').value;
    
    if (!name || !phone) {
        alert('Lütfen tüm alanları doldurun');
        return;
    }
    
    try {
        const response = await fetch(`/api/contacts/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, phone })
        });
        
        if (response.ok) {
            closeModal('edit-modal');
            loadContacts();
        } else {
            alert('Güncelleme başarısız');
        }
    } catch (error) {
        console.error('Error updating contact:', error);
        alert('Güncelleme sırasında hata oluştu');
    }
}

async function connectWhatsApp() {
    try {
        console.log('Connecting to WhatsApp...');
        const response = await fetch('/api/whatsapp/connect', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        console.log('Response status:', response.status);
        console.log('Response ok:', response.ok);
        
        if (!response.ok) {
            console.log('Response not ok, text:', await response.text());
            alert('Sunucu hatası. Lütfen tekrar deneyin.');
            return;
        }
        
        const result = await response.json();
        console.log('Connect response:', result);
        
        if (!result || typeof result !== 'object') {
            console.error('Invalid response:', result);
            alert('Geçersiz sunucu yanıtı. Lütfen tekrar deneyin.');
            return;
        }
        
        if (result.success) {
            if (result.already_logged_in) {
                // Already logged in, skip QR code
                whatsappConnected = true;
                updateConnectionStatus();
                alert('WhatsApp zaten bağlı! Oturum otomatik olarak yüklendi.');
            } else {
                // Show QR code
                openModal('qr-modal');
                checkQRCode();
            }
        } else {
            const message = result.message || 'Bilinmeyen hata';
            console.error('Connection failed:', message);
            alert('Bağlantı hatası: ' + message);
        }
    } catch (error) {
        console.error('Error connecting WhatsApp:', error);
        alert('Bağlantı sırasında bir hata oluştu: ' + error.message);
    }
}

async function checkQRCode() {
    let qrShown = false;
    let checkCount = 0;
    
    const interval = setInterval(async () => {
        try {
            checkCount++;
            console.log(`Checking WhatsApp connection... attempt ${checkCount}`);
            
            const response = await fetch('/api/whatsapp/qr');
            const data = await response.json();
            
            console.log('QR response:', data);
            
            if (data.qr && !qrShown) {
                qrShown = true;
                console.log('QR code received, displaying...');
                const qrContainer = document.getElementById('qr-container');
                qrContainer.innerHTML = `
                    <img src="data:image/png;base64,${data.qr}" class="qr-code" alt="QR Code">
                    <p style="margin-top: 20px; color: #25D366; font-weight: 500;">QR kod gösterildi. Lütfen WhatsApp uygulamanızdan taratın.</p>
                    <button class="submit-btn" id="confirm-qr-btn" style="margin-top: 20px;">QR Kodunu Tardım ✓</button>
                `;
                
                document.getElementById('confirm-qr-btn').addEventListener('click', async () => {
                    console.log('Manual QR confirmation clicked');
                    clearInterval(interval);
                    closeModal('qr-modal');
                    whatsappConnected = true;
                    updateConnectionStatus();
                    alert('WhatsApp başarıyla bağlandı!');
                });
            }
            
            const isConnected = await checkWhatsAppConnection();
            console.log('Connected:', isConnected);
            
            if (isConnected) {
                console.log('Auto-detection: WhatsApp connected');
                clearInterval(interval);
                closeModal('qr-modal');
                whatsappConnected = true;
                updateConnectionStatus();
                alert('WhatsApp başarıyla bağlandı!');
            }
        } catch (error) {
            console.error('Error checking QR:', error);
        }
    }, 3000);
    
    setTimeout(() => {
        clearInterval(interval);
        if (!whatsappConnected) {
            alert('QR kod süresi doldu. Lütfen tekrar deneyin.');
            closeModal('qr-modal');
        }
    }, 120000);
}

async function checkWhatsAppConnection() {
    try {
        const response = await fetch('/api/whatsapp/status');
        const data = await response.json();
        console.log('WhatsApp status response:', data);
        return data.connected;
    } catch (error) {
        console.error('Error checking WhatsApp connection:', error);
        return false;
    }
}

async function disconnectWhatsApp() {
    try {
        await fetch('/api/whatsapp/disconnect', {
            method: 'POST'
        });
        whatsappConnected = false;
        updateConnectionStatus();
    } catch (error) {
        console.error('Error disconnecting WhatsApp:', error);
    }
}

function updateConnectionStatus() {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    const connectBtn = document.querySelector('.connect-btn');
    const disconnectBtn = document.querySelector('.disconnect-btn');
    
    if (whatsappConnected) {
        statusDot.classList.add('connected');
        statusText.textContent = 'Bağlandı';
        connectBtn.style.display = 'none';
        disconnectBtn.style.display = 'inline-block';
    } else {
        statusDot.classList.remove('connected');
        statusText.textContent = 'Bağlantı yok';
        connectBtn.style.display = 'inline-block';
        disconnectBtn.style.display = 'none';
    }
}

async function startTracking() {
    if (contacts.length === 0) {
        alert('Lütfen önce numara ekleyin');
        return;
    }
    
    if ('Notification' in window && Notification.permission === 'default') {
        await Notification.requestPermission();
    }
    
    try {
        const response = await fetch('/api/start-tracking', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ contact_ids: contacts.map(c => c.id) })
        });
        
        if (response.ok) {
            tracking = true;
            document.getElementById('track-btn').textContent = 'Durdur';
            startAutoRefresh();
            alert('Takip başladı! Bildirimler aktif edildi.');
        }
    } catch (error) {
        console.error('Error starting tracking:', error);
    }
}

async function stopTracking() {
    try {
        const response = await fetch('/api/stop-tracking', {
            method: 'POST'
        });
        
        if (response.ok) {
            tracking = false;
            document.getElementById('track-btn').textContent = 'Takip Et';
            stopAutoRefresh();
        }
    } catch (error) {
        console.error('Error stopping tracking:', error);
    }
}

function toggleTracking() {
    if (tracking) {
        stopTracking();
    } else {
        startTracking();
    }
}

function startAutoRefresh() {
    refreshInterval = setInterval(loadContacts, 3000);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

async function showStatistics(contactId) {
    try {
        console.log(`Fetching statistics for contact ID: ${contactId}`);
        const response = await fetch(`/api/statistics/${contactId}`);
        
        if (!response.ok) {
            console.error('Response not ok:', response.status, response.statusText);
            const text = await response.text();
            console.error('Response text:', text);
            alert(`İstatistikler yüklenemedi. Hata kodu: ${response.status}`);
            return;
        }
        
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            console.error('Invalid content type:', contentType);
            const text = await response.text();
            console.error('Response text:', text);
            alert('İstatistikler yüklenemedi. Geçersiz yanıt formatı.');
            return;
        }
        
        const data = await response.json();
        console.log('Statistics data:', data);
        
        const modalContent = document.getElementById('stats-modal-content');
        modalContent.innerHTML = `
            <div class="modal-header">
                <h2>${data.contact.name} - İstatistikler</h2>
                <button class="close-btn" onclick="closeModal('stats-modal')">&times;</button>
            </div>
            
            <div class="stats-section">
                <div class="stat-row">
                    <span>Telefon:</span>
                    <span class="stat-value">${data.contact.phone}</span>
                </div>
                <div class="stat-row">
                    <span>Toplam Online Süre:</span>
                    <span class="stat-value">${formatDuration(data.contact.total_online_seconds)}</span>
                </div>
                <div class="stat-row">
                    <span>Toplam Giriş:</span>
                    <span class="stat-value">${data.history.length}</span>
                </div>
            </div>
            
            <h3>Online Geçmişi</h3>
            <div class="history-list">
                ${data.history.length === 0 ? '<p class="empty-state">Henüz kayıt yok</p>' : 
                data.history.map(h => `
                    <div class="history-item">
                        <div class="history-time">
                            ${h.online_at ? formatDate(h.online_at) : 'N/A'} - ${h.offline_at ? formatDate(h.offline_at) : 'Çevrimiçi'}
                        </div>
                        <div class="history-duration">
                            Süre: ${formatDuration(h.duration_seconds)}
                        </div>
                    </div>
                `).join('')}
            </div>
            
            <div class="export-buttons">
                <button class="export-btn export-json" onclick="exportData(${contactId}, 'json')">JSON İndir</button>
                <button class="export-btn export-csv" onclick="exportData(${contactId}, 'csv')">CSV İndir</button>
            </div>
        `;
        
        openModal('stats-modal');
    } catch (error) {
        console.error('Error loading statistics:', error);
        alert('İstatistikler yüklenirken bir hata oluştu: ' + error.message);
    }
}

function exportData(contactId, format) {
    window.open(`/api/export/${contactId}?format=${format}`, '_blank');
}

document.getElementById('add-contact-btn').addEventListener('click', () => openModal('add-modal'));
document.querySelector('.close-modal').addEventListener('click', () => closeModal('add-modal'));
document.querySelector('.submit-btn').addEventListener('click', addContact);
document.getElementById('save-edit-btn').addEventListener('click', saveEditContact);
document.querySelector('.connect-btn').addEventListener('click', connectWhatsApp);
document.querySelector('.disconnect-btn').addEventListener('click', disconnectWhatsApp);
document.getElementById('track-btn').addEventListener('click', toggleTracking);
document.getElementById('manual-connect-btn').addEventListener('click', async () => {
    console.log('Manual connect button clicked');
    try {
        await fetch('/api/whatsapp/manual-connect', {
            method: 'POST'
        });
        closeModal('qr-modal');
        whatsappConnected = true;
        updateConnectionStatus();
        alert('WhatsApp başarıyla bağlandı! Şimdi numara ekleyip takip başlatabilirsiniz.');
    } catch (error) {
        console.error('Error connecting manually:', error);
        alert('Bağlantı sırasında hata oluştu.');
    }
});

document.addEventListener('DOMContentLoaded', async () => {
    loadContacts();
    
    // Check WhatsApp connection on page load
    const isConnected = await checkWhatsAppConnection();
    whatsappConnected = isConnected;
    updateConnectionStatus();
    
    if (isConnected) {
        console.log('WhatsApp already connected from previous session');
    }
    
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
});