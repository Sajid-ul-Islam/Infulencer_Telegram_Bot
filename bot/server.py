import os
import time
import json
import logging
import threading
import requests
import collections
import asyncio
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from bot.config import (
    logger,
    DASHBOARD_PASSWORD,
    TELEGRAM_TOKEN,
    CHANNEL_ID,
    GROUP_ID,
    YOUTUBE_LINK,
    MEDIUM_LINK,
    SUBSTACK_URL,
    INSTAGRAM_LINK,
    TWITTER_LINK,
    FACEBOOK_LINK
)
from bot.database import FAQ, save_faq, remove_faq, db

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

# Helper to run async functions in synchronous threads
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

def ping_self():
    """Pings the bot's own Render URL every 10 minutes to prevent sleeping and tracks latency."""
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        logger.warning("RENDER_EXTERNAL_URL not set. Self-ping latency tracking is disabled.")
        return
        
    while True:
        try:
            time.sleep(600)  # Sleep 10 minutes
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

def check_and_sync_rss_manually():
    """Manually fetches latest YouTube, Medium, and Substack entries and broadcasts to channel if new."""
    import bot.jobs
    from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts

    def send_tg_message(text, reply_markup=None):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        res = requests.post(url, json=payload, timeout=10)
        return res.status_code == 200

    posts_sent = 0

    # Sync YouTube
    try:
        yt_msg, yt_btn, link = run_async(get_youtube_posts(limit=1))
        if yt_msg and link and link != bot.jobs.last_posted_youtube_url:
            reply_markup = {"inline_keyboard": [[{"text": yt_btn.text, "url": yt_btn.url}]]} if yt_btn else None
            if send_tg_message(yt_msg, reply_markup):
                bot.jobs.last_posted_youtube_url = link
                posts_sent += 1
                logger.info(f"Manual Sync: Posted YouTube video: {link}")
    except Exception as e:
        logger.error(f"Error manually syncing YouTube: {e}")

    # Sync Medium
    try:
        med_msg, med_btn, link = run_async(get_medium_posts(limit=1))
        if med_msg and link and link != bot.jobs.last_posted_medium_url:
            reply_markup = {"inline_keyboard": [[{"text": med_btn.text, "url": med_btn.url}]]} if med_btn else None
            if send_tg_message(med_msg, reply_markup):
                bot.jobs.last_posted_medium_url = link
                posts_sent += 1
                logger.info(f"Manual Sync: Posted Medium article: {link}")
    except Exception as e:
        logger.error(f"Error manually syncing Medium: {e}")

    # Sync Substack
    try:
        sub_msg, sub_btn, link = run_async(get_substack_posts(limit=1))
        if sub_msg and link and link != bot.jobs.last_posted_substack_url:
            reply_markup = {"inline_keyboard": [[{"text": sub_btn.text, "url": sub_btn.url}]]} if sub_btn else None
            if send_tg_message(sub_msg, reply_markup):
                bot.jobs.last_posted_substack_url = link
                posts_sent += 1
                logger.info(f"Manual Sync: Posted Substack newsletter: {link}")
    except Exception as e:
        logger.error(f"Error manually syncing Substack: {e}")

    return posts_sent

# Premium HTML/CSS/JS single page dashboard design for BB Bot HUB
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BB Bot HUB Admin</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #080C14;
            --bg-surface: #0E1424;
            --bg-card: rgba(20, 28, 48, 0.6);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #F3F4F6;
            --text-secondary: #9CA3AF;
            --primary: #3B82F6;
            --primary-glow: rgba(59, 130, 246, 0.4);
            --success: #10B981;
            --success-glow: rgba(16, 185, 129, 0.4);
            --warning: #F59E0B;
            --error: #EF4444;
            --purple: #8B5CF6;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-base);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            overflow-x: hidden;
        }

        .glass {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
        }

        /* Sidebar Styling */
        aside {
            width: 280px;
            background-color: var(--bg-surface);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            padding: 24px;
            position: fixed;
            height: 100vh;
            z-index: 100;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 40px;
        }

        .brand-logo {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, var(--primary), var(--purple));
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 20px;
            box-shadow: 0 0 15px var(--primary-glow);
        }

        .brand-info h2 {
            font-size: 18px;
            font-weight: 600;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: var(--success);
            margin-top: 2px;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background-color: var(--success);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--success-glow);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.9); opacity: 0.6; }
            50% { transform: scale(1.15); opacity: 1; }
            100% { transform: scale(0.9); opacity: 0.6; }
        }

        .nav-links {
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 8px;
            flex-grow: 1;
        }

        .nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            border-radius: 10px;
            color: var(--text-secondary);
            text-decoration: none;
            cursor: pointer;
            transition: all 0.3s ease;
            font-weight: 500;
        }

        .nav-item:hover, .nav-item.active {
            color: var(--text-primary);
            background-color: rgba(255, 255, 255, 0.05);
        }

        .nav-item.active {
            background: linear-gradient(90deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.02) 100%);
            border-left: 4px solid var(--primary);
            color: var(--primary);
        }

        .nav-item svg {
            width: 20px;
            height: 20px;
            fill: none;
            stroke: currentColor;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .aside-footer {
            margin-top: auto;
            border-top: 1px solid var(--border-color);
            padding-top: 20px;
        }

        .logout-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            transition: color 0.3s;
            font-family: inherit;
        }

        .logout-btn:hover {
            color: var(--error);
        }

        /* Main Container */
        main {
            margin-left: 280px;
            flex-grow: 1;
            padding: 40px;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 32px;
        }

        h1 {
            font-size: 28px;
            font-weight: 700;
        }

        /* Button styling */
        .btn {
            padding: 10px 20px;
            border-radius: 10px;
            font-weight: 600;
            font-family: inherit;
            cursor: pointer;
            border: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            transition: all 0.25s ease;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary), #2563EB);
            color: white;
            box-shadow: 0 4px 14px rgba(59, 130, 246, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
        }

        .btn-secondary {
            background-color: rgba(255, 255, 255, 0.08);
            color: var(--text-primary);
        }

        .btn-secondary:hover {
            background-color: rgba(255, 255, 255, 0.12);
        }

        .btn-danger {
            background-color: var(--error);
            color: white;
        }

        .btn-danger:hover {
            background-color: #DC2626;
            transform: translateY(-2px);
        }

        /* Tabs views */
        .tab-content {
            display: none;
            animation: fadeIn 0.4s ease;
        }

        .tab-content.active {
            display: block;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Stats Grid */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
            gap: 20px;
            margin-bottom: 32px;
        }

        .stat-card {
            padding: 24px;
            position: relative;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: linear-gradient(90deg, var(--primary), var(--purple));
        }

        .stat-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--text-secondary);
            font-size: 14px;
        }

        .stat-icon {
            opacity: 0.8;
            color: var(--primary);
        }

        .stat-value {
            font-size: 32px;
            font-weight: 700;
            letter-spacing: -0.5px;
        }

        .stat-desc {
            font-size: 12px;
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        /* Content Layout */
        .grid-2col {
            display: grid;
            grid-template-columns: 1.6fr 1fr;
            gap: 24px;
            margin-bottom: 32px;
        }

        .card {
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 4px;
        }

        .card-title {
            font-size: 18px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        /* Form styling */
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
        }

        label {
            font-size: 14px;
            color: var(--text-secondary);
            font-weight: 500;
        }

        input, textarea, select {
            background-color: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 12px;
            color: var(--text-primary);
            font-family: inherit;
            font-size: 15px;
            transition: all 0.3s;
        }

        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 10px rgba(59, 130, 246, 0.2);
            background-color: rgba(255, 255, 255, 0.08);
        }

        /* Table Styling */
        .table-container {
            overflow-x: auto;
            border-radius: 12px;
            border: 1px solid var(--border-color);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }

        th, td {
            padding: 16px;
            border-bottom: 1px solid var(--border-color);
        }

        th {
            background-color: rgba(255, 255, 255, 0.02);
            color: var(--text-secondary);
            font-weight: 600;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        td {
            font-size: 15px;
        }

        tr:last-child td {
            border-bottom: none;
        }

        .action-cell {
            text-align: right;
        }

        .icon-btn {
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            padding: 6px;
            border-radius: 6px;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
        }

        .icon-btn:hover {
            background-color: rgba(255, 255, 255, 0.05);
        }

        .no-data {
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
            font-style: italic;
        }

        /* Console styling */
        .console-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: #05080E;
            padding: 12px 20px;
            border-top-left-radius: 12px;
            border-top-right-radius: 12px;
            border: 1px solid var(--border-color);
            border-bottom: none;
        }

        .console {
            background-color: #05080E;
            border: 1px solid var(--border-color);
            border-bottom-left-radius: 12px;
            border-bottom-right-radius: 12px;
            padding: 20px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: #D1D5DB;
            height: 480px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 8px;
            box-shadow: inset 0 4px 12px rgba(0, 0, 0, 0.8);
        }

        .console-line {
            line-height: 1.6;
            white-space: pre-wrap;
            border-left: 3px solid transparent;
            padding-left: 8px;
        }

        .console-line.INFO { border-color: var(--primary); color: #E5E7EB; }
        .console-line.WARNING { border-color: var(--warning); color: #FBBF24; }
        .console-line.ERROR { border-color: var(--error); color: #FCA5A5; }
        .console-line .ts { color: var(--text-secondary); font-size: 11px; margin-right: 8px; }

        /* Login Overlay */
        .login-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(5, 8, 14, 0.98);
            z-index: 1000;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .login-card {
            width: 400px;
            padding: 40px;
            display: flex;
            flex-direction: column;
            gap: 24px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .login-card h2 {
            font-size: 24px;
            font-weight: 700;
            text-align: center;
            margin-bottom: 8px;
        }

        .login-error {
            color: var(--error);
            font-size: 14px;
            text-align: center;
            display: none;
        }

        /* Toast Alert */
        .toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            padding: 16px 24px;
            border-radius: 10px;
            z-index: 2000;
            font-weight: 600;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            gap: 10px;
            animation: slideIn 0.3s ease;
        }

        .toast.success { background-color: var(--success); color: white; }
        .toast.error { background-color: var(--error); color: white; }

        @keyframes slideIn {
            from { transform: translateY(20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }

        /* Modals style */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.85);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 999;
        }

        .modal-content {
            width: 500px;
            padding: 40px;
            text-align: center;
            border: 1px solid var(--border-color);
            position: relative;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
        }

        .modal-content::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 6px;
            background: linear-gradient(90deg, var(--primary), var(--purple));
        }

        .winner-crown {
            font-size: 64px;
            animation: bounce 1.5s infinite;
        }

        @keyframes bounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-10px); }
        }

        .winner-name {
            font-size: 32px;
            font-weight: 700;
            background: linear-gradient(135deg, #FFF, #A78BFA);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .platform-link {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            color: var(--text-primary);
            text-decoration: none;
            font-size: 14px;
            transition: background 0.3s;
        }
        .platform-link:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        /* Responsive */
        @media (max-width: 1024px) {
            body { flex-direction: column; }
            aside {
                width: 100%;
                height: auto;
                position: static;
                border-right: none;
                border-bottom: 1px solid var(--border-color);
                padding: 16px 24px;
            }
            .brand { margin-bottom: 20px; }
            .nav-links { flex-direction: row; flex-wrap: wrap; gap: 8px; }
            main { margin-left: 0; padding: 24px; }
            .grid-2col { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>

    <!-- Authentication Overlay -->
    <div id="login-overlay" class="login-overlay">
        <div class="login-card glass">
            <h2>BB Bot HUB Login</h2>
            <div id="login-error" class="login-error">Incorrect password. Please try again.</div>
            <div class="form-group">
                <label for="password-input">Dashboard Password</label>
                <input type="password" id="password-input" placeholder="••••••••">
            </div>
            <button id="login-btn" class="btn btn-primary" style="width: 100%;">Sign In</button>
        </div>
    </div>

    <!-- Toast Notification Container -->
    <div id="toast" class="toast"></div>

    <!-- Winner Announcement Modal -->
    <div id="winner-modal" class="modal-overlay">
        <div class="modal-content glass">
            <div class="winner-crown">👑</div>
            <h2 style="font-size: 20px; color: var(--success);">Winner Selected!</h2>
            <div id="winner-display-name" class="winner-name">Sajid Islam</div>
            <div id="winner-display-id" style="color: var(--text-secondary); font-size: 14px;">User ID: 12345678</div>
            <p style="font-size: 14px; color: var(--text-secondary); line-height: 1.5; margin-top: 10px;">
                The winner has been announced automatically in the Telegram channel.
            </p>
            <button onclick="closeWinnerModal()" class="btn btn-secondary" style="margin-top: 10px;">Dismiss</button>
        </div>
    </div>

    <!-- User Click Breakdown Details Modal -->
    <div id="user-modal" class="modal-overlay" onclick="closeUserModal()">
        <div class="modal-content glass" style="width: 450px; text-align: left; align-items: stretch;" onclick="event.stopPropagation()">
            <h2 id="user-modal-title" style="font-size: 20px; border-bottom: 1px solid var(--border-color); padding-bottom: 12px; margin-bottom: 16px;">User Activity Details</h2>
            <div style="display: flex; flex-direction: column; gap: 12px; font-size: 15px;">
                <div><strong>Username:</strong> <span id="user-modal-name">Unknown</span></div>
                <div><strong>User ID:</strong> <span id="user-modal-id">N/A</span></div>
                <div><strong>Last Active:</strong> <span id="user-modal-active">N/A</span></div>
                <div style="margin-top: 16px;">
                    <strong style="color: var(--primary);">Command Click Breakdown:</strong>
                    <div id="user-modal-commands" style="margin-top: 8px; display: flex; flex-direction: column; gap: 8px;">
                        <!-- Dynamic Command rows -->
                    </div>
                </div>
            </div>
            <button onclick="closeUserModal()" class="btn btn-secondary" style="margin-top: 24px; align-self: flex-end;">Close</button>
        </div>
    </div>

    <!-- Sidebar -->
    <aside>
        <div class="brand">
            <div class="brand-logo">B</div>
            <div class="brand-info">
                <h2>BB Bot HUB</h2>
                <div class="status-badge">
                    <div class="status-dot"></div>
                    <span>Bot Active</span>
                </div>
            </div>
        </div>

        <ul class="nav-links">
            <li class="nav-item active" data-tab="overview">
                <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>
                Overview
            </li>
            <li class="nav-item" data-tab="analytics">
                <svg viewBox="0 0 24 24"><path d="M18 20V10M12 20V4M6 20v-6"></path></svg>
                User Analytics
            </li>
            <li class="nav-item" data-tab="faqs">
                <svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
                FAQ Manager
            </li>
            <li class="nav-item" data-tab="suggestions">
                <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                Suggestions
            </li>
            <li class="nav-item" data-tab="questions">
                <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                Questions
            </li>
            <li class="nav-item" data-tab="giveaways">
                <svg viewBox="0 0 24 24"><polyline points="20 12 20 22 4 22 4 12"></polyline><rect x="2" y="7" width="20" height="5"></rect><line x1="12" y1="22" x2="12" y2="7"></line><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"></path><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"></path></svg>
                Giveaways
            </li>
            <li class="nav-item" data-tab="broadcast">
                <svg viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
                Broadcaster
            </li>
            <li class="nav-item" data-tab="logs">
                <svg viewBox="0 0 24 24"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg>
                Live Logs
            </li>
        </ul>

        <div class="aside-footer">
            <button class="logout-btn" id="logout-btn">
                <svg viewBox="0 0 24 24" style="width:16px;height:16px;"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
                Sign Out
            </button>
        </div>
    </aside>

    <!-- Main Workspace -->
    <main>
        <!-- Header -->
        <header>
            <div>
                <h1 id="page-title">Dashboard</h1>
                <p style="color: var(--text-secondary); margin-top: 4px;">Administration & User Tracker for BB Bot HUB</p>
            </div>
            <div class="header-actions">
                <button onclick="refreshAll()" class="btn btn-secondary">
                    <svg viewBox="0 0 24 24" style="width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2;"><path d="M23 4v6h-6"></path><path d="M1 20v-6h6"></path><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
                    Sync Data
                </button>
            </div>
        </header>

        <!-- OVERVIEW TAB -->
        <section id="tab-overview" class="tab-content active">
            <!-- Stats -->
            <div class="stats-grid">
                <div class="stat-card glass">
                    <div class="stat-header">
                        <span>System Uptime</span>
                        <svg viewBox="0 0 24 24" class="stat-icon" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                    </div>
                    <div class="stat-value" id="stat-uptime">00:00:00</div>
                    <div class="stat-desc">Since last deployment / reboot</div>
                </div>
                <div class="stat-card glass">
                    <div class="stat-header">
                        <span>Keep-Alive Status</span>
                        <div id="heartbeat-pulse" class="status-dot" style="background-color: var(--text-secondary); box-shadow: none;"></div>
                    </div>
                    <div class="stat-value" id="stat-heartbeat" style="font-size: 22px; margin-top: 8px;">No Data</div>
                    <div class="stat-desc" id="stat-heartbeat-desc">Ping latency history</div>
                </div>
                <div class="stat-card glass">
                    <div class="stat-header">
                        <span>Custom FAQs</span>
                        <svg viewBox="0 0 24 24" class="stat-icon" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path></svg>
                    </div>
                    <div class="stat-value" id="stat-faqs">0</div>
                    <div class="stat-desc">Locally cached FAQ patterns</div>
                </div>
                <div class="stat-card glass">
                    <div class="stat-header">
                        <span>Questions Asked</span>
                        <svg viewBox="0 0 24 24" class="stat-icon" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path></svg>
                    </div>
                    <div class="stat-value" id="stat-questions">0</div>
                    <div class="stat-desc">Total user questions in database</div>
                </div>
                <div class="stat-card glass">
                    <div class="stat-header">
                        <span>Topic Suggestions</span>
                        <svg viewBox="0 0 24 24" class="stat-icon" style="width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                    </div>
                    <div class="stat-value" id="stat-suggestions">0</div>
                    <div class="stat-desc">User suggested video topics</div>
                </div>
            </div>

            <!-- Dashboard Columns -->
            <div class="grid-2col">
                <div class="card glass">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" style="width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 2;"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path></svg>
                        Quick Actions
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;">
                        <button onclick="switchTab('analytics')" class="btn btn-secondary">Open User Analytics</button>
                        <button onclick="switchTab('faqs')" class="btn btn-secondary">Manage FAQ Database</button>
                        <button onclick="syncRSS()" id="rss-sync-btn" class="btn btn-secondary">Sync Content Platforms</button>
                        <button onclick="switchTab('giveaways')" class="btn btn-secondary">Draw Giveaway Winner</button>
                    </div>
                </div>
                
                <div class="card glass">
                    <div class="card-title">
                        <svg viewBox="0 0 24 24" style="width: 20px; height: 20px; fill: none; stroke: currentColor; stroke-width: 2;"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
                        Connected Hubs
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 12px;">
                        <a href="TELEGRAM_CHANNEL_LINK" target="_blank" class="platform-link" id="channel-link-display">
                            <span>📢 Telegram Channel:</span> <strong id="channel-id-text">Loading...</strong>
                        </a>
                        <a href="YOUTUBE_LINK" target="_blank" class="platform-link">
                            <span>📺 YouTube Channel</span>
                        </a>
                        <a href="MEDIUM_LINK" target="_blank" class="platform-link">
                            <span>📝 Medium Articles</span>
                        </a>
                        <a href="SUBSTACK_URL" target="_blank" class="platform-link">
                            <span>📰 Substack Newsletter</span>
                        </a>
                    </div>
                </div>
            </div>
        </section>

        <!-- USER ANALYTICS TAB -->
        <section id="tab-analytics" class="tab-content">
            <div class="grid-2col">
                <div class="card glass">
                    <div class="card-title">📈 Popular Actions / Commands</div>
                    <div id="analytics-stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 16px;">
                        <div class="no-data">No activity logged yet</div>
                    </div>
                </div>
                
                <div class="card glass">
                    <div class="card-title">👥 Active User Moderation (Click Row to View Clicks)</div>
                    <div class="table-container" style="max-height: 300px; overflow-y: auto;">
                        <table>
                            <thead>
                                <tr>
                                    <th>User</th>
                                    <th>ID</th>
                                    <th>Clicks</th>
                                    <th class="action-cell">Moderation Controls</th>
                                </tr>
                            </thead>
                            <tbody id="analytics-users-body">
                                <tr>
                                    <td colspan="4" class="no-data">Loading active users...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="card glass" style="margin-top: 24px;">
                <div class="card-title">⏱️ Live Command Click Stream</div>
                <div class="table-container" style="max-height: 400px; overflow-y: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>User ID</th>
                                <th>Action/Command Triggered</th>
                                <th>Timestamp</th>
                            </tr>
                        </thead>
                        <tbody id="analytics-activity-body">
                            <tr>
                                <td colspan="4" class="no-data">Loading live activity logs...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </section>

        <!-- FAQS TAB -->
        <section id="tab-faqs" class="tab-content">
            <div class="grid-2col">
                <div class="card glass">
                    <div class="card-header">
                        <div class="card-title">📚 Current FAQs</div>
                        <input type="text" id="faq-search" placeholder="Search keyword..." style="padding: 6px 12px; font-size: 14px;">
                    </div>
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Keyword</th>
                                    <th>Response Preview</th>
                                    <th class="action-cell">Actions</th>
                                </tr>
                            </thead>
                            <tbody id="faq-table-body">
                                <tr>
                                    <td colspan="3" class="no-data">Loading FAQs...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="card glass">
                    <div class="card-title" id="faq-editor-title">➕ Add Custom FAQ</div>
                    <form id="add-faq-form" style="display: flex; flex-direction: column; gap: 16px;">
                        <div class="form-group">
                            <label for="faq-keyword">Trigger Keyword / Phrase</label>
                            <input type="text" id="faq-keyword" placeholder="e.g. upload" required>
                        </div>
                        <div class="form-group">
                            <label for="faq-response">Automatic Response Text</label>
                            <textarea id="faq-response" rows="5" placeholder="Write your automated response message..." required></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary" style="align-self: flex-end;">Save FAQ Trigger</button>
                    </form>
                </div>
            </div>
        </section>

        <!-- SUGGESTIONS TAB -->
        <section id="tab-suggestions" class="tab-content">
            <div class="card glass">
                <div class="card-title">💡 User Topic Suggestions</div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Suggested Idea</th>
                                <th>Timestamp</th>
                            </tr>
                        </thead>
                        <tbody id="suggestions-table-body">
                            <tr>
                                <td colspan="3" class="no-data">Loading user suggestions...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </section>

        <!-- QUESTIONS TAB -->
        <section id="tab-questions" class="tab-content">
            <div class="card glass">
                <div class="card-title">❓ Recent User Questions</div>
                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Question Asked</th>
                                <th>Timestamp</th>
                            </tr>
                        </thead>
                        <tbody id="questions-table-body">
                            <tr>
                                <td colspan="3" class="no-data">Loading recent questions...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </section>

        <!-- GIVEAWAYS TAB -->
        <section id="tab-giveaways" class="tab-content">
            <div class="grid-2col">
                <div class="card glass">
                    <div class="card-title">⚙️ Giveaway Operations</div>
                    <div style="display: flex; flex-direction: column; gap: 20px;">
                        <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 12px; padding: 20px; text-align: center;">
                            <div style="font-size: 14px; color: var(--text-secondary); margin-bottom: 8px;">Current Registrations</div>
                            <div style="font-size: 48px; font-weight: 700; color: var(--success);" id="giveaway-active-entries">0</div>
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 8px;">Registered via the channel inline button</div>
                        </div>

                        <div style="display: flex; gap: 16px; justify-content: stretch;">
                            <button id="draw-winner-btn" onclick="drawWinner()" class="btn btn-primary" style="flex: 1; padding: 16px;">
                                👑 Draw Giveaway Winner
                            </button>
                        </div>
                    </div>
                </div>

                <div class="card glass">
                    <div class="card-title">🎁 Launch New Giveaway</div>
                    <form id="start-giveaway-form" style="display: flex; flex-direction: column; gap: 16px;">
                        <div class="form-group">
                            <label for="giveaway-prize">Giveaway Prize Name</label>
                            <input type="text" id="giveaway-prize" placeholder="e.g. Geopolitics eBook or Amazon Gift Card" required>
                        </div>
                        <p style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;">
                            Starting a new giveaway will instantly reset all existing entries in the database and broadcast the entry prompt in your channel.
                        </p>
                        <button type="submit" class="btn btn-primary" style="align-self: flex-end;">Post Giveaway Alert</button>
                    </form>
                </div>
            </div>
        </section>

        <!-- BROADCAST TAB -->
        <section id="tab-broadcast" class="tab-content">
            <div class="grid-2col">
                <div class="card glass">
                    <div class="card-title">📣 Send Channel Broadcast</div>
                    <form id="broadcast-form" style="display: flex; flex-direction: column; gap: 16px;">
                        <div class="form-group">
                            <label for="broadcast-msg">Broadcast Message</label>
                            <textarea id="broadcast-msg" rows="8" placeholder="Type your channel announcement here (supports HTML formatting)..." required></textarea>
                        </div>
                        <button type="submit" class="btn btn-primary" style="align-self: flex-end;">Send Broadcast Now</button>
                    </form>
                </div>

                <div class="card glass">
                    <div class="card-title">📊 Send Interactive Poll</div>
                    <form id="poll-form" style="display: flex; flex-direction: column; gap: 16px;">
                        <div class="form-group">
                            <label for="poll-question">Poll Question</label>
                            <input type="text" id="poll-question" placeholder="e.g. What topic should I cover next?" required>
                        </div>
                        <div class="form-group">
                            <label>Poll Options</label>
                            <div id="poll-options-container" style="display: flex; flex-direction: column; gap: 10px;">
                                <input type="text" class="poll-option-input" placeholder="Option 1" required>
                                <input type="text" class="poll-option-input" placeholder="Option 2" required>
                            </div>
                            <button type="button" onclick="addPollOption()" class="btn btn-secondary" style="font-size: 13px; padding: 6px 12px; align-self: flex-start; margin-top: 6px;">
                                ＋ Add Option
                            </button>
                        </div>
                        <button type="submit" class="btn btn-primary" style="align-self: flex-end; margin-top: 10px;">Post Poll to Channel</button>
                    </form>
                </div>
            </div>
        </section>

        <!-- LOGS TAB -->
        <section id="tab-logs" class="tab-content">
            <div class="console-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div style="width: 10px; height: 10px; border-radius: 50%; background-color: var(--primary);"></div>
                    <span style="font-weight: 600; font-size: 14px;">BB Bot HUB Console</span>
                </div>
                <button onclick="copyLogs()" class="btn btn-secondary" style="padding: 6px 12px; font-size: 13px;">Copy Session Logs</button>
            </div>
            <div class="console" id="console-display">
                <div class="console-line info"><span class="ts">00:00:00</span> [system] Initializing console display stream...</div>
            </div>
        </section>
    </main>

    <!-- JS Logic -->
    <script>
        // Tab switching
        const navItems = document.querySelectorAll('.nav-item');
        const tabContents = document.querySelectorAll('.tab-content');
        const pageTitle = document.getElementById('page-title');

        navItems.forEach(item => {
            item.addEventListener('click', () => {
                const tabId = item.getAttribute('data-tab');
                switchTab(tabId);
            });
        });

        function switchTab(tabId) {
            navItems.forEach(i => i.classList.remove('active'));
            document.querySelector(`[data-tab="${tabId}"]`).classList.add('active');

            tabContents.forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`tab-${tabId}`).classList.add('active');
            
            pageTitle.innerText = tabId.charAt(0).toUpperCase() + tabId.slice(1);
            
            if (tabId === 'faqs') refreshFAQs();
            if (tabId === 'suggestions') refreshSuggestions();
            if (tabId === 'questions') refreshQuestions();
            if (tabId === 'analytics') refreshAnalytics();
            if (tabId === 'logs') refreshLogs();
        }

        // Authentication logic
        const loginOverlay = document.getElementById('login-overlay');
        const passwordInput = document.getElementById('password-input');
        const loginBtn = document.getElementById('login-btn');
        const loginError = document.getElementById('login-error');
        const logoutBtn = document.getElementById('logout-btn');

        loginBtn.addEventListener('click', handleLogin);
        passwordInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleLogin();
        });

        async function handleLogin() {
            const password = passwordInput.value;
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                const res = await response.json();
                if (response.status === 200) {
                    localStorage.setItem('dashboard_password', password);
                    loginOverlay.style.display = 'none';
                    showToast('Logged in successfully', 'success');
                    refreshAll();
                    startPoller();
                } else {
                    loginError.style.display = 'block';
                    passwordInput.value = '';
                }
            } catch (err) {
                console.error(err);
                loginError.innerText = 'Network error. Please try again.';
                loginError.style.display = 'block';
            }
        }

        logoutBtn.addEventListener('click', () => {
            localStorage.removeItem('dashboard_password');
            loginOverlay.style.display = 'flex';
            passwordInput.value = '';
            loginError.style.display = 'none';
            stopPoller();
        });

        window.addEventListener('DOMContentLoaded', () => {
            const savedPassword = localStorage.getItem('dashboard_password');
            if (savedPassword) {
                loginOverlay.style.display = 'none';
                refreshAll();
                startPoller();
            } else {
                loginOverlay.style.display = 'flex';
            }
        });

        // Universal fetch handler
        async function fetchAPI(endpoint, method = 'GET', body = null) {
            const token = localStorage.getItem('dashboard_password') || '';
            const options = {
                method,
                headers: {
                    'Authorization': token,
                    'Content-Type': 'application/json'
                }
            };
            if (body) {
                options.body = JSON.stringify(body);
            }
            try {
                const response = await fetch(endpoint, options);
                if (response.status === 401) {
                    localStorage.removeItem('dashboard_password');
                    loginOverlay.style.display = 'flex';
                    showToast('Session expired or invalid token', 'error');
                    return null;
                }
                return await response.json();
            } catch (err) {
                console.error(err);
                showToast('Failed to connect to server', 'error');
                return null;
            }
        }

        function showToast(message, type = 'success') {
            const toast = document.getElementById('toast');
            toast.innerText = (type === 'success' ? '✅ ' : '❌ ') + message;
            toast.className = `toast ${type}`;
            toast.style.display = 'flex';
            
            setTimeout(() => {
                toast.style.display = 'none';
            }, 3000);
        }

        // Refresh stats (including latency heartbeat)
        async function refreshStats() {
            const data = await fetchAPI('/api/stats');
            if (!data) return;

            document.getElementById('stat-uptime').innerText = data.uptime;
            document.getElementById('stat-faqs').innerText = data.faqs_count;
            document.getElementById('stat-questions').innerText = data.questions_count;
            document.getElementById('stat-suggestions').innerText = data.suggestions_count;
            document.getElementById('stat-giveaway').innerText = data.giveaway_count;
            document.getElementById('giveaway-active-entries').innerText = data.giveaway_count;

            // Heartbeat monitor update
            const heartbeatVal = document.getElementById('stat-heartbeat');
            const heartbeatPulse = document.getElementById('heartbeat-pulse');
            const heartbeatDesc = document.getElementById('stat-heartbeat-desc');

            if (data.ping_history && data.ping_history.length > 0) {
                const lastPing = data.ping_history[data.ping_history.length - 1];
                heartbeatVal.innerText = `${lastPing.latency} ms`;
                heartbeatVal.style.color = lastPing.status === 200 ? 'var(--success)' : 'var(--error)';
                
                heartbeatPulse.style.backgroundColor = lastPing.status === 200 ? 'var(--success)' : 'var(--error)';
                heartbeatPulse.style.boxShadow = lastPing.status === 200 ? '0 0 10px var(--success-glow)' : '0 0 10px rgba(239, 68, 68, 0.4)';
                
                // Construct log history tooltip
                const pingsList = data.ping_history.slice().reverse().map(p => `${p.timestamp}: ${p.status} (${p.latency}ms)`).join(' | ');
                heartbeatDesc.innerText = pingsList;
            } else {
                heartbeatVal.innerText = 'No Pings';
                heartbeatVal.style.color = 'var(--text-secondary)';
                heartbeatPulse.style.backgroundColor = 'var(--text-secondary)';
                heartbeatPulse.style.boxShadow = 'none';
                heartbeatDesc.innerText = 'Self-ping pinger active';
            }

            document.getElementById('channel-id-text').innerText = data.channel_id || 'Not Set';
            if (data.channel_id) {
                document.getElementById('channel-link-display').href = `https://t.me/${data.channel_id.replace('-100', '')}`;
            }
        }

        // Manual RSS sync action
        async function syncRSS() {
            const syncBtn = document.getElementById('rss-sync-btn');
            syncBtn.disabled = true;
            syncBtn.innerText = 'Checking feeds...';
            
            const res = await fetchAPI('/api/rss/sync', 'POST');
            syncBtn.disabled = false;
            syncBtn.innerText = 'Sync Content Platforms';
            
            if (res && res.status === 'success') {
                showToast(`Manual Sync Complete! Sent ${res.posts_sent} update posts.`, 'success');
                refreshStats();
            } else if (res && res.error) {
                showToast(res.error, 'error');
            }
        }

        // Refresh Analytics tab data
        async function refreshAnalytics() {
            // 1. Fetch activity stream
            const activity = await fetchAPI('/api/analytics/activity');
            const activityBody = document.getElementById('analytics-activity-body');
            activityBody.innerHTML = '';
            
            if (!activity || activity.length === 0) {
                activityBody.innerHTML = '<tr><td colspan="4" class="no-data">No command clicks recorded yet</td></tr>';
            } else {
                activity.forEach(act => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td><strong>${escapeHTML(act.username)}</strong></td>
                        <td style="color: var(--text-secondary); font-size: 13px;">${escapeHTML(act.user_id)}</td>
                        <td><span style="padding: 4px 8px; border-radius: 6px; font-size: 13px; font-weight: 600; background: rgba(59,130,246,0.1); color: var(--primary);">${escapeHTML(act.command)}</span></td>
                        <td style="color: var(--text-secondary); font-size: 13px;">${escapeHTML(act.timestamp)}</td>
                    `;
                    activityBody.appendChild(tr);
                });
            }

            // 2. Fetch active users list with moderation options
            const users = await fetchAPI('/api/analytics/users');
            const usersBody = document.getElementById('analytics-users-body');
            usersBody.innerHTML = '';
            
            const cmdPopularity = {};

            if (!users || users.length === 0) {
                usersBody.innerHTML = '<tr><td colspan="4" class="no-data">No active users recorded</td></tr>';
            } else {
                users.forEach(u => {
                    const tr = document.createElement('tr');
                    tr.style.cursor = 'pointer';
                    tr.onclick = () => showUserDetails(u);
                    tr.innerHTML = `
                        <td><strong>${escapeHTML(u.username)}</strong></td>
                        <td style="color: var(--text-secondary); font-size: 13px;">${escapeHTML(u.user_id)}</td>
                        <td><span style="font-weight: 700; color: var(--purple);">${escapeHTML(u.total_clicks)}</span></td>
                        <td class="action-cell" onclick="event.stopPropagation()">
                            <button class="btn btn-secondary" onclick="muteUser('${escapeJS(u.user_id)}')" style="padding: 4px 8px; font-size: 12px; font-weight: 600; margin-right: 6px;">Mute 🔇</button>
                            <button class="btn btn-secondary" onclick="unmuteUser('${escapeJS(u.user_id)}')" style="padding: 4px 8px; font-size: 12px; font-weight: 600; color: var(--success); margin-right: 6px;">Unmute 🔊</button>
                            <button class="btn btn-danger" onclick="banUser('${escapeJS(u.user_id)}')" style="padding: 4px 8px; font-size: 12px; font-weight: 600;">Ban 🔨</button>
                        </td>
                    `;
                    usersBody.appendChild(tr);

                    if (u.commands) {
                        Object.keys(u.commands).forEach(cmd => {
                            cmdPopularity[cmd] = (cmdPopularity[cmd] || 0) + u.commands[cmd];
                        });
                    }
                });
            }

            // 3. Render popularity metrics
            const statsGrid = document.getElementById('analytics-stats-grid');
            statsGrid.innerHTML = '';
            
            const popularCmds = Object.keys(cmdPopularity);
            if (popularCmds.length === 0) {
                statsGrid.innerHTML = '<div class="no-data">No action stats recorded yet</div>';
            } else {
                popularCmds.sort((a,b) => cmdPopularity[b] - cmdPopularity[a]).forEach(cmd => {
                    const card = document.createElement('div');
                    card.style.background = 'rgba(255, 255, 255, 0.03)';
                    card.style.border = '1px solid var(--border-color)';
                    card.style.borderRadius = '10px';
                    card.style.padding = '12px 16px';
                    card.style.textAlign = 'center';
                    card.innerHTML = `
                        <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 4px; text-transform: uppercase;">/${escapeHTML(cmd)}</div>
                        <div style="font-size: 20px; font-weight: 700; color: var(--primary);">${escapeHTML(cmdPopularity[cmd])}</div>
                    `;
                    statsGrid.appendChild(card);
                });
            }
        }

        // Moderation Operations
        async function muteUser(userId) {
            if (!confirm(`Mute user ID ${userId} in the configured Telegram group?`)) return;
            const res = await fetchAPI('/api/moderation/mute', 'POST', { user_id: userId });
            if (res && res.status === 'success') {
                showToast(`User ${userId} has been restricted`, 'success');
            } else if (res && res.error) {
                showToast(res.error, 'error');
            }
        }

        async function unmuteUser(userId) {
            const res = await fetchAPI('/api/moderation/unmute', 'POST', { user_id: userId });
            if (res && res.status === 'success') {
                showToast(`User ${userId} restrictions removed`, 'success');
            } else if (res && res.error) {
                showToast(res.error, 'error');
            }
        }

        async function banUser(userId) {
            if (!confirm(`Permanently ban user ID ${userId} from the configured Telegram group?`)) return;
            const res = await fetchAPI('/api/moderation/ban', 'POST', { user_id: userId });
            if (res && res.status === 'success') {
                showToast(`User ${userId} banned successfully`, 'success');
            } else if (res && res.error) {
                showToast(res.error, 'error');
            }
        }

        // User Click Details Modal
        function showUserDetails(u) {
            document.getElementById('user-modal-name').innerText = u.username;
            document.getElementById('user-modal-id').innerText = u.user_id;
            document.getElementById('user-modal-active').innerText = u.last_active || 'N/A';
            
            const cmdList = document.getElementById('user-modal-commands');
            cmdList.innerHTML = '';
            
            if (!u.commands || Object.keys(u.commands).length === 0) {
                cmdList.innerHTML = '<div style="color: var(--text-secondary); font-style: italic;">No click telemetry logs.</div>';
            } else {
                Object.keys(u.commands).forEach(cmd => {
                    const row = document.createElement('div');
                    row.style.display = 'flex';
                    row.style.justifyContent = 'space-between';
                    row.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
                    row.style.padding = '6px 0';
                    row.innerHTML = `
                        <span style="font-family: monospace; color: var(--text-secondary);">/${escapeHTML(cmd)}</span>
                        <strong style="color: var(--primary);">${escapeHTML(u.commands[cmd])}</strong>
                    `;
                    cmdList.appendChild(row);
                });
            }
            
            document.getElementById('user-modal').style.display = 'flex';
        }

        function closeUserModal() {
            document.getElementById('user-modal').style.display = 'none';
        }

        // Refresh FAQ list
        let allFAQs = {};
        async function refreshFAQs() {
            const data = await fetchAPI('/api/faqs');
            if (!data) return;
            allFAQs = data;
            renderFAQs(document.getElementById('faq-search').value);
        }

        function renderFAQs(query = '') {
            const tbody = document.getElementById('faq-table-body');
            tbody.innerHTML = '';
            
            const filtered = Object.keys(allFAQs).filter(k => k.includes(query.toLowerCase()));
            
            if (filtered.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="no-data">No FAQs match search query</td></tr>';
                return;
            }

            filtered.forEach(k => {
                const tr = document.createElement('tr');
                const tdKey = document.createElement('td');
                tdKey.innerHTML = `<strong>${escapeHTML(k)}</strong>`;
                
                const tdVal = document.createElement('td');
                tdVal.innerText = allFAQs[k].substring(0, 80) + (allFAQs[k].length > 80 ? '...' : '');

                const tdAct = document.createElement('td');
                tdAct.className = 'action-cell';
                tdAct.innerHTML = `
                    <button class="icon-btn" onclick="editFAQ('${escapeJS(k)}')" title="Edit FAQ Response" style="color: var(--primary); margin-right: 8px;">
                        <svg viewBox="0 0 24 24" style="width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2;"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                    </button>
                    <button class="icon-btn" onclick="deleteFAQ('${escapeJS(k)}')" title="Delete FAQ Trigger">
                        <svg viewBox="0 0 24 24" style="width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; color: var(--error);"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                `;
                tr.appendChild(tdKey);
                tr.appendChild(tdVal);
                tr.appendChild(tdAct);
                tbody.appendChild(tr);
            });
        }

        // Edit FAQ
        function editFAQ(keyword) {
            const response = allFAQs[keyword];
            document.getElementById('faq-keyword').value = keyword;
            document.getElementById('faq-response').value = response;
            document.getElementById('faq-editor-title').innerText = `✏️ Edit FAQ Trigger`;
            
            document.getElementById('add-faq-form').scrollIntoView({ behavior: 'smooth' });
            showToast(`Loaded "/${keyword}" for editing`, 'success');
        }

        document.getElementById('faq-search').addEventListener('input', (e) => {
            renderFAQs(e.target.value);
        });

        // Add FAQ trigger submit
        document.getElementById('add-faq-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const keyword = document.getElementById('faq-keyword').value.trim().toLowerCase();
            const response = document.getElementById('faq-response').value.trim();
            
            const res = await fetchAPI('/api/faqs', 'POST', { keyword, response });
            if (res) {
                showToast(`Saved FAQ trigger: ${keyword}`, 'success');
                document.getElementById('add-faq-form').reset();
                document.getElementById('faq-editor-title').innerText = `➕ Add Custom FAQ`;
                refreshFAQs();
                refreshStats();
            }
        });

        async function deleteFAQ(keyword) {
            if (!confirm(`Are you sure you want to delete the FAQ trigger "${keyword}"?`)) return;
            const res = await fetchAPI(`/api/faqs?keyword=${encodeURIComponent(keyword)}`, 'DELETE');
            if (res) {
                showToast(`Deleted trigger: ${keyword}`, 'success');
                refreshFAQs();
                refreshStats();
            }
        }

        // Suggestions reload
        async function refreshSuggestions() {
            const data = await fetchAPI('/api/suggestions');
            const tbody = document.getElementById('suggestions-table-body');
            tbody.innerHTML = '';
            
            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="no-data">No topic suggestions found</td></tr>';
                return;
            }

            data.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${escapeHTML(item.username)}</strong></td>
                    <td>${escapeHTML(item.suggestion)}</td>
                    <td style="color: var(--text-secondary); font-size: 13px;">${escapeHTML(item.timestamp)}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        // Questions reload
        async function refreshQuestions() {
            const data = await fetchAPI('/api/questions');
            const tbody = document.getElementById('questions-table-body');
            tbody.innerHTML = '';
            
            if (!data || data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3" class="no-data">No recorded questions found</td></tr>';
                return;
            }

            data.forEach(item => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${escapeHTML(item.username)}</strong></td>
                    <td>${escapeHTML(item.question)}</td>
                    <td style="color: var(--text-secondary); font-size: 13px;">${escapeHTML(item.timestamp)}</td>
                `;
                tbody.appendChild(tr);
            });
        }

        // Broadcaster & Poll
        document.getElementById('broadcast-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const message = document.getElementById('broadcast-msg').value;
            const res = await fetchAPI('/api/broadcast', 'POST', { message });
            if (res) {
                showToast('Broadcast sent successfully to channel!', 'success');
                document.getElementById('broadcast-msg').value = '';
            }
        });

        function addPollOption() {
            const container = document.getElementById('poll-options-container');
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'poll-option-input';
            input.placeholder = `Option ${container.children.length + 1}`;
            input.required = true;
            container.appendChild(input);
        }

        document.getElementById('poll-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const question = document.getElementById('poll-question').value;
            const optionInputs = document.querySelectorAll('.poll-option-input');
            const options = Array.from(optionInputs).map(opt => opt.value.trim()).filter(val => val !== '');
            
            if (options.length < 2) {
                showToast('Please add at least 2 options', 'error');
                return;
            }

            const res = await fetchAPI('/api/poll', 'POST', { question, options });
            if (res) {
                showToast('Interactive poll sent to channel!', 'success');
                document.getElementById('poll-form').reset();
                const container = document.getElementById('poll-options-container');
                container.innerHTML = `
                    <input type="text" class="poll-option-input" placeholder="Option 1" required>
                    <input type="text" class="poll-option-input" placeholder="Option 2" required>
                `;
            }
        });

        // Giveaway launch
        document.getElementById('start-giveaway-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const prize = document.getElementById('giveaway-prize').value;
            const res = await fetchAPI('/api/giveaway/start', 'POST', { prize });
            if (res) {
                showToast(`Giveaway posted for: ${prize}`, 'success');
                document.getElementById('start-giveaway-form').reset();
                refreshStats();
            }
        });

        async function drawWinner() {
            const drawBtn = document.getElementById('draw-winner-btn');
            drawBtn.disabled = true;
            drawBtn.innerText = 'Selecting winner...';
            
            const res = await fetchAPI('/api/giveaway/pick', 'POST');
            drawBtn.disabled = false;
            drawBtn.innerText = '👑 Draw Giveaway Winner';
            
            if (res && res.winner_name) {
                document.getElementById('winner-display-name').innerText = res.winner_name;
                document.getElementById('winner-display-id').innerText = `Telegram UID: ${res.winner_id}`;
                document.getElementById('winner-modal').style.display = 'flex';
                refreshStats();
            } else if (res && res.error) {
                showToast(res.error, 'error');
            }
        }

        // Live logs console
        let lastLogCount = 0;
        async function refreshLogs() {
            const data = await fetchAPI('/api/logs');
            if (!data) return;
            
            const display = document.getElementById('console-display');
            display.innerHTML = '';
            
            data.forEach(log => {
                const div = document.createElement('div');
                div.className = `console-line ${log.level}`;
                div.innerHTML = `<span class="ts">${log.timestamp}</span> [${escapeHTML(log.logger.toLowerCase())}] ${escapeHTML(log.message)}`;
                display.appendChild(div);
            });
            
            display.scrollTop = display.scrollHeight;
        }

        function copyLogs() {
            const lines = Array.from(document.querySelectorAll('.console-line')).map(l => l.innerText);
            navigator.clipboard.writeText(lines.join('\\n')).then(() => {
                showToast('Logs copied to clipboard', 'success');
            });
        }

        // Sync triggers
        function refreshAll() {
            refreshStats();
            const activeTab = document.querySelector('.nav-item.active').getAttribute('data-tab');
            if (activeTab === 'faqs') refreshFAQs();
            if (activeTab === 'suggestions') refreshSuggestions();
            if (activeTab === 'questions') refreshQuestions();
            if (activeTab === 'analytics') refreshAnalytics();
            if (activeTab === 'logs') refreshLogs();
        }

        // Background poller
        let pollerId = null;
        function startPoller() {
            if (pollerId) return;
            pollerId = setInterval(() => {
                refreshStats();
                const activeTab = document.querySelector('.nav-item.active').getAttribute('data-tab');
                if (activeTab === 'logs') refreshLogs();
                if (activeTab === 'analytics') refreshAnalytics();
            }, 3000);
        }

        function stopPoller() {
            if (pollerId) {
                clearInterval(pollerId);
                pollerId = null;
            }
        }

        // Escaping utilities
        function escapeHTML(str) {
            if (!str) return '';
            return str.toString()
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        function escapeJS(str) {
            if (!str) return '';
            return str.toString()
                .replace(/\\\\/g, '\\\\\\\\')
                .replace(/'/g, "\\\\'")
                .replace(/"/g, '\\\\"')
                .replace(/\\n/g, '\\\\n')
                .replace(/\\r/g, '\\\\r');
        }

        function closeWinnerModal() {
            document.getElementById('winner-modal').style.display = 'none';
        }
    </script>
</body>
</html>"""

class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging HTTP requests in standard console
        pass

    def check_auth(self):
        auth_header = self.headers.get('Authorization')
        if not auth_header:
            return False
        return auth_header == DASHBOARD_PASSWORD

    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        if path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode('utf-8'))
            return

        # Authenticate all API endpoints
        if not self.check_auth():
            self.send_json(401, {"error": "Unauthorized"})
            return

        if path == '/api/stats':
            uptime_seconds = int(time.time() - START_TIME)
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            q_count, s_count, g_count = 0, 0, 0
            if db:
                try:
                    q_count = len(list(db.collection("questions").stream()))
                    s_count = len(list(db.collection("suggestions").stream()))
                    g_count = len(list(db.collection("giveaway_entries").stream()))
                except Exception as e:
                    logger.error(f"Error fetching stats: {e}")

            self.send_json(200, {
                "uptime": uptime_str,
                "faqs_count": len(FAQ),
                "questions_count": q_count,
                "suggestions_count": s_count,
                "giveaway_count": g_count,
                "channel_id": CHANNEL_ID,
                "ping_history": list(ping_history)
            })

        elif path == '/api/faqs':
            self.send_json(200, FAQ)

        elif path == '/api/suggestions':
            suggestions = []
            if db:
                try:
                    docs = db.collection("suggestions").order_by("timestamp", direction="DESCENDING").limit(50).stream()
                    for doc in docs:
                        d = doc.to_dict()
                        ts = d.get("timestamp")
                        ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else "N/A"
                        suggestions.append({
                            "username": d.get("username", "Unknown"),
                            "suggestion": d.get("suggestion", ""),
                            "timestamp": ts_str
                        })
                except Exception as e:
                    logger.error(f"Error fetching suggestions: {e}")
            self.send_json(200, suggestions)

        elif path == '/api/questions':
            questions = []
            if db:
                try:
                    docs = db.collection("questions").order_by("timestamp", direction="DESCENDING").limit(50).stream()
                    for doc in docs:
                        d = doc.to_dict()
                        ts = d.get("timestamp")
                        ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else "N/A"
                        questions.append({
                            "username": d.get("username", "Unknown"),
                            "question": d.get("question", ""),
                            "timestamp": ts_str
                        })
                except Exception as e:
                    logger.error(f"Error fetching questions: {e}")
            self.send_json(200, questions)

        elif path == '/api/analytics/activity':
            activity = []
            if db:
                try:
                    docs = db.collection("activity_logs").order_by("timestamp", direction="DESCENDING").limit(50).stream()
                    for doc in docs:
                        d = doc.to_dict()
                        ts = d.get("timestamp")
                        ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else "N/A"
                        activity.append({
                            "user_id": d.get("user_id", "N/A"),
                            "username": d.get("username", "Unknown"),
                            "command": d.get("command", "N/A"),
                            "timestamp": ts_str
                        })
                except Exception as e:
                    logger.error(f"Error fetching activity logs: {e}")
            self.send_json(200, activity)

        elif path == '/api/analytics/users':
            users_list = []
            if db:
                try:
                    docs = db.collection("users").order_by("total_clicks", direction="DESCENDING").limit(50).stream()
                    for doc in docs:
                        d = doc.to_dict()
                        ts = d.get("last_active")
                        ts_str = ts.strftime('%Y-%m-%d %H:%M:%S') if ts else "N/A"
                        users_list.append({
                            "user_id": doc.id,
                            "username": d.get("username", "Unknown"),
                            "last_active": ts_str,
                            "total_clicks": d.get("total_clicks", 0),
                            "commands": d.get("commands", {})
                        })
                except Exception as e:
                    logger.error(f"Error fetching top users: {e}")
            self.send_json(200, users_list)

        elif path == '/api/logs':
            self.send_json(200, list(memory_log_handler.logs))

        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        # Read JSON body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        data = {}
        if body:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_json(400, {"error": "Invalid JSON"})
                return

        # Special check for login endpoint which doesn't require auth header
        if path == '/api/login':
            password = data.get("password")
            if password == DASHBOARD_PASSWORD:
                self.send_json(200, {"status": "success"})
            else:
                self.send_json(401, {"error": "Invalid password"})
            return

        # Authenticate all other POST endpoints
        if not self.check_auth():
            self.send_json(401, {"error": "Unauthorized"})
            return

        if path == '/api/faqs':
            keyword = data.get("keyword", "").strip().lower()
            response = data.get("response", "").strip()
            if not keyword or not response:
                self.send_json(400, {"error": "Keyword and response are required"})
                return
            save_faq(keyword, response)
            self.send_json(200, {"status": "success"})

        elif path == '/api/rss/sync':
            try:
                posts_sent = check_and_sync_rss_manually()
                self.send_json(200, {"status": "success", "posts_sent": posts_sent})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == '/api/moderation/ban':
            user_id = data.get("user_id")
            if not user_id:
                self.send_json(400, {"error": "User ID is required"})
                return
            if not GROUP_ID:
                self.send_json(400, {"error": "GROUP_ID not configured"})
                return
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/banChatMember"
                res = requests.post(url, json={
                    "chat_id": GROUP_ID,
                    "user_id": user_id
                }, timeout=10)
                if res.status_code == 200:
                    self.send_json(200, {"status": "success"})
                else:
                    self.send_json(500, {"error": f"Telegram API error: {res.text}"})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == '/api/moderation/mute':
            user_id = data.get("user_id")
            if not user_id:
                self.send_json(400, {"error": "User ID is required"})
                return
            if not GROUP_ID:
                self.send_json(400, {"error": "GROUP_ID not configured"})
                return
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/restrictChatMember"
                res = requests.post(url, json={
                    "chat_id": GROUP_ID,
                    "user_id": user_id,
                    "permissions": {"can_send_messages": False}
                }, timeout=10)
                if res.status_code == 200:
                    self.send_json(200, {"status": "success"})
                else:
                    self.send_json(500, {"error": f"Telegram API error: {res.text}"})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == '/api/moderation/unmute':
            user_id = data.get("user_id")
            if not user_id:
                self.send_json(400, {"error": "User ID is required"})
                return
            if not GROUP_ID:
                self.send_json(400, {"error": "GROUP_ID not configured"})
                return
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/restrictChatMember"
                res = requests.post(url, json={
                    "chat_id": GROUP_ID,
                    "user_id": user_id,
                    "permissions": {
                        "can_send_messages": True,
                        "can_send_media_messages": True,
                        "can_send_polls": True,
                        "can_send_other_messages": True,
                        "can_add_web_page_previews": True,
                        "can_invite_users": True
                    }
                }, timeout=10)
                if res.status_code == 200:
                    self.send_json(200, {"status": "success"})
                else:
                    self.send_json(500, {"error": f"Telegram API error: {res.text}"})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == '/api/broadcast':
            msg = data.get("message", "").strip()
            if not msg:
                self.send_json(400, {"error": "Message is required"})
                return
            if not TELEGRAM_TOKEN or not CHANNEL_ID:
                self.send_json(500, {"error": "Bot credentials or channel not configured"})
                return

            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                res = requests.post(url, json={
                    "chat_id": CHANNEL_ID,
                    "text": msg,
                    "parse_mode": "HTML"
                }, timeout=10)
                if res.status_code == 200:
                    self.send_json(200, {"status": "success"})
                else:
                    self.send_json(500, {"error": f"Telegram API error: {res.text}"})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == '/api/poll':
            question = data.get("question", "").strip()
            options = data.get("options", [])
            if not question or len(options) < 2:
                self.send_json(400, {"error": "Question and at least 2 options are required"})
                return
            if not TELEGRAM_TOKEN or not CHANNEL_ID:
                self.send_json(500, {"error": "Bot credentials or channel not configured"})
                return

            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
                res = requests.post(url, json={
                    "chat_id": CHANNEL_ID,
                    "question": question,
                    "options": options,
                    "is_anonymous": True
                }, timeout=10)
                if res.status_code == 200:
                    self.send_json(200, {"status": "success"})
                else:
                    self.send_json(500, {"error": f"Telegram API error: {res.text}"})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == '/api/giveaway/start':
            prize = data.get("prize", "").strip()
            if not prize:
                self.send_json(400, {"error": "Prize is required"})
                return
            if not TELEGRAM_TOKEN or not CHANNEL_ID:
                self.send_json(500, {"error": "Bot credentials or channel not configured"})
                return

            try:
                if db:
                    docs = db.collection("giveaway_entries").stream()
                    for doc in docs:
                        doc.reference.delete()

                message = (
                    f"🎁 <b>GIVEAWAY ALERT!</b> 🎁\n\n"
                    f"We are giving away: <b>{prize}</b>\n\n"
                    f"Click the button below to enter!"
                )
                reply_markup = {
                    "inline_keyboard": [[
                        {"text": "Enter Giveaway 🎉", "callback_data": "enter_giveaway"}
                    ]]
                }
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                res = requests.post(url, json={
                    "chat_id": CHANNEL_ID,
                    "text": message,
                    "parse_mode": "HTML",
                    "reply_markup": reply_markup
                }, timeout=10)
                
                if res.status_code == 200:
                    self.send_json(200, {"status": "success"})
                else:
                    self.send_json(500, {"error": f"Telegram API error: {res.text}"})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif path == '/api/giveaway/pick':
            if not db:
                self.send_json(500, {"error": "Firebase database not configured"})
                return

            try:
                import random
                docs = list(db.collection("giveaway_entries").stream())
                if not docs:
                    self.send_json(400, {"error": "No entries registered for the giveaway yet"})
                    return

                winner_doc = random.choice(docs)
                winner_data = winner_doc.to_dict()
                winner_name = winner_data.get('username', 'Unknown')
                winner_id = winner_data.get('user_id')

                announcement = (
                    f"🎊 <b>GIVEAWAY WINNER!</b> 🎊\n\n"
                    f"Congratulations <a href='tg://user?id={winner_id}'>{winner_name}</a>! You have won the giveaway!\n"
                    f"Please DM the admin to claim your prize."
                )

                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                res = requests.post(url, json={
                    "chat_id": CHANNEL_ID,
                    "text": announcement,
                    "parse_mode": "HTML"
                }, timeout=10)

                if res.status_code == 200:
                    self.send_json(200, {
                        "winner_name": winner_name,
                        "winner_id": winner_id
                    })
                else:
                    self.send_json(500, {"error": f"Telegram announcement failed: {res.text}"})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        else:
            self.send_json(404, {"error": "Endpoint not found"})

    def do_DELETE(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query = parse_qs(parsed_path.query)

        if not self.check_auth():
            self.send_json(401, {"error": "Unauthorized"})
            return

        if path == '/api/faqs':
            keywords = query.get("keyword")
            if not keywords or not keywords[0]:
                self.send_json(400, {"error": "Keyword parameter is required"})
                return
            keyword = keywords[0].lower()
            remove_faq(keyword)
            self.send_json(200, {"status": "success"})
        else:
            self.send_json(404, {"error": "Endpoint not found"})

def start_dummy_server():
    """Starts the HTTP dashboard server binding to PORT."""
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), DashboardHandler)
    logger.info(f"BB Bot HUB web server running on port {port}")
    server.serve_forever()

def start_server_threads():
    """Start the dashboard server and self pinger in background threads."""
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()
    
    logger.info("BB Bot HUB web server & self-pinger initialized successfully!")
