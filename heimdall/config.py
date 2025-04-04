#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Configuration management module for Heimdall.

This module handles loading and managing both the main configuration
and server configurations.
"""

import json
import os
import logging

# Configuration files
SERVERS_FILE = "servers.json"
CONFIG_FILE = "config.json"

logger = logging.getLogger("Heimdall")

def load_config():
    """Load the main configuration file."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        else:
            # Create default config
            default_config = {
                "email": {
                    "enabled": False,
                    "smtp_server": "smtp.example.com",
                    "smtp_port": 587,
                    "use_tls": True,
                    "username": "user@example.com",
                    "password": "password",
                    "sender": "heimdall@example.com",
                    "recipients": ["admin@example.com"]
                },
                "thresholds": {
                    "cpu": 80,
                    "memory": 80,
                    "disk": 85
                },
                "check_interval": 300
            }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(default_config, f, indent=2)
            return default_config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        return None

class ServerConfig:
    def __init__(self):
        self.servers = []
        self.load_servers()
    
    def load_servers(self):
        """Load servers from the JSON file."""
        if os.path.exists(SERVERS_FILE):
            try:
                with open(SERVERS_FILE, 'r') as f:
                    data = json.load(f)
                    self.servers = data.get('servers', [])
                logger.info(f"Loaded {len(self.servers)} servers from configuration")
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {SERVERS_FILE}")
                self.servers = []
        else:
            # Create an empty servers file
            logger.info(f"Creating new servers file: {SERVERS_FILE}")
            self.save_servers()
    
    def save_servers(self):
        """Save servers to the JSON file."""
        data = {'servers': self.servers}
        with open(SERVERS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(self.servers)} servers to configuration")
    
    def add_server(self, server_data):
        """Add a new server to the configuration."""
        self.servers.append(server_data)
        self.save_servers()
        logger.info(f"Added new server: {server_data['nickname']} ({server_data['hostname']})")
    
    def remove_server(self, nickname):
        """Remove a server from the configuration."""
        for i, server in enumerate(self.servers):
            if server['nickname'] == nickname:
                del self.servers[i]
                self.save_servers()
                logger.info(f"Removed server: {nickname}")
                return True
        logger.warning(f"Server not found: {nickname}")
        return False
    
    def get_servers(self):
        """Get the list of configured servers."""
        return self.servers