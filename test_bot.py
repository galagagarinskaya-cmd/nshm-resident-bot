#!/usr/bin/env python3
"""
Test script to verify bot setup and Google Sheets connection
"""
import sys
import os

print("=" * 60)
print("НШМ Бот - Setup Verification")
print("=" * 60)

# 1. Check Python version
print("\n✓ Python version:", sys.version.split()[0])

# 2. Check required files
print("\n📁 Checking files...")
required_files = [
    ".env",
    "credentials.json",
    "config.py",
    "database.py",
    "sheets_service.py",
    "main.py",
    "admin_panel.py"
]

missing = []
for f in required_files:
    if os.path.exists(f):
        print(f"  ✓ {f}")
    else:
        print(f"  ✗ {f} - MISSING")
        missing.append(f)

if missing:
    print(f"\n❌ Missing files: {', '.join(missing)}")
    sys.exit(1)

# 3. Check environment variables
print("\n🔐 Checking environment variables...")
from dotenv import load_dotenv
load_dotenv()

required_env = [
    "TELEGRAM_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_ADMIN_IDS"
]

for env in required_env:
    value = os.getenv(env)
    if value:
        masked = value[:10] + "..." if len(value) > 10 else value
        print(f"  ✓ {env}: {masked}")
    else:
        print(f"  ✗ {env} - NOT SET")

# 4. Test imports
print("\n📦 Testing imports...")
try:
    from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, SHEETS_ID
    print("  ✓ config.py")
except ImportError as e:
    print(f"  ✗ config.py: {e}")

try:
    from database import Database
    db = Database()
    print("  ✓ database.py")
except Exception as e:
    print(f"  ✗ database.py: {e}")

try:
    from sheets_service import SheetsService
    sheets = SheetsService("credentials.json")
    print("  ✓ sheets_service.py")
except Exception as e:
    print(f"  ✗ sheets_service.py: {e}")

# 5. Test Google Sheets connection
print("\n🔗 Testing Google Sheets connection...")
try:
    from sheets_service import SheetsService
    sheets = SheetsService("credentials.json")
    if sheets.service:
        rules = sheets.get_rules()
        content = sheets.get_content()
        print(f"  ✓ Connected to Sheets")
        print(f"    - Loaded {len(rules)} rule blocks")
        print(f"    - Loaded {len(content)} content items")
    else:
        print("  ⚠ Google Sheets service not initialized")
except Exception as e:
    print(f"  ⚠ Google Sheets connection: {e}")

# 6. Test database
print("\n💾 Testing database...")
try:
    from database import Database
    db = Database()
    print("  ✓ Database initialized")
    print(f"    - Database file: {db.db_path}")
except Exception as e:
    print(f"  ✗ Database: {e}")

print("\n" + "=" * 60)
print("✅ Setup verification complete!")
print("=" * 60)
print("\nNext steps:")
print("1. Start the bot: python main.py")
print("2. Open admin panel: python admin_panel.py (in another terminal)")
print("3. Send /start to bot in Telegram")
print("\nDocumentation:")
print("- README.md - Installation and usage")
print("- SHEETS_SETUP.md - Google Sheets configuration")
print("- DEPLOYMENT.md - Railway deployment guide")
