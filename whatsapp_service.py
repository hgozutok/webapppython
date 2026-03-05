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
                
                if op['op'] == 'connect':
                    result = await self._connect_async()
                    self.result_queue.put(result)
                
                elif op['op'] == 'get_qr':
                    result = await self._get_qr_async()
                    self.result_queue.put(result)
                
                elif op['op'] == 'is_connected':
                    result = await self._is_connected_async()
                    self.result_queue.put(result)
                
                elif op['op'] == 'check_online_status':
                    result = await self._check_online_status_async(op['phone'])
                    self.result_queue.put(result)
                
                elif op['op'] == 'disconnect':
                    result = await self._disconnect_async()
                    self.result_queue.put(result)
                
                elif op['op'] == 'stop':
                    break
                
                self.op_queue.task_done()
            
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in playwright loop: {e}")
                self.result_queue.put({'error': str(e)})
        
        # Cleanup
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    def _execute_operation(self, op_name, timeout=10, **kwargs):
        """Execute an operation on the Playwright thread"""
        try:
            self.op_queue.put({'op': op_name, **kwargs})
            result = self.result_queue.get(timeout=timeout)
            
            if isinstance(result, dict) and 'error' in result:
                raise Exception(result['error'])
            
            return result
        except queue.Empty:
            raise TimeoutError(f"Operation {op_name} timed out")
    
    async def _connect_async(self):
        try:
            # Use persistent context for session persistence
            import os
            user_data_dir = os.path.join(os.path.dirname(__file__), 'whatsapp_session')
            
            if self.browser:
                # Close existing browser
                await self.browser.close()
            
            # Launch with persistent context
            self.browser = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                args=['--disable-blink-features=AutomationControlled']
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
            
            # Try direct URL with phone number
            clean_phone = phone_number.replace('+', '')
            chat_url = f'https://web.whatsapp.com/send?phone={clean_phone}'
            print(f"Navigating to chat URL: {chat_url}")
            
            try:
                await self.page.goto(chat_url, timeout=30000)
                await self.page.wait_for_load_state('networkidle', timeout=10000)
                print("Page loaded")
            except Exception as e:
                print(f"Error navigating to chat: {e}")
                return None
            
            # Wait for chat to open
            print("Waiting for chat...")
            await asyncio.sleep(5)
            
            # Check online status
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    // Check URL to see if we're still on main page
                    const url = window.location.href;
                    console.log('Current URL:', url);
                    
                    // Try multiple ways to check online status
                    const allText = document.body.innerText || document.body.textContent || '';
                    
                    console.log('Page text preview:', allText.substring(0, 300));
                    
                    // Look for "çevrimiçi" or "online" in ANY text on page
                    let foundOnline = allText.toLowerCase().includes('çevrimiçi') || 
                                          allText.toLowerCase().includes('online') ||
                                          allText.toLowerCase().includes('şu an');
                    
                    console.log('Is online:', foundOnline);
                    
                    return {{ 
                        success: true, 
                        is_online: foundOnline,
                        message: 'Checked page text',
                        text: allText.substring(0, 200)
                    }};
                }} catch (e) {{
                    console.error('Error checking status:', e);
                    return {{ success: false, message: e.message }};
                }}
            }}""")
            
            print(f"Online status result: {result}")
            
            if result and result['success']:
                is_online = result['is_online']
                message = result.get('message', '')
                text = result.get('text', '')
                print(f"Online status for {phone_number}: {is_online}, Message: {message}")
                return is_online
            else:
                print(f"Failed to get online status: {result}")
                return None
                
        except Exception as e:
            print(f"Error checking status for {phone_number}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        try:
            print(f"Checking online status for: {phone_number}")
            
            # Try direct URL with phone number
            # Remove + if present
            clean_phone = phone_number.replace('+', '')
            chat_url = f'https://web.whatsapp.com/send?phone={clean_phone}'
            print(f"Navigating to chat URL: {chat_url}")
            
            try:
                await self.page.goto(chat_url, timeout=30000)
                await self.page.wait_for_load_state('networkidle', timeout=10000)
                print("Page loaded, checking status...")
            except Exception as e:
                print(f"Error navigating to chat URL: {e}")
                return None
            
            # Wait for chat to open
            print("Waiting for chat to open...")
            await asyncio.sleep(5)
            
            # Check online status
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    // Wait a bit
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    
                    // Get all text from page
                    const allText = document.body.innerText || document.body.textContent || '';
                    console.log('Page text length:', allText.length);
                    console.log('Page text preview:', allText.substring(0, 500));
                    
                    // Check if we're still on main page
                    if (allText.includes('Aratın veya yeni sohbet başlatın') ||
                        allText.includes('Tümü') ||
                        allText.includes('Favoriler')) {{
                        console.log('Still on main page');
                        
                        // Check for online status on main page
                        const isOnline = allText.toLowerCase().includes('çevrimiçi') || 
                                         allText.toLowerCase().includes('online');
                        
                        return {{ 
                            success: true, 
                            is_online: isOnline, 
                            message: 'On main page'
                        }};
                    }}
                    
                    // Check for last-seen element
                    const lastSeen = document.querySelector('[data-testid="last-seen"]');
                    console.log('Last seen element found:', !!lastSeen);
                    
                    if (lastSeen) {{
                        const lastSeenText = lastSeen.innerText || lastSeen.textContent || '';
                        console.log('Last seen text:', lastSeenText);
                        
                        const isOnline = lastSeenText.toLowerCase().includes('çevrimiçi') || 
                                       lastSeenText.toLowerCase().includes('online') ||
                                       lastSeenText.toLowerCase().includes('here') ||
                                       lastSeenText.toLowerCase().includes('şu an');
                        
                        console.log('Is online (from last-seen):', isOnline);
                        
                        return {{ 
                            success: true, 
                            is_online: isOnline, 
                            message: 'Found last-seen',
                            text: lastSeenText.substring(0, 100)
                        }};
                    }}
                    
                    // Check in page text
                    const isOnline = allText.toLowerCase().includes('çevrimiçi') || 
                                     allText.toLowerCase().includes('online') ||
                                     allText.toLowerCase().includes('şu an çevrimiçi');
                    
                    console.log('Is online (from page text):', isOnline);
                    
                    return {{ 
                        success: true, 
                        is_online: isOnline,
                        message: 'Checked page text',
                        text: allText.substring(0, 200)
                    }};
                }} catch (e) {{
                    console.error('Error checking status:', e);
                    return {{ success: false, message: e.message }};
                }}
            }}""")
            
            print(f"Online status result: {result}")
            
            if result and result['success']:
                is_online = result['is_online']
                message = result.get('message', '')
                text = result.get('text', '')
                print(f"Online status for {phone_number}: {is_online}, Message: {message}, Text: {text[:100] if text else 'N/A'}")
                return is_online
            else:
                print(f"Failed to get online status: {result}")
                return None
                
        except Exception as e:
            print(f"Error checking status for {phone_number}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        try:
            print(f"Checking online status for: {phone_number}")
            
            # Go back to main page first
            await self.page.goto('https://web.whatsapp.com')
            await self.page.wait_for_load_state('networkidle', timeout=10000)
            await asyncio.sleep(2)
            
            # Use JavaScript to search and open chat
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    // Wait for search box
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    
                    // Find search box
                    const searchBox = document.querySelector('[contenteditable="true"][data-testid="search"]') ||
                                          document.querySelector('[data-testid="search"]');
                    
                    if (!searchBox) {{
                        console.log('Search box not found');
                        return {{ success: false, message: 'Search box not found' }};
                    }}
                    
                    console.log('Search box found');
                    
                    // Clear and type phone number
                    searchBox.focus();
                    searchBox.textContent = '';
                    searchBox.value = '';
                    
                    const phone = '{phone_number}';
                    for (let i = 0; i < phone.length; i++) {{
                        searchBox.textContent += phone[i];
                        searchBox.value += phone[i];
                        searchBox.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                    
                    console.log('Typed phone number:', phone);
                    
                    // Wait for search results
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    
                    // Press Enter or click first result
                    const firstResult = document.querySelector('[role="gridcell"]');
                    if (firstResult) {{
                        console.log('Found chat result');
                        firstResult.click();
                    }} else {{
                        // Try pressing Enter
                        const enterEvent = new KeyboardEvent('keydown', {{
                            key: 'Enter',
                            code: 'Enter',
                            keyCode: 13,
                            bubbles: true
                        }});
                        searchBox.dispatchEvent(enterEvent);
                    }}
                    
                    return {{ success: true, message: 'Search completed' }};
                }} catch (e) {{
                    console.error('Error in JS:', e);
                    return {{ success: false, message: e.message }};
                }}
            }}""")
            
            print(f"Search result: {result}")
            
            if not result or not result['success']:
                print("Search failed")
                return None
            
            # Wait for chat to open
            print("Waiting for chat to open...")
            await asyncio.sleep(5)
            
            # Check online status
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    // Wait for chat to load
                    await new Promise(resolve => setTimeout(resolve, 3000));
                    
                    // Check if we're on chat page
                    const url = window.location.href;
                    console.log('Current URL:', url);
                    
                    if (url.includes('web.whatsapp.com') && !url.includes('send') && !url.includes('chat')) {{
                        console.log('Still on main page');
                        
                        // Look for any online status in entire page
                        const allText = document.body.innerText || '';
                        const isOnline = allText.toLowerCase().includes('çevrimiçi') || 
                                         allText.toLowerCase().includes('online');
                        
                        return {{ 
                            success: true, 
                            is_online: isOnline, 
                            message: 'Checking main page'
                        }};
                    }}
                    
                    // Try to find chat panel
                    const chatPanel = document.querySelector('[data-testid="conversation-panel-messages"]') ||
                                       document.querySelector('[data-testid="conversation-panel-body"]') ||
                                       document.querySelector('div[data-testid="chat-panel"]');
                    
                    if (!chatPanel) {{
                        console.log('Chat panel not found');
                        
                        // Check in main content
                        const mainContent = document.querySelector('main') || document.body;
                        const allText = mainContent.innerText || mainContent.textContent || '';
                        const isOnline = allText.toLowerCase().includes('çevrimiçi') || 
                                         allText.toLowerCase().includes('online');
                        
                        return {{ 
                            success: true, 
                            is_online: isOnline,
                            message: 'Checking main content'
                        }};
                    }}
                    
                    // Get chat panel text
                    let allText = chatPanel.innerText || chatPanel.textContent || '';
                    console.log('Chat panel text length:', allText.length);
                    console.log('Chat panel text preview:', allText.substring(0, 300));
                    
                    // Check for indicators that we're NOT in a real chat
                    if (allText.includes('Aratın veya yeni sohbet başlatın') ||
                        allText.includes('Tümü') ||
                        allText.includes('Favoriler')) {{
                        console.log('Still on main page');
                        
                        const isOnline = allText.toLowerCase().includes('çevrimiçi') || 
                                         allText.toLowerCase().includes('online');
                        
                        return {{ 
                            success: true, 
                            is_online: isOnline,
                            message: 'Still on main page'
                        }};
                    }}
                    
                    // Look for online status
                    const lastSeen = document.querySelector('[data-testid="last-seen"]');
                    console.log('Last seen element found:', !!lastSeen);
                    
                    let isOnline = false;
                    
                    if (lastSeen) {{
                        const lastSeenText = lastSeen.innerText || lastSeen.textContent || '';
                        console.log('Last seen text:', lastSeenText);
                        
                        isOnline = lastSeenText.toLowerCase().includes('çevrimiçi') || 
                                   lastSeenText.toLowerCase().includes('online') ||
                                   lastSeenText.toLowerCase().includes('here') ||
                                   lastSeenText.toLowerCase().includes('şu an');
                    }}
                    
                    // Also check in chat panel text
                    isOnline = isOnline || allText.toLowerCase().includes('çevrimiçi') || 
                                     allText.toLowerCase().includes('online') ||
                                     allText.toLowerCase().includes('şu an çevrimiçi');
                    
                    console.log('Is online:', isOnline);
                    
                    return {{ 
                        success: true, 
                        is_online: isOnline, 
                        text: allText.substring(0, 300)
                    }};
                }} catch (e) {{
                    console.error('Error checking status:', e);
                    return {{ success: false, message: e.message }};
                }}
            }}""")
            
            print(f"Online status result: {result}")
            
            if result and result['success']:
                is_online = result['is_online']
                message = result.get('message', '')
                text = result.get('text', '')
                print(f"Online status for {phone_number}: {is_online}, Message: {message}, Text: {text[:100] if text else 'N/A'}")
                return is_online
            else:
                print(f"Failed to get online status: {result}")
                return None
                
        except Exception as e:
            print(f"Error checking status for {phone_number}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        try:
            print(f"Checking online status for: {phone_number}")
            
            # Navigate directly to chat URL first
            chat_url = f'https://web.whatsapp.com/send?phone={phone_number}'
            print(f"Navigating to chat URL: {chat_url}")
            await self.page.goto(chat_url)
            await self.page.wait_for_load_state('networkidle', timeout=10000)
            
            # Wait for chat panel to load
            print("Waiting for chat panel...")
            await asyncio.sleep(5)
            
            # Check online status using JavaScript
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    // Wait a bit more
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    
                    // Check URL to make sure we're on chat page
                    const currentUrl = window.location.href;
                    console.log('Current URL:', currentUrl);
                    
                    if (!currentUrl.includes('send') && !currentUrl.includes('chat')) {{
                        console.log('Not on chat page yet');
                        return {{ 
                            success: false, 
                            message: 'Not on chat page',
                            is_online: false 
                        }};
                    }}
                    
                    // Try multiple selectors for chat panel
                    const chatPanel = document.querySelector('[data-testid="conversation-panel-messages"]') ||
                                       document.querySelector('[data-testid="conversation-panel-body"]') ||
                                       document.querySelector('div[data-testid="chat-panel"]');
                    
                    console.log('Chat panel found:', !!chatPanel);
                    
                    if (!chatPanel) {{
                        return {{ 
                            success: false, 
                            message: 'Chat panel not loaded',
                            is_online: false 
                        }};
                    }}
                    
                    // Get chat panel text
                    let allText = chatPanel.innerText || chatPanel.textContent || '';
                    console.log('Chat panel text length:', allText.length);
                    console.log('Chat panel text preview:', allText.substring(0, 200));
                    
                    if (allText.length < 10) {{
                        console.log('Chat panel text too short, panel not loaded');
                        return {{ 
                            success: false, 
                            message: 'Chat panel text too short',
                            is_online: false 
                        }};
                    }}
                    
                    // Check for indicators that we're NOT on a real chat
                    if (allText.includes('Aratın veya yeni sohbet başlatın') ||
                        allText.includes('Tümü') ||
                        allText.includes('Favoriler')) {{
                        console.log('Still on main page, not in chat');
                        return {{ 
                            success: false, 
                            message: 'Still on main page',
                            is_online: false 
                        }};
                    }}
                    
                    // Look for online status
                    const lastSeen = document.querySelector('[data-testid="last-seen"]');
                    console.log('Last seen element found:', !!lastSeen);
                    
                    let isOnline = false;
                    
                    if (lastSeen) {{
                        const lastSeenText = lastSeen.innerText || lastSeen.textContent || '';
                        console.log('Last seen text:', lastSeenText);
                        
                        isOnline = lastSeenText.toLowerCase().includes('çevrimiçi') || 
                                   lastSeenText.toLowerCase().includes('online') ||
                                   lastSeenText.toLowerCase().includes('here') ||
                                   lastSeenText.toLowerCase().includes('şu an çevrimiçi');
                    }}
                    
                    // Also check in chat panel text
                    isOnline = isOnline || allText.toLowerCase().includes('çevrimiçi') || 
                                      allText.toLowerCase().includes('online') ||
                                      allText.toLowerCase().includes('şu an çevrimiçi');
                    
                    console.log('Is online:', isOnline);
                    
                    return {{ 
                        success: true, 
                        is_online: isOnline, 
                        text: allText.substring(0, 200) 
                    }};
                }} catch (e) {{
                    console.error('Error checking status:', e);
                    return {{ success: false, message: e.message }};
                }}
            }}""")
            
            print(f"Online status result: {result}")
            
            if result and result['success']:
                is_online = result['is_online']
                message = result.get('message', '')
                text = result.get('text', '')
                print(f"Online status for {phone_number}: {is_online}, Message: {message}, Text: {text[:100] if text else 'N/A'}")
                return is_online
            else:
                print(f"Failed to get online status: {result}")
                return None
                
        except Exception as e:
            print(f"Error checking status for {phone_number}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        try:
            print(f"Checking online status for: {phone_number}")
            
            # Use JavaScript to find and interact with elements
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    // Find search box using JavaScript
                    const searchBox = document.querySelector('[contenteditable="true"][data-testid="search"]') ||
                                      document.querySelector('div[contenteditable="true"]') ||
                                      document.querySelector('input[type="text"]') ||
                                      document.querySelector('[role="searchbox"]');
                    
                    if (!searchBox) {{
                        console.log('Search box not found via JS');
                        return {{ success: false, message: 'Search box not found' }};
                    }}
                    
                    console.log('Search box found:', searchBox);
                    
                    // Click and focus
                    searchBox.click();
                    searchBox.focus();
                    
                    // Clear and type phone number
                    searchBox.textContent = '';
                    searchBox.value = '';
                    
                    // Type phone number character by character
                    const phone = '{phone_number}';
                    for (let i = 0; i < phone.length; i++) {{
                        searchBox.textContent += phone[i];
                        searchBox.value += phone[i];
                        searchBox.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                    
                    console.log('Typed phone number:', phone);
                    
                    return {{ success: true, message: 'Search box filled' }};
                }} catch (e) {{
                    console.error('Error in JS:', e);
                    return {{ success: false, message: e.message }};
                }}
            }}""")
            
            print(f"JS result: {result}")
            
            if not result or not result['success']:
                print("Failed to fill search via JS")
                return None
            
            # Wait for search results
            await asyncio.sleep(3)
            
            # Click on first chat result using JavaScript
            result = await self.page.evaluate("""async () => {
                try {
                    // Find chat by phone number or gridcell
                    const phone = '""" + phone_number + """';
                    
                    // Try to find by data-id
                    let chat = document.querySelector(`[data-id="${phone}"]`);
                    
                    // If not found, try to find by title
                    if (!chat) {
                        const allChats = document.querySelectorAll('[role="gridcell"], [data-id]');
                        for (let c of allChats) {
                            const title = c.getAttribute('title') || c.getAttribute('data-id') || '';
                            if (title.includes(phone)) {
                                chat = c;
                                break;
                            }
                        }
                    }
                    
                    // If still not found, click first gridcell
                    if (!chat) {
                        chat = document.querySelector('[role="gridcell"]');
                    }
                    
                    if (chat) {
                        console.log('Found chat:', chat);
                        chat.click();
                        return { success: true, message: 'Chat clicked' };
                    }
                    
                    return { success: false, message: 'Chat not found' };
                } catch (e) {
                    console.error('Error clicking chat:', e);
                    return { success: false, message: e.message };
                }
            }""")
            
            print(f"Chat click result: {result}")
            
            # Wait for chat to load - LONGER WAIT
            print("Waiting for chat panel to load (longer wait)...")
            await asyncio.sleep(8)
            
            # Try to scroll to load chat panel
            await self.page.evaluate("""() => {
                try {
                    const chatPanel = document.querySelector('[data-testid="conversation-panel-messages"]');
                    if (chatPanel) {
                        chatPanel.scrollTop = chatPanel.scrollHeight;
                    }
                } catch (e) {
                    console.log('Scroll error:', e);
                }
            }""")
            
            await asyncio.sleep(2)
            
            # Check online status using JavaScript
            result = await self.page.evaluate(f"""async () => {{
                try {{
                    // Wait a bit for chat panel to load
                    await new Promise(resolve => setTimeout(resolve, 5000));
                    
                    // Try multiple selectors for chat panel
                    const chatPanel = document.querySelector('[data-testid="conversation-panel-messages"]') ||
                                       document.querySelector('[data-testid="conversation-panel-body"]') ||
                                       document.querySelector('div[data-testid="chat-panel"]');
                    
                    console.log('Chat panel found:', !!chatPanel);
                    
                    if (!chatPanel) {{
                        console.log('Chat panel still not loaded, trying fallback...');
                        
                        // Try to find any conversation content
                        const mainContent = document.querySelector('main') || document.body;
                        const allText = mainContent.innerText || mainContent.textContent || '';
                        
                        // Check for online status in entire text
                        const isOnline = allText.toLowerCase().includes('çevrimiçi') || 
                                         allText.toLowerCase().includes('online') ||
                                         allText.toLowerCase().includes('şu an çevrimiçi');
                        
                        console.log('Is online (fallback):', isOnline);
                        return {{ 
                            success: true, 
                            is_online: isOnline, 
                            text: 'Fallback: ' + allText.substring(0, 200) 
                        }};
                    }}
                    
                    // Get chat panel text
                    let allText = chatPanel.innerText || chatPanel.textContent || '';
                    console.log('Chat panel text length:', allText.length);
                    console.log('Chat panel text preview:', allText.substring(0, 300));
                    
                    // Look for specific online indicators
                    const lastSeen = document.querySelector('[data-testid="last-seen"]');
                    console.log('Last seen element found:', !!lastSeen);
                    
                    if (lastSeen) {{
                        const lastSeenText = lastSeen.innerText || lastSeen.textContent || '';
                        console.log('Last seen text:', lastSeenText);
                        
                        // Check for online in last seen
                        const isOnline = lastSeenText.toLowerCase().includes('çevrimiçi') || 
                                         lastSeenText.toLowerCase().includes('online') ||
                                         lastSeenText.toLowerCase().includes('here') ||
                                         lastSeenText.toLowerCase().includes('şu an');
                        
                        console.log('Is online (from last-seen):', isOnline);
                        return {{ 
                            success: true, 
                            is_online: isOnline, 
                            text: lastSeenText.substring(0, 200) 
                        }};
                    }}
                    
                    // Check in chat panel text
                    const isOnline = allText.toLowerCase().includes('çevrimiçi') || 
                                     allText.toLowerCase().includes('online') ||
                                     allText.toLowerCase().includes('şu an çevrimiçi') ||
                                     allText.toLowerCase().includes('şu an çevrimiçi');
                    
                    console.log('Is online (from chat panel):', isOnline);
                    
                    return {{ 
                        success: true, 
                        is_online: isOnline, 
                        text: allText.substring(0, 300) 
                    }};
                }} catch (e) {{
                    console.error('Error checking status:', e);
                    return {{ success: false, message: e.message }};
                }}
            }}""")
            
            print(f"Online status result: {result}")
            
            if result and result['success']:
                is_online = result['is_online']
                text = result.get('text', '')
                print(f"Online status for {phone_number}: {is_online}, Text: {text[:100] if text else 'N/A'}")
                return is_online
            else:
                print(f"Failed to get online status: {result}")
                return None
                
        except Exception as e:
            print(f"Error checking status for {phone_number}: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        try:
            print(f"Checking online status for: {phone_number}")
            
            # Debug: Take screenshot
            try:
                import os
                screenshot_path = os.path.join(os.path.dirname(__file__), f'debug_{phone_number}.png')
                await self.page.screenshot(path=screenshot_path, timeout=5000)
                print(f"Screenshot saved to: {screenshot_path}")
            except Exception as e:
                print(f"Could not take screenshot: {e}")
            
            # Debug: Print page URL and title
            url = self.page.url
            title = await self.page.title()
            print(f"Current page - URL: {url}, Title: {title}")
            
            # Wait for page to be ready
            try:
                await self.page.wait_for_load_state('networkidle', timeout=5000)
                print("Page is ready (networkidle)")
            except Exception as e:
                print(f"Wait for load state failed: {e}")
            
            # Try to click on body first to focus the page
            try:
                await self.page.click('body', timeout=2000)
                print("Clicked on body to focus page")
            except:
                pass
            
            # Wait a bit for everything to load
            await asyncio.sleep(2)
            
            # Try multiple search box selectors
            search_selectors = [
                '[contenteditable="true"][data-testid="search"]',
                '[contenteditable="true"][title*="Ara"]',
                '[contenteditable="true"][placeholder*="Ara"]',
                'div[contenteditable="true"]',
                'input[placeholder*="Ara"]',
                'input[title*="Ara"]',
                '[data-testid="search"]'
            ]
            
            search_box = None
            for selector in search_selectors:
                try:
                    search_box = self.page.locator(selector)
                    count = await search_box.count()
                    print(f"Selector {selector}: found {count} elements")
                    if count > 0:
                        await search_box.wait_for(state='visible', timeout=2000)
                        await search_box.click(timeout=2000)
                        print(f"Search box clicked using selector: {selector}")
                        break
                except Exception as e:
                    print(f"Selector {selector} failed: {e}")
                    continue
            
            if not search_box:
                print("No search box found - WhatsApp page might not be loaded properly")
                print("Please check the Chrome window and ensure WhatsApp Web is loaded")
                return None
            
            await asyncio.sleep(0.5)
            await search_box.fill('', timeout=2000)
            await asyncio.sleep(0.5)
            await search_box.fill(phone_number, timeout=2000)
            print(f"Filled search with: {phone_number}")
            await asyncio.sleep(3)
            
            # Try multiple chat selectors
            chat_selectors = [
                f'[data-id="{phone_number}"]',
                f'[title*="{phone_number}"]',
                f'[aria-label*="{phone_number}"]'
            ]
            
            chat = None
            for selector in chat_selectors:
                try:
                    chat = self.page.locator(selector)
                    count = await chat.count()
                    print(f"Chat selector {selector}: found {count} chats")
                    if count > 0:
                        break
                except:
                    continue
            
            if not chat or await chat.count() == 0:
                # Try first gridcell
                gridcells = self.page.locator('[role="gridcell"], div[role="gridcell"]')
                gridcell_count = await gridcells.count()
                print(f"Found {gridcell_count} gridcells")
                if gridcell_count > 0:
                    chat = gridcells.first
            
            if chat and await chat.count() > 0:
                await chat.click(timeout=2000)
                print("Chat clicked")
                await asyncio.sleep(3)
                
                # Try multiple last-seen selectors
                last_seen_selectors = [
                    '[data-testid="last-seen"]',
                    'span:has-text("çevrimiçi")',
                    'span:has-text("online")',
                    'div[data-testid="conversation-panel-messages"] span:last-child'
                ]
                
                for selector in last_seen_selectors:
                    try:
                        last_seen = self.page.locator(selector)
                        count = await last_seen.count()
                        if count > 0:
                            text = await last_seen.first.inner_text()
                            print(f"Found last-seen element: {text}")
                            is_online = 'çevrimiçi' in text.lower() or 'online' in text.lower()
                            print(f"Online status for {phone_number}: {is_online}")
                            return is_online
                    except:
                        continue
                
                print("No last-seen element found")
                return False
            else:
                print(f"No chat found for {phone_number}")
                return None
                
        except Exception as e:
            print(f"Error checking status for {phone_number}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def check_online_status(self, phone_number):
        return self._execute_operation('check_online_status', timeout=30, phone=phone_number)
    
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
                        
                        if is_online:
                            contact.last_online_at = datetime.now()
                            print(f"{contact.name} is now ONLINE")
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
                                print(f"{contact.name} is now OFFLINE, duration: {duration}s")
                        
                        last_states[contact.id] = is_online
                        db.session.commit()
                
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