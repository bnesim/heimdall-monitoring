#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Utility functions and classes for Heimdall.

This module contains utility functions and classes used across the application,
including terminal colors and logging setup.
"""

import os
import logging

# Log file location
LOG_FILE = "logs/heimdall.log"
ALERT_LOG_FILE = "logs/alerts.log"

def setup_logging():
    """Setup logging configuration for the application."""
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("Heimdall")

class Colors:
    """ANSI Colors for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'
    
    @classmethod
    def red(cls, text):
        return f"{cls.RED}{text}{cls.END}"
    
    @classmethod
    def green(cls, text):
        return f"{cls.GREEN}{text}{cls.END}"
    
    @classmethod
    def yellow(cls, text):
        return f"{cls.YELLOW}{text}{cls.END}"
    
    @classmethod
    def blue(cls, text):
        return f"{cls.BLUE}{text}{cls.END}"
    
    @classmethod
    def bold(cls, text):
        return f"{cls.BOLD}{text}{cls.END}"
