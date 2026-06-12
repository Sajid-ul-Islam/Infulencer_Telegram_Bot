import os
import time
import threading
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from bot.config import logger

def ping_self():
    """Pings the bot's own Render URL every 10 minutes to prevent sleeping."""
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        logger.warning("RENDER_EXTERNAL_URL not set. Self-ping will not work.")
        return
        
    while True:
        try:
            time.sleep(600)  # Sleep 10 minutes
            response = requests.get(url)
            logger.info(f"Self-ping executed: Status {response.status_code}")
        except Exception as e:
            logger.error(f"Self-ping failed: {e}")

def start_dummy_server():
    """Starts a dummy HTTP server to satisfy Render's Web Service port binding requirement."""
    port = int(os.environ.get("PORT", 8080))
    class DummyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Bot is running!")
        # Suppress logging to keep the console clean
        def log_message(self, format, *args):
            pass
            
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

def start_server_threads():
    """Start the dummy server and self pinger in background threads."""
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    
    logger.info("Dummy web server & self-pinger started to keep Render happy!")
