#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Alert management module for Heimdall.

This module handles alert generation, tracking, and email notifications.
"""

import os
import json
import hashlib
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Alert status file
ALERT_STATUS_FILE = "alert_status.json"

# Alert rate limiting (in hours)
# ALERT_COOLDOWN constant is replaced with a configurable parameter

logger = logging.getLogger("Heimdall")

class AlertManager:
    def __init__(self, config):
        self.config = config
        self.alert_status = self.load_alert_status()
    
    def load_alert_status(self):
        """Load the alert status from file."""
        if os.path.exists(ALERT_STATUS_FILE):
            try:
                with open(ALERT_STATUS_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {ALERT_STATUS_FILE}")
                return {"active_alerts": {}, "resolved_alerts": {}}
        else:
            return {"active_alerts": {}, "resolved_alerts": {}}
    
    def save_alert_status(self):
        """Save the alert status to file."""
        with open(ALERT_STATUS_FILE, 'w') as f:
            json.dump(self.alert_status, f, indent=2)
    
    def get_alert_id(self, nickname, hostname, alert_type):
        """Generate a unique ID for an alert."""
        alert_string = f"{nickname}:{hostname}:{alert_type}"
        return hashlib.md5(alert_string.encode()).hexdigest()
    
    def send_alert(self, nickname, hostname, message, alert_type=None):
        """Send an alert email with rate limiting and resolution tracking."""
        # Extract alert type from message if not provided
        if not alert_type:
            alert_type = message.split()[0].lower()
        
        # Log to file
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("logs/alerts.log", "a") as log:
            log.write(f"[{timestamp}] {nickname} ({hostname}): {message}\n")
        
        logger.warning(f"Alert for {nickname} ({hostname}): {message}")
        
        # Generate alert ID and get current time
        alert_id = self.get_alert_id(nickname, hostname, alert_type)
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # Check if this is a new alert
        is_new_alert = alert_id not in self.alert_status["active_alerts"]
        is_recurring = alert_id in self.alert_status["resolved_alerts"]
        
        # Determine if we should send an email
        should_send_email = False
        
        if is_new_alert:
            # New alert, record and send email
            self.alert_status["active_alerts"][alert_id] = {
                "server": nickname,
                "hostname": hostname,
                "type": alert_type,
                "message": message,
                "first_detected": now_str,
                "last_detected": now_str,
                "last_notified": now_str
            }
            should_send_email = True
            
            # If it was previously resolved, move it from resolved to active
            if is_recurring:
                del self.alert_status["resolved_alerts"][alert_id]
        else:
            # Existing alert, update timestamp
            self.alert_status["active_alerts"][alert_id]["last_detected"] = now_str
            
            # Check if we should send another notification (rate limiting)
            last_notified = datetime.strptime(
                self.alert_status["active_alerts"][alert_id]["last_notified"],
                "%Y-%m-%d %H:%M:%S"
            )
            
            hours_since_last_notification = (now - last_notified).total_seconds() / 3600
            
            # Use the configurable alert_cooldown from config instead of hardcoded constant
            alert_cooldown = self.config.get('alert_cooldown', 1)  # Default to 1 hour if not configured
            
            if hours_since_last_notification >= alert_cooldown:
                should_send_email = True
                self.alert_status["active_alerts"][alert_id]["last_notified"] = now_str
        
        # Save updated alert status
        self.save_alert_status()
        
        # Send email if enabled and needed
        if self.config and self.config.get('email', {}).get('enabled', False) and should_send_email:
            self._send_email_alert(nickname, hostname, message, is_new_alert)
    
    def check_alert_resolution(self, nickname, hostname, metric, current_value, threshold):
        """Check if an alert has been resolved."""
        alert_id = self.get_alert_id(nickname, hostname, metric.lower())
        
        if alert_id in self.alert_status["active_alerts"]:
            if current_value < threshold:
                # Alert is resolved
                alert = self.alert_status["active_alerts"].pop(alert_id)
                self.alert_status["resolved_alerts"][alert_id] = alert
                self.alert_status["resolved_alerts"][alert_id]["resolved_at"] = \
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Save updated status
                self.save_alert_status()
                
                # Send resolution notification
                if self.config and self.config.get('email', {}).get('enabled', False):
                    self._send_resolution_email(nickname, hostname, metric, current_value)
    
    def _send_email_alert(self, nickname, hostname, message, is_new_alert):
        """Send an alert email."""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['email']['sender']
            msg['To'] = ", ".join(self.config['email']['recipients'])
            
            # Set subject based on whether it's new or recurring
            subject_prefix = "NEW ALERT" if is_new_alert else "RECURRING ALERT"
            msg['Subject'] = f"HEIMDALL {subject_prefix}: {nickname} - {message}"
            
            # Create HTML version of the message with logo from GitHub URL
            html = f"""
            <html>
              <head>
                <style>
                  body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                  .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                  .header {{ text-align: center; margin-bottom: 20px; }}
                  .logo {{ max-width: 200px; }}
                  h2 {{ color: #cc3300; }}
                  .alert-info {{ background-color: #f8f8f8; padding: 15px; border-left: 4px solid #cc3300; }}
                  .footer {{ margin-top: 30px; font-size: 12px; color: #777; text-align: center; }}
                </style>
              </head>
              <body>
                <div class="container">
                  <div class="header">
                    <img src="https://raw.githubusercontent.com/bnesim/heimdall-monitoring/refs/heads/main/HEIMDALL.png" alt="Heimdall Logo" class="logo">
                  </div>
                  <h2>Heimdall Alert</h2>
                  <div class="alert-info">
                    <p><strong>Server:</strong> {nickname} ({hostname})</p>
                    <p><strong>Alert:</strong> {message}</p>
                    <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>Please investigate this issue as soon as possible.</p>
                  </div>
                  <div class="footer">
                    <p>This is an automated message from Heimdall Monitoring System.</p>
                  </div>
                </div>
              </body>
            </html>
            """
            
            msg.attach(MIMEText(html, 'html'))
            
            # Send the email
            with smtplib.SMTP(self.config['email']['smtp_server'], 
                            self.config['email']['smtp_port']) as server:
                if self.config['email']['use_tls']:
                    server.starttls()
                server.login(self.config['email']['username'],
                           self.config['email']['password'])
                server.send_message(msg)
            
            logger.info(f"Sent alert email for {nickname}")
        except Exception as e:
            logger.error(f"Failed to send alert email: {str(e)}")
    
    def _send_resolution_email(self, nickname, hostname, metric, current_value):
        """Send an alert resolution email."""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['email']['sender']
            msg['To'] = ", ".join(self.config['email']['recipients'])
            msg['Subject'] = f"HEIMDALL RESOLVED: {nickname} - {metric}"
            
            # Create HTML version of the message with logo from GitHub URL
            html = f"""
            <html>
              <head>
                <style>
                  body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                  .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
                  .header {{ text-align: center; margin-bottom: 20px; }}
                  .logo {{ max-width: 200px; }}
                  h2 {{ color: #2c7a2c; font-size: 24px; margin-bottom: 20px; text-align: center; }}
                  .alert-info {{ background-color: #f8f8f8; padding: 15px; border-left: 4px solid #2c7a2c; margin-bottom: 20px; }}
                  .server-info {{ font-weight: bold; margin-bottom: 10px; }}
                  .resolution-message {{ color: #2c7a2c; font-weight: bold; }}
                  .footer {{ margin-top: 30px; font-size: 12px; color: #777; text-align: center; border-top: 1px solid #eee; padding-top: 15px; }}
                </style>
              </head>
              <body>
                <div class="container">
                  <div class="header">
                    <img src="https://raw.githubusercontent.com/bnesim/heimdall-monitoring/refs/heads/main/HEIMDALL.png" alt="Heimdall Logo" class="logo">
                  </div>
                  <h2>Heimdall Alert Resolution</h2>
                  <div class="alert-info">
                    <div class="server-info">
                      <p><strong>Server:</strong> {nickname} ({hostname})</p>
                    </div>
                    <p class="resolution-message"><strong>Resolved Issue:</strong> {metric} is now at {current_value:.1f}%</p>
                    <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>The previously reported issue has been resolved. No further action is required.</p>
                  </div>
                  <div class="footer">
                    <p>This is an automated message from Heimdall Monitoring System.</p>
                  </div>
                </div>
              </body>
            </html>
            """
            
            msg.attach(MIMEText(html, 'html'))
            
            with smtplib.SMTP(self.config['email']['smtp_server'], 
                            self.config['email']['smtp_port']) as server:
                if self.config['email']['use_tls']:
                    server.starttls()
                server.login(self.config['email']['username'],
                           self.config['email']['password'])
                server.send_message(msg)
            
            logger.info(f"Sent resolution email for {nickname} - {metric}")
        except Exception as e:
            logger.error(f"Failed to send resolution email: {str(e)}")