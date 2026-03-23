import threading
import queue
from playwright.sync_api import sync_playwright
from datetime import datetime
import time
import base64

class WhatsAppService:
    def __init__(self):
        self.browser = None
        self.page = None
        self.context = None
        self.connected = False
        self.tracking = False
        self.contact_ids = []
        self.qr_code = None
        self.playwright = None
        
        self.op_queue = queue.Queue()
        self.result_queue = queue.Queue()
        
        self.playwright_thread = None
        self.running = True
        self._start_playwright_thread()
        
    def _start_playwright_thread(self):
        def run_playwright():
            self._playwright_loop()
        
        self.playwright_thread = threading.Thread(target=run_playwright, daemon=True)
        self.playwright_thread.start()
    
    def _playwright_loop(self):
        self.playwright = sync_playwright().start()
        
        while self.running:
            try:
                op = self.op_queue.get(timeout=1.0)
                op_id = op.get('op_id')
                result = None
                
                if op['op'] == 'connect':
                    result = self._connect_async()
                elif op['op'] == 'get_qr':
                    result = self._get_qr_async()
                elif op['op'] == 'is_connected':
                    print(f"[playwright_loop] Handling is_connected, self.connected = {self.connected}")
                    result = self._is_connected_async()
                elif op['op'] == 'check_online_status':
                    result = self._check_online_status_async(op['phone'])
                elif op['op'] == 'disconnect':
                    result = self._disconnect_async()
                elif op['op'] == 'stop':
                    break
                
                self.result_queue.put({'op_id': op_id, 'result': result})
                self.op_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in playwright loop: {e}")
                self.result_queue.put({'op_id': op_id, 'error': str(e)})
        
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def _execute_operation(self, op_name, timeout=10, **kwargs):
        try:
            import uuid
            op_id = str(uuid.uuid4())
            self.op_queue.put({'op': op_name, 'op_id': op_id, **kwargs})
            
            result = None
            while True:
                result = self.result_queue.get(timeout=timeout)
                if isinstance(result, dict) and result.get('op_id') == op_id:
                    break
                else:
                    self.result_queue.put(result)
            
            if isinstance(result, dict) and 'error' in result:
                raise Exception(result['error'])
            
            return result.get('result') if isinstance(result, dict) else result
        except queue.Empty:
            raise TimeoutError(f"Operation {op_name} timed out")
    
    def _connect_async(self):
        try:
            import os
            user_data_dir = os.path.join(os.path.dirname(__file__), 'whatsapp_session')
            
            if self.browser:
                try:
                    self.browser.close()
                except:
                    pass
                self.browser = None
            
            if self.playwright:
                try:
                    self.playwright.stop()
                except:
                    pass
                self.playwright = None
            
            self.playwright = sync_playwright().start()
            
            self.browser = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                args=['--disable-blink-features=AutomationControlled'],
                timeout=60000
            )
            
            if len(self.browser.pages) > 0:
                self.page = self.browser.pages[0]
            else:
                self.page = self.browser.new_page()
            
            self.page.goto('https://web.whatsapp.com')
            self.page.wait_for_load_state('networkidle', timeout=30000)
            time.sleep(5)
            
            try:
                qr_canvas = self.page.locator('canvas').count()
                qr_image = self.page.locator('img[src*="qr"], img[alt*="QR"]').count()
                
                if qr_canvas > 0 or qr_image > 0:
                    print("QR code is visible - NOT logged in yet")
                    self.connected = False
                    return {'success': True, 'message': 'Browser started, waiting for QR scan', 'already_logged_in': False}
            except:
                pass
            
            try:
                search_box = self.page.locator('[data-testid="search"]').count()
                menu = self.page.locator('[data-testid="menu"]').count()
                grid = self.page.locator('div[role="grid"]').count()
                
                if search_box > 0 or menu > 0 or grid > 0:
                    print("Main interface elements found - ALREADY LOGGED IN")
                    self.connected = True
                    print(f"Setting self.connected = True")
                    return {'success': True, 'message': 'WhatsApp already connected', 'already_logged_in': True}
            except:
                pass
            
            print("Status unclear - assume NOT logged in")
            self.connected = False
            return {'success': True, 'message': 'Browser started, waiting for QR scan', 'already_logged_in': False}
        except Exception as e:
            print(f"Connect error: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': str(e)}
    
    def connect(self):
        return self._execute_operation('connect', timeout=60)
    
    def _get_qr_async(self):
        if not self.page:
            return None
        
        try:
            time.sleep(5)
            
            print("Looking for QR code...")
            
            canvas_elements = self.page.locator('canvas')
            canvas_count = canvas_elements.count()
            print(f"Found {canvas_count} canvas elements")
            
            if canvas_count > 0:
                for i in range(min(canvas_count, 5)):
                    try:
                        canvas = canvas_elements.nth(i)
                        screenshot = canvas.screenshot(timeout=5000)
                        
                        if screenshot and len(screenshot) > 5000:
                            print(f"QR code found from canvas {i}, size: {len(screenshot)}")
                            self.qr_code = screenshot
                            return base64.b64encode(self.qr_code).decode('utf-8')
                    except Exception as e:
                        print(f"Error capturing canvas {i}: {e}")
                        continue
            
            qr_images = self.page.locator('img[src*="qr"], img[alt*="QR"], img[src*="QR"]')
            img_count = qr_images.count()
            print(f"Found {img_count} QR image elements")
            
            if img_count > 0:
                try:
                    screenshot = qr_images.first.screenshot(timeout=5000)
                    if screenshot and len(screenshot) > 1000:
                        print(f"QR code found from image, size: {len(screenshot)}")
                        return base64.b64encode(screenshot).decode('utf-8')
                except Exception as e:
                    print(f"Error capturing QR image: {e}")
            
            qr_divs = self.page.locator('div[style*="qr"], div[class*="qr"]')
            if qr_divs.count() > 0:
                try:
                    screenshot = qr_divs.first.screenshot(timeout=5000)
                    if screenshot and len(screenshot) > 1000:
                        print(f"QR code found from div, size: {len(screenshot)}")
                        return base64.b64encode(screenshot).decode('utf-8')
                except Exception as e:
                    print(f"Error capturing QR div: {e}")
                    
        except Exception as e:
            print(f"Error getting QR: {e}")
        
        print("QR code not found")
        return None
    
    def get_qr(self):
        return self._execute_operation('get_qr', timeout=5)
    
    def _is_connected_async(self):
        print(f"[_is_connected_async] self.connected = {self.connected}, self.page = {self.page is not None}")
        
        if self.connected:
            print("[_is_connected_async] Returning True because self.connected is True")
            return True
        
        if not self.page:
            print("[_is_connected_async] No page, returning False")
            return False
        
        try:
            title = self.page.title()
            print(f"Page title: {title}")
            
            if 'WhatsApp' in title:
                url = self.page.url
                print(f"Page URL: {url}")
                
                if 'web.whatsapp.com' in url:
                    selectors = [
                        '[data-testid="menu"]',
                        '[data-testid="search"]',
                        '[data-testid="chat"]',
                        'div[role="grid"]',
                        'div[role="list"]',
                        'canvas[aria-label*="WhatsApp"]',
                        'canvas[alt*="WhatsApp"]',
                        'div[aria-label="WhatsApp"]',
                        'div[role="main"]'
                    ]
                    
                    for selector in selectors:
                        try:
                            element = self.page.wait_for_selector(selector, timeout=500)
                            if element:
                                count = element.count()
                                if count > 0:
                                    print(f"Found connected element: {selector}")
                                    self.connected = True
                                    return True
                        except:
                            continue
            
            print("WhatsApp not connected yet")
            return False
        except Exception as e:
            print(f"Connection check failed: {e}")
            return False
    
    def is_connected(self):
        return self._execute_operation('is_connected', timeout=3)
    
    def _check_online_status_async(self, phone_number):
        if not self.page or not self.connected:
            print(f"Cannot check status - page: {self.page is not None}, connected: {self.connected}")
            return None
        
        try:
            print(f"Checking online status for: {phone_number}")
            
            clean_phone = phone_number.replace('+', '').replace(' ', '')
            chat_url = f'https://web.whatsapp.com/send?phone={clean_phone}'
            
            current_url = self.page.url
            if clean_phone in current_url:
                print(f"Already on chat page, skipping navigation")
            else:
                print(f"Navigating to chat URL: {chat_url}")
                self.page.goto(chat_url, timeout=60000)
                self.page.wait_for_load_state('networkidle', timeout=30000)
                time.sleep(5)
            
            header_selectors = [
                '[data-testid="conversation-panel-header"]',
                '#main > header',
                '[role="region"] header',
                'div[role="main"] header',
                'header[role="banner"]'
            ]
            
            header_found = False
            for selector in header_selectors:
                try:
                    if self.page.wait_for_selector(selector, timeout=10000):
                        print(f"Header found with selector: {selector}")
                        header_found = True
                        break
                except:
                    continue
            
            if not header_found:
                print("Header not found with any selector")
                return None
            
            time.sleep(3)
            
            result = self.page.evaluate("""() => {
                try {
                    const selectors = [
                        '[data-testid="conversation-panel-header"]',
                        '#main > header',
                        '[role="region"] header',
                        'div[role="main"] header',
                        'header[role="banner"]'
                    ];
                    
                    let header = null;
                    for (const selector of selectors) {
                        header = document.querySelector(selector);
                        if (header) {
                            console.log('Header found with selector:', selector);
                            break;
                        }
                    }
                    
                    if (!header) {
                        return { success: false, message: 'Header not found' };
                    }
                    
                    const allText = header.innerText || header.textContent || '';
                    const lowerText = allText.toLowerCase().trim();
                    
                    console.log('DOM Full text:', allText);
                    console.log('DOM Lower text:', lowerText);
                    console.log('DOM Text length:', allText.length);
                    
                    const exactOnlineMatch = lowerText === 'çevrimiçi' || 
                                           lowerText === 'online' ||
                                           lowerText === 'şu an çevrimiçi';
                    
                    const onlineIndicators = ['çevrimiçi', 'online', 'şu an çevrimiçi'];
                    const offlineIndicators = [
                        'son görülme', 'last seen', 'yaklaşık', 
                        'bugün', 'today', 'dün', 'yesterday',
                        'saat önce', 'hours ago', 'dakika önce', 'minutes ago'
                    ];
                    
                    const hasOnline = onlineIndicators.some(ind => lowerText.includes(ind));
                    const hasOffline = offlineIndicators.some(ind => lowerText.includes(ind));
                    
                    const timePatterns = [
                        /^\\d{1,2}\\.\\d{2}$/,
                        /^\\d{1,2}:\\d{2}$/,
                        /^\\d{1,2} \\d{1,2}$/,
                        /^\\d{1,2}\\.\\d{2} - \\d{1,2}\\.\\d{2}$/
                    ];
                    
                    const isTime = timePatterns.some(pattern => pattern.test(lowerText));
                    
                    const hasPrivacyText = lowerText.includes('son görülme') || lowerText.includes('last seen') || 
                                          lowerText.includes('yaklaşık') || lowerText.includes('gizlilik') ||
                                          lowerText.includes('privacy') || lowerText.includes('göreceksiniz');
                    
                    const hasNumbers = /\\d/.test(lowerText);
                    
                    let isOnline = false;
                    
                    if (exactOnlineMatch) {
                        isOnline = true;
                    } else if (hasOnline && !hasOffline && !hasPrivacyText && !hasNumbers && lowerText.length < 50) {
                        isOnline = true;
                    }
                    
                    if (hasOffline) {
                        isOnline = false;
                    }
                    
                    console.log('DOM Analysis:', {
                        text: lowerText,
                        exactOnlineMatch,
                        hasOnline,
                        hasOffline,
                        isTime,
                        hasPrivacyText,
                        hasNumbers,
                        textLength: lowerText.length,
                        isOnline
                    });
                    
                    return { 
                        success: true, 
                        is_online: isOnline,
                        element_text: allText
                    };
                } catch (e) {
                    console.error('Error:', e);
                    return { success: false, message: e.message };
                }
            }""")
            
            is_online_from_dom = None
            element_text = ''
            
            if result and result.get('success'):
                is_online_from_dom = result.get('is_online', False)
                element_text = result.get('element_text', '')
                print(f"DOM check for {phone_number}: {is_online_from_dom}, Text: {element_text}")
            
            is_online_from_image = None
            try:
                header_selectors = [
                    '[data-testid="conversation-panel-header"]',
                    '#main > header',
                    '[role="region"] header',
                    'div[role="main"] header',
                    'header[role="banner"]'
                ]
                
                header = None
                screenshot_bytes = None
                
                for selector in header_selectors:
                    try:
                        locator = self.page.locator(selector).first
                        if locator.count() > 0:
                            header = locator
                            print(f"Header screenshot using selector: {selector}")
                            break
                    except:
                        continue
                
                if not header:
                    print("No header found for screenshot")
                else:
                    screenshot_bytes = header.screenshot(timeout=30000)
                
                if not screenshot_bytes:
                    print("No screenshot captured")
                else:
                    screenshot_bytes = header.screenshot(timeout=30000)
                
                if not screenshot_bytes:
                    print("No screenshot captured")
                else:
                    import os
                    import io
                    import platform
                    
                    try:
                        import pytesseract
                        from pytesseract import image_to_string
                        from PIL import Image, ImageEnhance, ImageFilter
                        
                        if platform.system() == 'Windows':
                            tesseract_path = os.path.join(os.path.dirname(__file__), 'tesseract', 'tesseract.exe')
                            if os.path.exists(tesseract_path):
                                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                                print(f"Using tesseract from: {tesseract_path}")
                            else:
                                print("Tesseract not found in local directory")
                                raise Exception("Tesseract not installed")
                        
                        image = Image.open(io.BytesIO(screenshot_bytes))
                        image_gray = image.convert('L')
                        image_contrast = ImageEnhance.Contrast(image_gray).enhance(2.0)
                        image_sharp = image_contrast.filter(ImageFilter.SHARPEN)
                        
                        text = image_to_string(image_sharp, lang='tur+eng', config='--psm 6 --oem 1')
                        lower_text = text.lower().strip()
                        
                        print(f"OCR Text from image: {repr(lower_text)}")
                        
                        online_keywords = ['çevrimiçi', 'online']
                        offline_keywords = ['son görülme', 'last seen', 'son gorulme']
                        
                        has_online = any(kw in lower_text for kw in online_keywords)
                        has_offline = any(kw in lower_text for kw in offline_keywords)
                        
                        if has_offline:
                            is_online_from_image = False
                            print(f"Image OCR: OFFLINE (found offline keyword)")
                        elif has_online:
                            is_online_from_image = True
                            print(f"Image OCR: ONLINE (found online keyword)")
                        else:
                            print(f"Image OCR: UNCLEAR (no keyword found)")
                            is_online_from_image = None
                    except Exception as e:
                        print(f"OCR error: {e}")
                        print("Using DOM text as fallback for screenshot analysis")
                        
                        fallback_text = result.get('element_text', '') if result else ''
                        lower_text = fallback_text.lower().strip()
                        print(f"Fallback text: {repr(lower_text)}")
                        
                        online_keywords = ['çevrimiçi', 'online']
                        offline_keywords = ['son görülme', 'last seen', 'son gorulme']
                        
                        has_online = any(kw in lower_text for kw in online_keywords)
                        has_offline = any(kw in lower_text for kw in offline_keywords)
                        
                        if has_offline:
                            is_online_from_image = False
                            print(f"Image (fallback): OFFLINE (found offline keyword)")
                        elif has_online:
                            is_online_from_image = True
                            print(f"Image (fallback): ONLINE (found online keyword)")
                        else:
                            print(f"Image (fallback): UNCLEAR (no keyword found)")
                            is_online_from_image = None
                
            except Exception as e:
                print(f"Image analysis failed for {phone_number}: {e}")
            
            if not self.use_dom and not self.use_image:
                print("No tracking method selected, returning None")
                return None
            
            final_is_online = None
            
            if self.use_dom:
                print(f"DOM result: {is_online_from_dom}")
                if is_online_from_dom is not None:
                    final_is_online = is_online_from_dom
                    print(f"Using DOM: {final_is_online}")
            
            if self.use_image:
                print(f"Image result: {is_online_from_image}")
                if is_online_from_image is not None:
                    if final_is_online is None:
                        final_is_online = is_online_from_image
                        print(f"Using Image (DOM was None): {final_is_online}")
                    else:
                        final_is_online = is_online_from_image
                        print(f"Using Image (overriding DOM): {final_is_online}")
            
            print(f"Final status for {phone_number}: {final_is_online} (Use DOM: {self.use_dom}, Use Image: {self.use_image})")
            
            import os
            screenshot_path = None
            try:
                screenshot_path = os.path.join(os.path.dirname(__file__), f'debug_{phone_number}_{int(time.time())}.png')
                self.page.screenshot(path=screenshot_path, timeout=5000)
                print(f"Debug screenshot saved: {screenshot_path}")
                
                print(f"Checking deletion: final_is_online={final_is_online}")
                if final_is_online is not True:
                    try:
                        if os.path.exists(screenshot_path):
                            os.remove(screenshot_path)
                            print(f"✓ Not online, screenshot deleted: {screenshot_path}")
                            screenshot_path = None
                        else:
                            print(f"✗ Screenshot file not found: {screenshot_path}")
                    except Exception as e:
                        print(f"✗ Could not delete screenshot: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"→ Keeping screenshot (final_is_online={final_is_online})")
            except Exception as e:
                print(f"Could not take debug screenshot: {e}")
                import traceback
                traceback.print_exc()
            
            return final_is_online
            
            return None
        except Exception as e:
            print(f"Error checking status for {phone_number}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def check_online_status(self, phone_number):
        return self._execute_operation('check_online_status', timeout=120, phone=phone_number)
    
    def start_tracking(self, contact_ids, use_dom=True, use_image=True):
        self.contact_ids = contact_ids
        self.use_dom = use_dom
        self.use_image = use_image
        self.tracking = True
        print(f"[start_tracking] Starting with contact_ids: {contact_ids}, connected: {self.connected}")
        self.tracking_thread = threading.Thread(target=self._tracking_loop)
        self.tracking_thread.daemon = True
        self.tracking_thread.start()
    
    def stop_tracking(self):
        self.tracking = False
        if self.tracking_thread:
            self.tracking_thread.join(timeout=5)
    
    def _tracking_loop(self):
        from app import app
        with app.app_context():
            from models import db, Contact, OnlineStatus
            
            print(f"Tracking started for contact IDs: {self.contact_ids}")
            
            last_states = {}
            
            for contact in Contact.query.filter(Contact.id.in_(self.contact_ids)):
                last_states[contact.id] = contact.is_online
            
            while self.tracking:
                print("Tracking loop iteration...")
                for contact in Contact.query.filter(Contact.id.in_(self.contact_ids)):
                    print(f"Checking contact: {contact.name} ({contact.phone})")
                    is_online = self.check_online_status(contact.phone)
                    
                    actual_is_online = is_online if is_online is not None else False
                    
                    if actual_is_online != last_states.get(contact.id):
                        contact.is_online = actual_is_online
                        now = datetime.now()
                        
                        if actual_is_online:
                            contact.last_online_at = now
                            print(f"{contact.name} is now ONLINE at {now}")
                            
                            status = OnlineStatus(
                                contact_id=contact.id,
                                online_at=now,
                                offline_at=None,
                                duration_seconds=0
                            )
                            db.session.add(status)
                        else:
                            if contact.last_online_at:
                                duration = (now - contact.last_online_at).total_seconds()
                                contact.total_online_seconds += duration
                                contact.last_offline_at = now
                                
                                status = OnlineStatus(
                                    contact_id=contact.id,
                                    online_at=contact.last_online_at,
                                    offline_at=now,
                                    duration_seconds=duration
                                )
                                db.session.add(status)
                                print(f"{contact.name} is now OFFLINE at {now}, duration: {duration}s")
                        
                        last_states[contact.id] = actual_is_online
                        db.session.commit()
                        print(f"Saved to DB - is_online: {contact.is_online}, last_online_at: {contact.last_online_at}, last_offline_at: {contact.last_offline_at}")
                
                time.sleep(10)
            
            print("Tracking stopped")
    
    def _disconnect_async(self):
        self.stop_tracking()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        self.browser = None
        self.page = None
        self.context = None
        self.connected = False
        self.qr_code = None
    
    def disconnect(self):
        return self._execute_operation('disconnect', timeout=5)
    
    def __del__(self):
        self.running = False
        try:
            self.op_queue.put({'op': 'stop'})
        except:
            pass
