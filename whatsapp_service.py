import asyncio
import threading
import queue
from playwright.async_api import async_playwright
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
        
        # Queue for Playwright operations
        self.op_queue = queue.Queue()
        self.result_queue = queue.Queue()
        
        # Start Playwright thread
        self.playwright_thread = None
        self.running = True
        self._start_playwright_thread()
        
    def _start_playwright_thread(self):
        """Start the dedicated Playwright thread"""
        def run_playwright():
            asyncio.run(self._playwright_loop())
        
        self.playwright_thread = threading.Thread(target=run_playwright, daemon=True)
        self.playwright_thread.start()
    
    async def _playwright_loop(self):
        """Main event loop for all Playwright operations"""
        self.playwright = await async_playwright().start()
        
        while self.running:
            try:
                # Get operation from queue with timeout
                op = self.op_queue.get(timeout=1.0)
                
                op_id = op.get('op_id')
                result = None
                
                if op['op'] == 'connect':
                    result = await self._connect_async()
                elif op['op'] == 'get_qr':
                    result = await self._get_qr_async()
                elif op['op'] == 'is_connected':
                    result = await self._is_connected_async()
                elif op['op'] == 'check_online_status':
                    result = await self._check_online_status_async(op['phone'])
                elif op['op'] == 'disconnect':
                    result = await self._disconnect_async()
                elif op['op'] == 'stop':
                    break
                
                self.result_queue.put({'op_id': op_id, 'result': result})
                self.op_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in playwright loop: {e}")
                self.result_queue.put({'op_id': op_id, 'error': str(e)})
        
        # Cleanup
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    def _execute_operation(self, op_name, timeout=10, **kwargs):
        """Execute an operation on the Playwright thread"""
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
    
    async def _connect_async(self):
        try:
            # Use persistent context for session persistence
            import os
            user_data_dir = os.path.join(os.path.dirname(__file__), 'whatsapp_session')
            
            # Close existing browser and playwright properly
            if self.browser:
                try:
                    await self.browser.close()
                except:
                    pass
                self.browser = None
            
            if self.playwright:
                try:
                    await self.playwright.stop()
                except:
                    pass
                self.playwright = None
            
            # Restart playwright
            self.playwright = await async_playwright().start()
            
            # Launch with persistent context
            self.browser = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                args=['--disable-blink-features=AutomationControlled'],
                timeout=60000
            )
            
            # Get or create page
            if len(self.browser.pages) > 0:
                self.page = self.browser.pages[0]
            else:
                self.page = await self.browser.new_page()
            
            # Navigate to WhatsApp
            await self.page.goto('https://web.whatsapp.com')
            
            # Wait for page to load
            await self.page.wait_for_load_state('networkidle', timeout=30000)
            
            # Wait a bit more and check if already logged in
            await asyncio.sleep(3)
            
            # Check if QR code is present (NOT logged in)
            try:
                qr_canvas = await self.page.locator('canvas').count()
                qr_image = await self.page.locator('img[src*="qr"], img[alt*="QR"]').count()
                
                if qr_canvas > 0 or qr_image > 0:
                    print("QR code is visible - NOT logged in yet")
                    self.connected = False
                    return {'success': True, 'message': 'Browser started, waiting for QR scan', 'already_logged_in': False}
            except:
                pass
            
            # Check if we're already logged in by looking for main interface elements
            try:
                search_box = await self.page.locator('[data-testid="search"]').count()
                menu = await self.page.locator('[data-testid="menu"]').count()
                grid = await self.page.locator('div[role="grid"]').count()
                
                if search_box > 0 or menu > 0 or grid > 0:
                    print("Main interface elements found - ALREADY LOGGED IN")
                    self.connected = True
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
    
    async def _get_qr_async(self):
        if not self.page:
            return None
        
        try:
            await asyncio.sleep(3)
            
            print("Looking for QR code...")
            
            canvas_elements = self.page.locator('canvas')
            canvas_count = await canvas_elements.count()
            print(f"Found {canvas_count} canvas elements")
            
            if canvas_count > 0:
                for i in range(min(canvas_count, 5)):
                    try:
                        canvas = canvas_elements.nth(i)
                        screenshot = await canvas.screenshot(timeout=5000)
                        
                        if screenshot and len(screenshot) > 5000:
                            print(f"QR code found from canvas {i}, size: {len(screenshot)}")
                            self.qr_code = screenshot
                            return base64.b64encode(self.qr_code).decode('utf-8')
                    except Exception as e:
                        print(f"Error capturing canvas {i}: {e}")
                        continue
            
            qr_images = self.page.locator('img[src*="qr"], img[alt*="QR"], img[src*="QR"]')
            img_count = await qr_images.count()
            print(f"Found {img_count} QR image elements")
            
            if img_count > 0:
                try:
                    screenshot = await qr_images.first.screenshot(timeout=5000)
                    if screenshot and len(screenshot) > 1000:
                        print(f"QR code found from image, size: {len(screenshot)}")
                        return base64.b64encode(screenshot).decode('utf-8')
                except Exception as e:
                    print(f"Error capturing QR image: {e}")
            
            qr_divs = self.page.locator('div[style*="qr"], div[class*="qr"]')
            if await qr_divs.count() > 0:
                try:
                    screenshot = await qr_divs.first.screenshot(timeout=5000)
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
    
    async def _is_connected_async(self):
        if not self.page:
            return False
        
        try:
            title = await self.page.title()
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
                                count = await element.count()
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
    
    async def _check_online_status_async(self, phone_number):
        if not self.page or not self.connected:
            print(f"Cannot check status - page: {self.page is not None}, connected: {self.connected}")
            return None
        
        try:
            print(f"Checking online status for: {phone_number}")
            
            # Navigate to chat
            clean_phone = phone_number.replace('+', '').replace(' ', '')
            chat_url = f'https://web.whatsapp.com/send?phone={clean_phone}'
            print(f"Navigating to chat URL: {chat_url}")
            
            await self.page.goto(chat_url, timeout=30000)
            await self.page.wait_for_load_state('networkidle', timeout=10000)
            
            # Wait for chat to load
            print("Waiting for chat to load...")
            await asyncio.sleep(8)
            
            # Check online status using JavaScript
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    // Wait for DOM to be ready
                    await new Promise(resolve => setTimeout(resolve, 5000));
                    
                    // Check if we're still on main page
                    const url = window.location.href;
                    console.log('Current URL:', url);
                    
                    // Look for online status indicators
                    const lastSeen = document.querySelector('[data-testid="last-seen"]');
                    const allText = document.body.innerText || document.body.textContent || '';
                    
                    console.log('Looking for online status...');
                    console.log('Last seen found:', !!lastSeen);
                    console.log('Page text preview:', allText.substring(0, 200));
                    
                    let isOnline = false;
                    
                    // Check last-seen element
                    if (lastSeen) {{
                        const lastSeenText = lastSeen.innerText || lastSeen.textContent || '';
                        console.log('Last seen text:', lastSeenText);
                        
                        isOnline = lastSeenText.toLowerCase().includes('çevrimiçi') || 
                                   lastSeenText.toLowerCase().includes('online') ||
                                   lastSeenText.toLowerCase().includes('şu an');
                    }}
                    
                    // Check in all page text
                    isOnline = isOnline || allText.toLowerCase().includes('çevrimiçi') || 
                                       allText.toLowerCase().includes('online') ||
                                       allText.toLowerCase().includes('şu an çevrimiçi');
                    
                    console.log('Final is_online status:', isOnline);
                    
                    return {{ 
                        success: true, 
                        is_online: isOnline,
                        message: 'Status checked'
                    }};
                }} catch (e) {{
                    console.error('Error:', e);
                    return {{ success: false, message: e.message }};
                }}
            }}""")
            
            if result and result.get('success'):
                is_online = result.get('is_online', False)
                print(f"Online status for {phone_number}: {is_online}")
                return is_online
            
            return None
                
        except Exception as e:
            print(f"Error checking status for {phone_number}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def check_online_status(self, phone_number):
        return self._execute_operation('check_online_status', timeout=120, phone=phone_number)
    
    def start_tracking(self, contact_ids):
        self.contact_ids = contact_ids
        self.tracking = True
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
                    
                    if is_online is not None and is_online != last_states.get(contact.id):
                        contact.is_online = is_online
                        now = datetime.now()
                        
                        if is_online:
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
                        
                        last_states[contact.id] = is_online
                        db.session.commit()
                        print(f"Saved to DB - is_online: {contact.is_online}, last_online_at: {contact.last_online_at}, last_offline_at: {contact.last_offline_at}")
                
                time.sleep(3)
            
            print("Tracking stopped")
    
    async def _disconnect_async(self):
        self.stop_tracking()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
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