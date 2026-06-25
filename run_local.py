#!/usr/bin/env python3
"""
Local development runner - starts both bot and admin panel
"""
import subprocess
import sys
import threading
import time

def run_bot():
    """Run telegram bot"""
    print("Starting Telegram Bot...")
    subprocess.call([sys.executable, "main.py"])

def run_admin():
    """Run admin panel"""
    print("Starting Admin Panel on http://localhost:5000...")
    subprocess.call([sys.executable, "admin_panel.py"])

if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════╗
    ║  НШМ Резидент Бот - Local Development Mode   ║
    ╠═══════════════════════════════════════════════╣
    ║  Bot:   Running on Telegram                   ║
    ║  Admin: http://localhost:5000                 ║
    ║                                               ║
    ║  Press Ctrl+C to stop                         ║
    ╚═══════════════════════════════════════════════╝
    """)

    # Start bot in separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Give bot time to start
    time.sleep(2)

    # Start admin panel in main thread
    run_admin()
