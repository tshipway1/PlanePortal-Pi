#!/usr/bin/env python3
"""PlanePortal Pi — entry point.

Starts the Flask dashboard on port 5000 (or $PORT).
"""

import os
from dotenv import load_dotenv

# Load .env before anything else reads config
load_dotenv()

from app.server import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("PLANEPORTAL_DEBUG", "0").lower() in ("1", "true", "yes")
    # Use 0.0.0.0 so the dashboard is accessible from other devices on the network
    app.run(host="0.0.0.0", port=port, debug=debug)
