#!/usr/bin/env python3
"""Run only Flask admin panel (for Railway admin service)"""

import os
from admin_panel import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    print(f"🎛️ Starting Admin Panel on {host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)
