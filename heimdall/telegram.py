#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Telegram bot module for Heimdall.

This module handles Telegram bot functionality including subscriber management
and sending alerts via Telegram.
"""

import json
import logging
import requests
from datetime import datetime
import time
import threading

CONFIG_FILE = "config.json"
logger = logging.getLogger("Heimdall")

class TelegramBot:
    def __init__(self, config):
        self.config = config
        self.telegram_config = config.get('telegram', {})
        self.bot_token = self.telegram_config.get('bot_token', '')
        self.subscribers = self.telegram_config.get('subscribers', [])
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.polling_thread = None
        self.polling_active = False
        self.last_update_id = 0
        
    def is_configured(self):
        """Check if Telegram bot is properly configured."""
        return bool(self.bot_token) and self.telegram_config.get('enabled', False)
    
    def save_subscribers(self):
        """Save subscribers list to config file."""
        try:
            # Load current config
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            
            # Update telegram subscribers
            if 'telegram' not in config:
                config['telegram'] = {}
            config['telegram']['subscribers'] = self.subscribers
            
            # Save back to file
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
                
            logger.info(f"Saved {len(self.subscribers)} Telegram subscribers")
            return True
        except Exception as e:
            logger.error(f"Failed to save Telegram subscribers: {str(e)}")
            return False
    
    def add_subscriber(self, chat_id, username=None, first_name=None):
        """Add a new subscriber."""
        # Check if already subscribed
        for sub in self.subscribers:
            if sub['chat_id'] == chat_id:
                logger.info(f"User {chat_id} already subscribed")
                return False
        
        # Add new subscriber
        subscriber = {
            'chat_id': chat_id,
            'username': username,
            'first_name': first_name,
            'subscribed_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.subscribers.append(subscriber)
        self.save_subscribers()
        logger.info(f"Added new Telegram subscriber: {username or first_name or chat_id}")
        return True
    
    def remove_subscriber(self, chat_id):
        """Remove a subscriber."""
        for i, sub in enumerate(self.subscribers):
            if sub['chat_id'] == chat_id:
                removed = self.subscribers.pop(i)
                self.save_subscribers()
                logger.info(f"Removed Telegram subscriber: {removed.get('username', chat_id)}")
                return True
        return False
    
    def send_message(self, chat_id, text, parse_mode='HTML'):
        """Send a message to a specific chat."""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {chat_id}: {str(e)}")
            return False
    
    def send_alert_to_all(self, nickname, hostname, message, is_new_alert=True, open_alerts_text=""):
        """Send alert to all subscribers."""
        if not self.is_configured():
            return False
        
        # Format the alert message
        alert_type = "🚨 NEW ALERT" if is_new_alert else "⚠️ RECURRING ALERT"
        
        text = f"""<b>{alert_type}</b>

<b>Server:</b> {nickname}
<b>Hostname:</b> <code>{hostname}</code>
<b>Issue:</b> {message}

<b>Time:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}{open_alerts_text}

<i>This is an automated alert from Heimdall Monitoring System.</i>"""
        
        # Send to all subscribers
        sent_count = 0
        for subscriber in self.subscribers:
            if self.send_message(subscriber['chat_id'], text):
                sent_count += 1
        
        logger.info(f"Sent Telegram alert to {sent_count}/{len(self.subscribers)} subscribers")
        return sent_count > 0
    
    def send_resolution_to_all(self, nickname, hostname, metric, current_value, threshold, duration_str, open_alerts_text=""):
        """Send resolution notification to all subscribers."""
        if not self.is_configured():
            return False
        
        text = f"""<b>✅ ALERT RESOLVED</b>

<b>Server:</b> {nickname}
<b>Hostname:</b> <code>{hostname}</code>
<b>Metric:</b> {metric}

<b>Current Value:</b> {current_value:.1f}% (threshold: {threshold}%)
<b>Duration:</b> {duration_str}

<b>Resolved at:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

<i>The issue has been resolved. System is back to normal.</i>{open_alerts_text}"""
        
        # Send to all subscribers
        sent_count = 0
        for subscriber in self.subscribers:
            if self.send_message(subscriber['chat_id'], text):
                sent_count += 1
        
        logger.info(f"Sent Telegram resolution to {sent_count}/{len(self.subscribers)} subscribers")
        return sent_count > 0
    
    def process_update(self, update):
        """Process a single update from Telegram."""
        try:
            # Extract message data
            message = update.get('message', {})
            chat_id = message.get('chat', {}).get('id')
            text = message.get('text', '')
            from_user = message.get('from', {})
            username = from_user.get('username')
            first_name = from_user.get('first_name')
            
            if not chat_id or not text:
                return
            
            # Process commands
            if text.lower() == '/start' or text.lower() == '/subscribe':
                if self.add_subscriber(chat_id, username, first_name):
                    welcome_msg = """🎉 <b>Welcome to Heimdall Monitoring!</b>

You are now subscribed to server alerts. You will receive notifications when:
• Server resources (CPU, Memory, Disk) exceed thresholds
• Monitored services go down
• Issues are resolved

Available commands:
/status - Check your subscription status
/unsubscribe - Stop receiving alerts
/help - Show this help message"""
                    self.send_message(chat_id, welcome_msg)
                else:
                    self.send_message(chat_id, "You are already subscribed to Heimdall alerts! 👍")
            
            elif text.lower() == '/unsubscribe' or text.lower() == '/stop':
                if self.remove_subscriber(chat_id):
                    self.send_message(chat_id, "You have been unsubscribed from Heimdall alerts. Use /start to subscribe again.")
                else:
                    self.send_message(chat_id, "You are not currently subscribed.")
            
            elif text.lower() == '/status':
                # Find subscriber info
                subscriber = None
                for sub in self.subscribers:
                    if sub['chat_id'] == chat_id:
                        subscriber = sub
                        break
                
                if subscriber:
                    status_msg = f"""<b>Your Subscription Status</b>

✅ <b>Status:</b> Active
📅 <b>Subscribed since:</b> {subscriber.get('subscribed_at', 'Unknown')}
👥 <b>Total subscribers:</b> {len(self.subscribers)}"""
                    self.send_message(chat_id, status_msg)
                else:
                    self.send_message(chat_id, "❌ You are not subscribed. Use /start to subscribe.")
            
            elif text.lower() == '/help':
                help_msg = """<b>Heimdall Monitoring Bot Help</b>

Available commands:
/start or /subscribe - Subscribe to alerts
/status - Check your subscription status
/unsubscribe or /stop - Unsubscribe from alerts
/help - Show this help message

<i>Heimdall monitors your servers and sends alerts when issues are detected.</i>"""
                self.send_message(chat_id, help_msg)
            
            else:
                # Unknown command
                self.send_message(chat_id, "Unknown command. Use /help to see available commands.")
                
        except Exception as e:
            logger.error(f"Error processing Telegram update: {str(e)}")
    
    def poll_updates(self):
        """Poll for Telegram updates (for handling subscriptions)."""
        while self.polling_active:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {
                    'offset': self.last_update_id + 1,
                    'timeout': 30  # Long polling
                }
                response = requests.get(url, params=params, timeout=35)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('ok'):
                        updates = data.get('result', [])
                        for update in updates:
                            self.process_update(update)
                            self.last_update_id = update.get('update_id', self.last_update_id)
                
            except Exception as e:
                logger.error(f"Error polling Telegram updates: {str(e)}")
                time.sleep(5)  # Wait before retrying
    
    def start_polling(self):
        """Start polling for updates in a separate thread."""
        if not self.is_configured():
            logger.warning("Telegram bot not configured, skipping polling")
            return False
        
        if self.polling_thread and self.polling_thread.is_alive():
            logger.warning("Telegram polling already active")
            return False
        
        self.polling_active = True
        self.polling_thread = threading.Thread(target=self.poll_updates, daemon=True)
        self.polling_thread.start()
        logger.info("Started Telegram bot polling")
        return True
    
    def stop_polling(self):
        """Stop polling for updates."""
        self.polling_active = False
        if self.polling_thread:
            self.polling_thread.join(timeout=5)
        logger.info("Stopped Telegram bot polling")
    
    def test_connection(self):
        """Test the bot connection by getting bot info."""
        try:
            url = f"{self.base_url}/getMe"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('ok'):
                bot_info = data.get('result', {})
                logger.info(f"Telegram bot connected: @{bot_info.get('username', 'Unknown')}")
                return True, bot_info
            else:
                return False, "Invalid response from Telegram API"
        except Exception as e:
            return False, str(e)