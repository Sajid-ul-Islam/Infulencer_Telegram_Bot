import os
import time
import collections
import logging
import requests
from datetime import datetime
from bot.config import logger

# Global start time for uptime calculation
START_TIME = time.time()

# Store keep-alive ping stats (up to 5 recent pings)
ping_history = collections.deque(maxlen=5)

# Custom Log Handler to keep logs in memory
class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=150):
        super().__init__()
        self.capacity = capacity
        self.logs = collections.deque(maxlen=capacity)

    def emit(self, record):
        try:
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()
            }
            self.logs.append(log_entry)
        except Exception:
            self.handleError(record)

# Initialize the log handler
memory_log_handler = MemoryLogHandler()
memory_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(memory_log_handler)

def ping_self():
    """Pings the bot's own Render URL every 10 minutes to prevent sleeping and tracks latency."""
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        logger.warning("RENDER_EXTERNAL_URL not set. Self-ping latency tracking is disabled.")
        return
        
    while True:
        try:
            start_ping = time.time()
            response = requests.get(url, timeout=10)
            latency = int((time.time() - start_ping) * 1000)
            
            ping_entry = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "status": response.status_code,
                "latency": latency
            }
            ping_history.append(ping_entry)
            logger.info(f"Self-ping executed: Status {response.status_code} ({latency}ms)")
        except Exception as e:
            logger.error(f"Self-ping failed: {e}")
        time.sleep(600)  # Sleep 10 minutes between pings
