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
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from .telegram import TelegramBot

# Alert status file
ALERT_STATUS_FILE = "alert_status.json"

logger = logging.getLogger("Heimdall")

class AlertManager:
    def __init__(self, config):
        self.config = config
        self.alert_status = self.load_alert_status()
        self.telegram_bot = TelegramBot(config)
        if self.telegram_bot.is_configured():
            self.telegram_bot.start_polling()
    
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
        os.makedirs('logs', exist_ok=True)
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
            
            # Use the configurable alert_cooldown from config
            alert_cooldown = self.config.get('alert_cooldown', 1)  # Default to 1 hour if not configured
            
            if hours_since_last_notification >= alert_cooldown:
                should_send_email = True
                self.alert_status["active_alerts"][alert_id]["last_notified"] = now_str
        
        # Save updated alert status
        self.save_alert_status()
        
        # Get alert_cooldown for email (in case it wasn't set above)
        alert_cooldown = self.config.get('alert_cooldown', 1)  # Default to 1 hour if not configured
        
        # Send notifications if needed
        email_sent = False
        telegram_sent = False
        
        if should_send_email:
            # Send email if enabled
            if self.config and self.config.get('email', {}).get('enabled', False):
                email_sent = self._send_email_alert(nickname, hostname, message, is_new_alert, alert_cooldown)
            
            # Send Telegram if enabled
            if self.telegram_bot.is_configured():
                telegram_sent = self.telegram_bot.send_alert_to_all(nickname, hostname, message, is_new_alert)
        
        # Log the outcome
        if not should_send_email and alert_id in self.alert_status["active_alerts"]:
            logger.info(f"Alert {alert_id} logged but notifications suppressed (rate limited)")
        elif not email_sent and not telegram_sent:
            logger.info(f"Alert {alert_id} logged (no notifications sent)")
        
        return email_sent or telegram_sent
    
    def check_alert_resolution(self, nickname, hostname, metric, current_value, threshold):
        """Check if an alert has been resolved."""
        alert_id = self.get_alert_id(nickname, hostname, metric.lower())
        logger.debug(f"Checking resolution for {nickname}:{hostname}:{metric} - alert_id: {alert_id}")
        logger.debug(f"Active alerts: {list(self.alert_status['active_alerts'].keys())}")
        
        if alert_id in self.alert_status["active_alerts"]:
            logger.debug(f"Found active alert for {alert_id}, current_value={current_value}, threshold={threshold}")
            if current_value < threshold:
                # Alert is resolved
                alert = self.alert_status["active_alerts"].pop(alert_id)
                alert["resolved_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.alert_status["resolved_alerts"][alert_id] = alert
                
                # Save updated status
                self.save_alert_status()
                
                # Log resolution
                logger.info(f"{nickname} ({hostname}): {metric} alert resolved - now at {current_value:.1f}%, below threshold of {threshold}%")
                
                # Calculate duration for Telegram
                first_detected = datetime.strptime(alert["first_detected"], "%Y-%m-%d %H:%M:%S")
                resolved_time = datetime.strptime(alert["resolved_time"], "%Y-%m-%d %H:%M:%S")
                duration = resolved_time - first_detected
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{duration.days} days, {hours} hours, {minutes} minutes" if duration.days > 0 else f"{hours} hours, {minutes} minutes"
                
                # Send resolution notifications
                email_sent = False
                telegram_sent = False
                
                if self.config and self.config.get('email', {}).get('enabled', False):
                    email_sent = self._send_resolution_email(nickname, hostname, metric, current_value, threshold, alert)
                
                if self.telegram_bot.is_configured():
                    telegram_sent = self.telegram_bot.send_resolution_to_all(nickname, hostname, metric, current_value, threshold, duration_str)
                
                logger.info(f"Resolution notifications sent - Email: {email_sent}, Telegram: {telegram_sent}")
                return email_sent or telegram_sent
        else:
            logger.debug(f"No active alert found for {alert_id}")
        return False
    
    def _send_email_alert(self, nickname, hostname, message, is_new_alert, alert_cooldown):
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
                  body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9f9f9; margin: 0; padding: 0; }}
                  .container {{ max-width: 600px; margin: 20px auto; padding: 20px; background-color: #fff; border-radius: 5px; border-top: 5px solid #ff3860; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); }}
                  h1 {{ color: #ff3860; margin-top: 0; }}
                  .logo {{ text-align: center; margin-bottom: 20px; }}
                  .logo img {{ width: 150px; height: auto; }}
                  .server-info {{ background-color: #f5f5f5; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                  .server-name {{ font-size: 18px; font-weight: bold; color: #333; }}
                  .server-hostname {{ color: #777; font-family: monospace; }}
                  .alert-message {{ font-size: 18px; color: #ff3860; background-color: #ffeeee; padding: 10px; border-radius: 4px; margin: 15px 0; }}
                  .timestamp {{ color: #777; font-size: 14px; margin-top: 20px; }}
                  .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #777; }}
                </style>
              </head>
              <body>
                <div class="container">
                  <div class="logo">
                    <img src="https://raw.githubusercontent.com/bnesim/heimdall-monitoring/refs/heads/main/HEIMDALL.png" alt="Heimdall Logo">
                  </div>
                  <h1>⚠️ Heimdall Server Alert ⚠️</h1>
                  <p>Heimdall has detected an issue that requires your attention.</p>
                  
                  <div class="server-info">
                    <div class="server-name">{nickname}</div>
                    <div class="server-hostname">{hostname}</div>
                  </div>
                  
                  <div class="alert-message">
                    {message}
                  </div>
                  
                  <div class="timestamp">
                    Detected: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                  </div>
                  
                  <div class="footer">
                    This is an automated message from Heimdall, the all-seeing guardian of your servers.
                    <br>You will not receive another notification about this issue for at least {alert_cooldown} hour(s).
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
            
            logger.info(f"Alert email sent to {msg['To']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send alert email: {str(e)}")
            return False
    
    def _send_resolution_email(self, nickname, hostname, metric, current_value, threshold, alert_info):
        """Send an alert resolution email."""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['email']['sender']
            msg['To'] = ", ".join(self.config['email']['recipients'])
            msg['Subject'] = f"HEIMDALL RESOLVED: {nickname} - {metric} issue resolved"
            
            # Calculate problem duration
            first_detected = datetime.strptime(alert_info["first_detected"], "%Y-%m-%d %H:%M:%S")
            resolved_time = datetime.strptime(alert_info["resolved_time"], "%Y-%m-%d %H:%M:%S")
            duration = resolved_time - first_detected
            hours, remainder = divmod(duration.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = f"{duration.days} days, {hours} hours, {minutes} minutes" if duration.days > 0 else f"{hours} hours, {minutes} minutes"
            
            # Create HTML version of the message with logo from GitHub URL
            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9f9f9; margin: 0; padding: 0; }}
                    .container {{ max-width: 600px; margin: 20px auto; padding: 20px; background-color: #fff; border-radius: 5px; border-top: 5px solid #48c774; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); }}
                    h1 {{ color: #48c774; margin-top: 0; }}
                    .logo {{ text-align: center; margin-bottom: 20px; }}
                    .logo img {{ width: 150px; height: auto; }}
                    .server-info {{ background-color: #f5f5f5; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                    .server-name {{ font-size: 18px; font-weight: bold; color: #333; }}
                    .server-hostname {{ color: #777; font-family: monospace; }}
                    .resolve-message {{ font-size: 18px; color: #48c774; background-color: #effaf5; padding: 10px; border-radius: 4px; margin: 15px 0; }}
                    .alert-details {{ background-color: #f5f5f5; padding: 12px; border-radius: 4px; margin: 15px 0; font-size: 14px; }}
                    .detail-row {{ display: flex; justify-content: space-between; margin-bottom: 5px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
                    .detail-label {{ font-weight: bold; }}
                    .timestamp {{ color: #777; font-size: 14px; margin-top: 20px; }}
                    .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #777; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="logo">
                        <img src="https://raw.githubusercontent.com/bnesim/heimdall-monitoring/refs/heads/main/HEIMDALL.png" alt="Heimdall Logo">
                    </div>
                    <h1>✅ Alert Resolved</h1>
                    <p>Heimdall has detected that a previous alert has been resolved.</p>
                    
                    <div class="server-info">
                        <div class="server-name">{nickname}</div>
                        <div class="server-hostname">{hostname}</div>
                    </div>
                    
                    <div class="resolve-message">
                        {metric} usage has returned to normal levels: {current_value:.1f}% (threshold: {threshold}%)
                    </div>
                    
                    <div class="alert-details">
                        <div class="detail-row">
                            <span class="detail-label">First Detected:</span>
                            <span>{alert_info["first_detected"]}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Resolved:</span>
                            <span>{alert_info["resolved_time"]}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Duration:</span>
                            <span>{duration_str}</span>
                        </div>
                        <div class="detail-row">
                            <span class="detail-label">Original Issue:</span>
                            <span>{alert_info["message"]}</span>
                        </div>
                    </div>
                    
                    <div class="footer">
                        This is an automated message from Heimdall, the all-seeing guardian of your servers.
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
            
            logger.info(f"Resolution email sent to {msg['To']}")
            return True
        except Exception as e:
            logger.error(f"Failed to send resolution email: {str(e)}")
            return False
            
    def send_test_email(self):
        """Send a test email to verify SMTP settings."""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['email']['sender']
            msg['To'] = ", ".join(self.config['email']['recipients'])
            msg['Subject'] = "HEIMDALL TEST EMAIL"
            
            body = f'''
            This is a test email from Heimdall Monitoring System.
            
            Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            
            If you're receiving this, your SMTP configuration is working correctly!
            '''
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Connect to SMTP server and send email
            server = smtplib.SMTP(self.config['email']['smtp_server'], self.config['email']['smtp_port'])
            
            if self.config['email']['use_tls']:
                server.starttls()
            
            if self.config['email']['username'] and self.config['email']['password']:
                server.login(self.config['email']['username'], self.config['email']['password'])
            
            server.send_message(msg)
            server.quit()
            
            logger.info("Test email sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send test email: {str(e)}")
            return False
    
    def send_test_telegram(self):
        """Send a test message to all Telegram subscribers."""
        if not self.telegram_bot.is_configured():
            logger.error("Telegram bot is not configured")
            return False
        
        test_message = f"""<b>🧪 TEST MESSAGE</b>

This is a test message from Heimdall Monitoring System.

<b>Time:</b> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
<b>Subscribers:</b> {len(self.telegram_bot.subscribers)}

If you're receiving this, your Telegram configuration is working correctly!"""
        
        sent_count = 0
        for subscriber in self.telegram_bot.subscribers:
            if self.telegram_bot.send_message(subscriber['chat_id'], test_message):
                sent_count += 1
        
        logger.info(f"Test message sent to {sent_count}/{len(self.telegram_bot.subscribers)} Telegram subscribers")
        return sent_count > 0