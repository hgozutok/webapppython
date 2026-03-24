import os
import sys
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
        self.use_dom = True
        self.use_image = True
        
        # Telegram notification callback
        self.on_online_callback = None
        # Database update callback (will be called from main thread)
        self.on_status_change_callback = None
        
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
                elif op['op'] == 'take_screenshot':
                    result = self._take_screenshot_async(op['path'])
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
            import time
            
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
            
            import logging
            logging.basicConfig(level=logging.DEBUG)
            
            print("Launching browser...")
            sys.stdout.flush()
            self.browser = self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu'
                ],
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                timeout=120000
            )
            print("Browser launched successfully")
            
            if len(self.browser.pages) > 0:
                self.page = self.browser.pages[0]
            else:
                self.page = self.browser.new_page()
            print(f"Page created: {self.page is not None}")
            
            print("Navigating to WhatsApp Web...")
            self.page.goto('https://web.whatsapp.com', timeout=120000, wait_until='networkidle')
            print("Page loaded, waiting for initialization...")
            
            for i in range(20):
                print(f"Checking connection status, attempt {i + 1}/20")
                
                try:
                    title = self.page.title()
                    print(f"Page title: {title}")
                    url = self.page.url
                    print(f"Page URL: {url}")
                except Exception as e:
                    print(f"Error getting page info: {e}")
                
                try:
                    search_box = self.page.locator('[data-testid="search"]').count()
                    menu = self.page.locator('[data-testid="menu"]').count()
                    grid = self.page.locator('div[role="grid"]').count()
                    
                    if search_box > 0 or menu > 0 or grid > 0:
                        print("Main interface elements found - ALREADY LOGGED IN")
                        self.connected = True
                        print(f"Setting self.connected = True")
                        return {'success': True, 'message': 'WhatsApp already connected', 'already_logged_in': True}
                except Exception as e:
                    print(f"Error checking main interface: {e}")
                
                try:
                    qr_canvas = self.page.locator('canvas').count()
                    qr_image = self.page.locator('img[src*="qr"], img[alt*="QR"]').count()
                    
                    print(f"Canvas count: {qr_canvas}, QR image count: {qr_image}")
                    
                    if qr_canvas > 0 or qr_image > 0:
                        print("QR code is visible - NOT logged in yet")
                        self.connected = False
                        return {'success': True, 'message': 'Browser started, waiting for QR scan', 'already_logged_in': False}
                except Exception as e:
                    print(f"Error checking QR elements: {e}")
                
                try:
                    debug_screenshot = os.path.join(os.path.dirname(__file__), f'deconnect_attempt_{i+1}.png')
                    self.page.screenshot(path=debug_screenshot, timeout=10000)
                    print(f"Debug screenshot saved: {debug_screenshot}")
                except Exception as e:
                    print(f"Could not take debug screenshot: {e}")
                
                time.sleep(5)
            
            print("Status unclear after all attempts - assume NOT logged in")
            self.connected = False
            return {'success': True, 'message': 'Browser started, waiting for QR scan', 'already_logged_in': False}
        except Exception as e:
            print(f"Connect error: {e}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': str(e)}
    
    def connect(self):
        try:
            return self._execute_operation('connect', timeout=120)
        except TimeoutError:
            print("Connect operation timed out")
            return {'success': False, 'message': 'Connection timeout'}
        except Exception as e:
            print(f"Connect operation failed: {e}")
            return {'success': False, 'message': str(e)}
    
    def _get_qr_async(self):
        if not self.page:
            return None
        
        try:
            print("Looking for QR code...")
            
            max_retries = 15
            for attempt in range(max_retries):
                print(f"QR attempt {attempt + 1}/{max_retries}")
                
                try:
                    self.page.wait_for_load_state('networkidle', timeout=3000)
                except:
                    pass
                
                time.sleep(5)
                
                try:
                    canvas_elements = self.page.locator('canvas')
                    canvas_count = canvas_elements.count()
                    print(f"Found {canvas_count} canvas elements")
                    
                    if canvas_count > 0:
                        for i in range(min(canvas_count, 10)):
                            try:
                                canvas = canvas_elements.nth(i)
                                screenshot = canvas.screenshot(timeout=3000)
                                
                                if screenshot and len(screenshot) > 5000:
                                    print(f"QR code found from canvas {i}, size: {len(screenshot)}")
                                    self.qr_code = screenshot
                                    return base64.b64encode(self.qr_code).decode('utf-8')
                            except Exception as e:
                                print(f"Error capturing canvas {i}: {e}")
                                continue
                except Exception as e:
                    print(f"Error searching for canvas: {e}")
                
                try:
                    qr_images = self.page.locator('img[src*="qr"], img[alt*="QR"], img[src*="QR"]')
                    img_count = qr_images.count()
                    print(f"Found {img_count} QR image elements")
                    
                    if img_count > 0:
                        for i in range(min(img_count, 5)):
                            try:
                                screenshot = qr_images.nth(i).screenshot(timeout=3000)
                                if screenshot and len(screenshot) > 1000:
                                    print(f"QR code found from image {i}, size: {len(screenshot)}")
                                    return base64.b64encode(screenshot).decode('utf-8')
                            except Exception as e:
                                print(f"Error capturing QR image {i}: {e}")
                                continue
                except Exception as e:
                    print(f"Error searching for QR images: {e}")
                
                try:
                    qr_divs = self.page.locator('div[style*="qr"], div[class*="qr"]')
                    if qr_divs.count() > 0:
                        for i in range(min(qr_divs.count(), 5)):
                            try:
                                screenshot = qr_divs.nth(i).screenshot(timeout=3000)
                                if screenshot and len(screenshot) > 1000:
                                    print(f"QR code found from div {i}, size: {len(screenshot)}")
                                    return base64.b64encode(screenshot).decode('utf-8')
                            except Exception as e:
                                print(f"Error capturing QR div {i}: {e}")
                                continue
                except Exception as e:
                    print(f"Error searching for QR divs: {e}")
            
            print("QR code not found after all retries")
            
            try:
                debug_screenshot = self.page.screenshot(timeout=10000)
                if debug_screenshot:
                    print(f"Full page screenshot taken, size: {len(debug_screenshot)}")
            except Exception as e:
                print(f"Could not take debug screenshot: {e}")
            
            return None
                    
        except Exception as e:
            print(f"Error getting QR: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_qr(self):
        try:
            result = self._execute_operation('get_qr', timeout=120)
            if result:
                print(f"QR code result: {result}")
            return result
        except TimeoutError:
            print("QR code operation timed out, returning None")
            return None
        except Exception as e:
            print(f"QR code operation failed: {e}")
            return None
    
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
        # This tracking loop does NOT use Flask's app context
        # Instead, it collects data and reports back via callback for DB operations
        
        print(f"Tracking started for contact IDs: {self.contact_ids}")
        
        # Store contact info (id, name, phone) locally without DB access
        # We'll need to get this from the main app before starting
        # For now, use a queue to receive contact info from main thread
        contact_info_queue = queue.Queue()
        
        # Request contact info from main thread
        if self.on_status_change_callback:
            # Send a request for contact info
            self.on_status_change_callback({
                'type': 'get_contacts',
                'contact_ids': self.contact_ids,
                'response_queue': contact_info_queue
            })
            
            # Wait for contact info from main thread
            try:
                contacts_data = contact_info_queue.get(timeout=10)
            except queue.Empty:
                print("Failed to get contact info from main thread")
                return
        else:
            print("No status change callback configured!")
            return
        
        # Initialize last_states with None so first online detection triggers callback
        last_states = {}
        for contact_data in contacts_data:
            last_states[contact_data['id']] = None  # Force callback on first check
        
        while self.tracking:
            print("Tracking loop iteration...")
            for contact_data in contacts_data:
                contact_id = contact_data['id']
                contact_name = contact_data['name']
                contact_phone = contact_data['phone']
                
                print(f"Checking contact: {contact_name} ({contact_phone})")
                is_online = self.check_online_status(contact_phone)
                
                actual_is_online = is_online if is_online is not None else False
                
                if actual_is_online != last_states.get(contact_id):
                    now = datetime.now()
                    
                    if actual_is_online:
                        print(f"{contact_name} is now ONLINE at {now}")
                        
                        # Handle screenshot and telegram notification in this thread
                        print(f"[DEBUG] on_online_callback = {self.on_online_callback}")
                        if self.on_online_callback:
                            print(f"[DEBUG] Calling Telegram callback for {contact_name}")
                            try:
                                import glob
                                import shutil
                                import tempfile
                                
                                # Also search with + prefix (original phone format)
                                phone_clean = contact_phone.replace('+', '').replace(' ', '')
                                debug_files = glob.glob(os.path.join(os.path.dirname(__file__), f'debug_{phone_clean}_*.png'))
                                
                                # Also check with + prefix in filename
                                if not debug_files:
                                    debug_files_plus = glob.glob(os.path.join(os.path.dirname(__file__), f'debug_+{phone_clean}_*.png'))
                                    if debug_files_plus:
                                        debug_files = debug_files_plus
                                
                                if debug_files:
                                    screenshot_path = max(debug_files, key=os.path.getmtime)
                                    print(f"Kullanilacak debug screenshot: {screenshot_path}")
                                else:
                                    print(f"[WARN] Debug screenshot bulunamadi, yeni screenshot cekilecek")
                                    screenshot_path = os.path.join(os.path.dirname(__file__), f'notify_{phone_clean}_{int(time.time())}.png')
                                    try:
                                        result = self.take_screenshot(screenshot_path)
                                        if result and result.get('success'):
                                            print(f"Yeni screenshot cekildi: {screenshot_path}")
                                        else:
                                            print(f"Screenshot hatasi: {result.get('message') if result else 'Bilinmeyen hata'}")
                                            screenshot_path = None
                                    except Exception as e:
                                        print(f"Screenshot hatasi: {e}")
                                        screenshot_path = None
                                
                                if not screenshot_path:
                                    print("[WARN] Screenshot yok, bildirim ekransiz gonderilecek")
                                    temp_screenshot = None
                                else:
                                    temp_dir = tempfile.gettempdir()
                                    temp_screenshot = os.path.join(temp_dir, f'telegram_notify_{int(time.time())}.png')
                                    shutil.copy2(screenshot_path, temp_screenshot)
                                
                                contact_info = {
                                    'name': contact_name,
                                    'phone': contact_phone,
                                    'screenshot_path': temp_screenshot
                                }
                                self.on_online_callback(contact_info)
                            except Exception as e:
                                import traceback
                                print(f"[TELEGRAM ERROR] Bildirim hatasi: {e}")
                                traceback.print_exc()
                    
                    # Report status change to main thread for DB update
                    if self.on_status_change_callback:
                        self.on_status_change_callback({
                            'type': 'status_change',
                            'contact_id': contact_id,
                            'is_online': actual_is_online,
                            'timestamp': now,
                            'contact_name': contact_name,
                            'contact_phone': contact_phone
                        })
                    
                    last_states[contact_id] = actual_is_online
                    print(f"Status change: {contact_name} -> {actual_is_online}")
            
            time.sleep(10)
        
        print("Tracking stopped")
    
    def _disconnect_async(self):
        try:
            self.stop_tracking()
        except:
            pass
        if self.browser:
            try:
                self.browser.close()
            except:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except:
                pass
        self.browser = None
        self.page = None
        self.context = None
        self.connected = False
        self.qr_code = None
        return {'success': True}
    
    def _take_screenshot_async(self, path):
        try:
            if not self.page:
                return {'success': False, 'message': 'No page available'}
            self.page.screenshot(path=path, timeout=10000)
            return {'success': True, 'path': path}
        except Exception as e:
            return {'success': False, 'message': str(e)}
    
    def take_screenshot(self, path):
        return self._execute_operation('take_screenshot', timeout=15, path=path)
    
    def disconnect(self):
        try:
            return self._execute_operation('disconnect', timeout=10)
        except Exception as e:
            print(f"Disconnect operation failed: {e}")
            return {'success': False, 'message': str(e)}
    
    def __del__(self):
        self.running = False
        try:
            self.op_queue.put({'op': 'stop'})
        except:
            pass
