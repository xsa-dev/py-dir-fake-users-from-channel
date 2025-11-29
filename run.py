#!/usr/bin/env python3
"""
Simple entry point for the Telegram Scanner application
"""

import sys
import os

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from telegram_scanner.main import main

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
