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
        
        # Session-based alert collection
        self.session_active = False
        self.session_new_alerts = []
        self.session_resolved_alerts = []
        self.session_recurring_alerts = []
    
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
    
    def start_session(self):
        """Start a new alert collection session."""
        self.session_active = True
        self.session_new_alerts = []
        self.session_resolved_alerts = []
        self.session_recurring_alerts = []
        logger.debug("Started new alert session")
    
    def end_session(self):
        """End the alert session and send batch notifications."""
        if not self.session_active:
            return
        
        self.session_active = False
        logger.debug(f"Ending alert session - New: {len(self.session_new_alerts)}, Resolved: {len(self.session_resolved_alerts)}, Recurring: {len(self.session_recurring_alerts)}")
        
        # Send batch notifications
        notifications_sent = False
        
        # Send new/recurring alerts together
        if self.session_new_alerts or self.session_recurring_alerts:
            if self._send_batch_alerts():
                notifications_sent = True
        
        # Send resolved alerts
        if self.session_resolved_alerts:
            if self._send_batch_resolutions():
                notifications_sent = True
        
        # Reset cooldown for all active alerts if we sent any notifications
        if notifications_sent:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.reset_all_alert_cooldowns(now_str)
            self.save_alert_status()
            logger.info("Reset cooldown for all active alerts after sending batch notifications")
        
        # Clear session data
        self.session_new_alerts = []
        self.session_resolved_alerts = []
        self.session_recurring_alerts = []
    
    def get_open_alerts(self):
        """Get a list of all currently open alerts."""
        open_alerts = []
        for alert_id, alert in self.alert_status["active_alerts"].items():
            # Calculate duration
            first_detected = datetime.strptime(alert["first_detected"], "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            duration = now - first_detected
            hours, remainder = divmod(duration.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            duration_str = f"{duration.days} days, {hours} hours" if duration.days > 0 else f"{hours} hours, {minutes} minutes"
            
            open_alerts.append({
                "server": alert["server"],
                "hostname": alert["hostname"],
                "type": alert["type"],
                "message": alert["message"],
                "first_detected": alert["first_detected"],
                "duration": duration_str
            })
        
        return open_alerts
    
    def format_open_alerts_html(self, exclude_alert_id=None):
        """Format open alerts as HTML table for email."""
        open_alerts = self.get_open_alerts()
        
        # Exclude current alert if specified (for resolution messages)
        if exclude_alert_id:
            excluded_alert = self.alert_status["active_alerts"].get(exclude_alert_id)
            if excluded_alert:
                open_alerts = [alert for alert in open_alerts if not (
                    alert["server"] == excluded_alert["server"] and 
                    alert["hostname"] == excluded_alert["hostname"] and 
                    alert["type"] == excluded_alert["type"]
                )]
        
        if not open_alerts:
            return "<p style='color: #48c774; font-style: italic;'>No other open alerts.</p>"
        
        html = """
        <div class="open-alerts">
            <h3 style="color: #333; margin: 20px 0 10px 0;">Other Open Alerts:</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <thead>
                    <tr style="background-color: #f5f5f5;">
                        <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Server</th>
                        <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Issue</th>
                        <th style="padding: 8px; text-align: left; border-bottom: 1px solid #ddd;">Duration</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for alert in open_alerts:
            html += f"""
                    <tr>
                        <td style="padding: 8px; border-bottom: 1px solid #eee; font-family: monospace;">{alert["server"]}</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{alert["message"]}</td>
                        <td style="padding: 8px; border-bottom: 1px solid #eee;">{alert["duration"]}</td>
                    </tr>
            """
        
        html += """
                </tbody>
            </table>
        </div>
        """
        
        return html
    
    def format_open_alerts_text(self, exclude_alert_id=None):
        """Format open alerts as plain text for Telegram."""
        open_alerts = self.get_open_alerts()
        
        # Exclude current alert if specified (for resolution messages)
        if exclude_alert_id:
            excluded_alert = self.alert_status["active_alerts"].get(exclude_alert_id)
            if excluded_alert:
                open_alerts = [alert for alert in open_alerts if not (
                    alert["server"] == excluded_alert["server"] and 
                    alert["hostname"] == excluded_alert["hostname"] and 
                    alert["type"] == excluded_alert["type"]
                )]
        
        if not open_alerts:
            return "\n\n<i>No other open alerts.</i>"
        
        text = "\n\n<b>Other Open Alerts:</b>\n"
        for alert in open_alerts:
            text += f"• <b>{alert['server']}</b> ({alert['hostname']}): {alert['message']} - Duration: {alert['duration']}\n"
        
        return text
    
    def reset_all_alert_cooldowns(self, current_time_str):
        """Reset the last_notified timestamp for all active alerts."""
        for alert_id in self.alert_status["active_alerts"]:
            self.alert_status["active_alerts"][alert_id]["last_notified"] = current_time_str
        logger.debug(f"Reset cooldown for {len(self.alert_status['active_alerts'])} active alerts")
    
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
        
        # If we're in a session, queue the alert instead of sending immediately
        if self.session_active and should_send_email:
            alert_data = {
                "server": nickname,
                "hostname": hostname,
                "message": message,
                "type": alert_type,
                "alert_id": alert_id,
                "is_new": is_new_alert,
                "is_recurring": is_recurring
            }
            
            if is_new_alert:
                self.session_new_alerts.append(alert_data)
            else:
                self.session_recurring_alerts.append(alert_data)
            
            logger.debug(f"Queued {'new' if is_new_alert else 'recurring'} alert for {nickname} in session")
            return True
        
        # Original immediate notification logic (for non-session mode)
        alert_cooldown = self.config.get('alert_cooldown', 1)
        email_sent = False
        telegram_sent = False
        
        if should_send_email and not self.session_active:
            # Send email if enabled
            if self.config and self.config.get('email', {}).get('enabled', False):
                email_sent = self._send_email_alert(nickname, hostname, message, is_new_alert, alert_cooldown)
            
            # Send Telegram if enabled
            if self.telegram_bot.is_configured():
                open_alerts_text = self.format_open_alerts_text()
                telegram_sent = self.telegram_bot.send_alert_to_all(nickname, hostname, message, is_new_alert, open_alerts_text)
            
            # If we sent a notification (NEW or RECURRING), reset cooldown for ALL active alerts
            if email_sent or telegram_sent:
                self.reset_all_alert_cooldowns(now_str)
                self.save_alert_status()  # Save the updated timestamps
                logger.info(f"Reset cooldown for all active alerts after sending {'NEW' if is_new_alert else 'RECURRING'} alert")
        
        # Log the outcome
        if not should_send_email and alert_id in self.alert_status["active_alerts"]:
            logger.info(f"Alert {alert_id} logged but notifications suppressed (rate limited)")
        elif not email_sent and not telegram_sent and not self.session_active:
            logger.info(f"Alert {alert_id} logged (no notifications sent)")
        
        return email_sent or telegram_sent or self.session_active
    
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
                
                # Calculate duration
                first_detected = datetime.strptime(alert["first_detected"], "%Y-%m-%d %H:%M:%S")
                resolved_time = datetime.strptime(alert["resolved_time"], "%Y-%m-%d %H:%M:%S")
                duration = resolved_time - first_detected
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                duration_str = f"{duration.days} days, {hours} hours, {minutes} minutes" if duration.days > 0 else f"{hours} hours, {minutes} minutes"
                
                # If we're in a session, queue the resolution
                if self.session_active:
                    resolution_data = {
                        "server": nickname,
                        "hostname": hostname,
                        "metric": metric,
                        "current_value": current_value,
                        "threshold": threshold,
                        "alert_info": alert,
                        "alert_id": alert_id,
                        "duration": duration_str
                    }
                    self.session_resolved_alerts.append(resolution_data)
                    logger.debug(f"Queued resolution for {nickname} {metric} in session")
                    return True
                
                # Original immediate notification logic (for non-session mode)
                email_sent = False
                telegram_sent = False
                
                if self.config and self.config.get('email', {}).get('enabled', False):
                    email_sent = self._send_resolution_email(nickname, hostname, metric, current_value, threshold, alert, alert_id)
                
                if self.telegram_bot.is_configured():
                    telegram_sent = self.telegram_bot.send_resolution_to_all(nickname, hostname, metric, current_value, threshold, duration_str, self.format_open_alerts_text(alert_id))
                
                # If we sent resolution notifications, reset cooldown for ALL remaining active alerts
                if (email_sent or telegram_sent) and self.alert_status["active_alerts"]:
                    resolved_time = alert["resolved_time"]
                    self.reset_all_alert_cooldowns(resolved_time)
                    self.save_alert_status()  # Save the updated timestamps
                    logger.info(f"Reset cooldown for all remaining active alerts after sending RESOLVED notification")
                
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
            
            # Get open alerts for inclusion in the email
            open_alerts_html = self.format_open_alerts_html()
            
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
                  .open-alerts {{ margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-radius: 4px; border-left: 4px solid #ffc107; }}
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
                  
                  {open_alerts_html}
                  
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
    
    def _send_resolution_email(self, nickname, hostname, metric, current_value, threshold, alert_info, alert_id=None):
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
            
            # Get open alerts for inclusion in the email (excluding the one being resolved)
            open_alerts_html = self.format_open_alerts_html(alert_id)
            
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
                    .open-alerts {{ margin: 20px 0; padding: 15px; background-color: #f8f9fa; border-radius: 4px; border-left: 4px solid #ffc107; }}
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
                    
                    {open_alerts_html}
                    
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
    
    def _send_batch_alerts(self):
        """Send batch email and Telegram for all queued alerts."""
        if not self.session_new_alerts and not self.session_recurring_alerts:
            return False
        
        all_alerts = self.session_new_alerts + self.session_recurring_alerts
        
        # Group alerts by server for better organization
        alerts_by_server = {}
        for alert in all_alerts:
            server_key = f"{alert['server']} ({alert['hostname']})"
            if server_key not in alerts_by_server:
                alerts_by_server[server_key] = {"new": [], "recurring": []}
            
            if alert['is_new']:
                alerts_by_server[server_key]["new"].append(alert)
            else:
                alerts_by_server[server_key]["recurring"].append(alert)
        
        notifications_sent = False
        
        # Send batch email
        if self.config and self.config.get('email', {}).get('enabled', False):
            if self._send_batch_email_alerts(alerts_by_server):
                notifications_sent = True
        
        # Send batch Telegram
        if self.telegram_bot.is_configured():
            if self._send_batch_telegram_alerts(alerts_by_server):
                notifications_sent = True
        
        return notifications_sent
    
    def _send_batch_resolutions(self):
        """Send batch email and Telegram for all resolved alerts."""
        if not self.session_resolved_alerts:
            return False
        
        # Group resolutions by server
        resolutions_by_server = {}
        for resolution in self.session_resolved_alerts:
            server_key = f"{resolution['server']} ({resolution['hostname']})"
            if server_key not in resolutions_by_server:
                resolutions_by_server[server_key] = []
            resolutions_by_server[server_key].append(resolution)
        
        notifications_sent = False
        
        # Send batch email
        if self.config and self.config.get('email', {}).get('enabled', False):
            if self._send_batch_resolution_email(resolutions_by_server):
                notifications_sent = True
        
        # Send batch Telegram
        if self.telegram_bot.is_configured():
            if self._send_batch_telegram_resolutions(resolutions_by_server):
                notifications_sent = True
        
        return notifications_sent
    
    def _send_batch_email_alerts(self, alerts_by_server):
        """Send a single email with all new and recurring alerts."""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['email']['sender']
            msg['To'] = ", ".join(self.config['email']['recipients'])
            
            # Count alerts
            new_count = sum(len(alerts["new"]) for alerts in alerts_by_server.values())
            recurring_count = sum(len(alerts["recurring"]) for alerts in alerts_by_server.values())
            
            # Set subject
            if new_count > 0 and recurring_count > 0:
                msg['Subject'] = f"HEIMDALL ALERTS: {new_count} new, {recurring_count} recurring issues detected"
            elif new_count > 0:
                msg['Subject'] = f"HEIMDALL NEW ALERTS: {new_count} new issues detected"
            else:
                msg['Subject'] = f"HEIMDALL RECURRING ALERTS: {recurring_count} issues persist"
            
            # Get open alerts for inclusion
            open_alerts_html = self.format_open_alerts_html()
            
            # Build HTML content
            html = f"""
            <html>
              <head>
                <style>
                  body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9f9f9; margin: 0; padding: 0; }}
                  .container {{ max-width: 800px; margin: 20px auto; padding: 20px; background-color: #fff; border-radius: 5px; border-top: 5px solid #ff3860; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); }}
                  h1 {{ color: #ff3860; margin-top: 0; }}
                  h2 {{ color: #333; margin-top: 30px; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
                  .logo {{ text-align: center; margin-bottom: 20px; }}
                  .logo img {{ width: 150px; height: auto; }}
                  .server-section {{ background-color: #f5f5f5; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                  .server-name {{ font-size: 18px; font-weight: bold; color: #333; }}
                  .alert-item {{ margin: 10px 0; padding: 10px; border-left: 4px solid #ff3860; background-color: #fff; }}
                  .new-alert {{ border-left-color: #ff3860; }}
                  .recurring-alert {{ border-left-color: #ffc107; }}
                  .alert-type {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 12px; font-weight: bold; margin-right: 10px; }}
                  .type-new {{ background-color: #ff3860; color: white; }}
                  .type-recurring {{ background-color: #ffc107; color: #333; }}
                  .timestamp {{ color: #777; font-size: 14px; margin-top: 20px; }}
                  .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #777; }}
                  .summary {{ background-color: #f8f9fa; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                  .summary-item {{ display: inline-block; margin-right: 20px; }}
                  .summary-count {{ font-size: 24px; font-weight: bold; }}
                  .summary-label {{ font-size: 14px; color: #666; }}
                </style>
              </head>
              <body>
                <div class="container">
                  <div class="logo">
                    <img src="https://raw.githubusercontent.com/bnesim/heimdall-monitoring/refs/heads/main/HEIMDALL.png" alt="Heimdall Logo">
                  </div>
                  <h1>⚠️ Heimdall Alert Summary ⚠️</h1>
                  
                  <div class="summary">
                    <div class="summary-item">
                      <div class="summary-count" style="color: #ff3860;">{new_count}</div>
                      <div class="summary-label">New Alerts</div>
                    </div>
                    <div class="summary-item">
                      <div class="summary-count" style="color: #ffc107;">{recurring_count}</div>
                      <div class="summary-label">Recurring Alerts</div>
                    </div>
                    <div class="summary-item">
                      <div class="summary-count" style="color: #666;">{len(alerts_by_server)}</div>
                      <div class="summary-label">Affected Servers</div>
                    </div>
                  </div>
            """
            
            # Add alerts by server
            for server_key, alerts in sorted(alerts_by_server.items()):
                if not alerts["new"] and not alerts["recurring"]:
                    continue
                
                html += f"""
                  <div class="server-section">
                    <div class="server-name">{server_key}</div>
                """
                
                # Add new alerts
                for alert in alerts["new"]:
                    html += f"""
                    <div class="alert-item new-alert">
                      <span class="alert-type type-new">NEW</span>
                      {alert['message']}
                    </div>
                    """
                
                # Add recurring alerts
                for alert in alerts["recurring"]:
                    html += f"""
                    <div class="alert-item recurring-alert">
                      <span class="alert-type type-recurring">RECURRING</span>
                      {alert['message']}
                    </div>
                    """
                
                html += "</div>"
            
            html += f"""
                  <div class="timestamp">
                    Detected: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                  </div>
                  
                  {open_alerts_html}
                  
                  <div class="footer">
                    This is an automated batch alert from Heimdall monitoring system.
                    <br>You will not receive another notification about these issues for at least {self.config.get('alert_cooldown', 1)} hour(s).
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
            
            logger.info(f"Batch alert email sent with {new_count} new and {recurring_count} recurring alerts")
            return True
        except Exception as e:
            logger.error(f"Failed to send batch alert email: {str(e)}")
            return False
    
    def _send_batch_resolution_email(self, resolutions_by_server):
        """Send a single email with all resolved alerts."""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = self.config['email']['sender']
            msg['To'] = ", ".join(self.config['email']['recipients'])
            
            # Count resolutions
            total_resolved = sum(len(resolutions) for resolutions in resolutions_by_server.values())
            
            msg['Subject'] = f"HEIMDALL RESOLVED: {total_resolved} issues resolved"
            
            # Get open alerts for inclusion
            open_alerts_html = self.format_open_alerts_html()
            
            # Build HTML content
            html = f"""
            <html>
              <head>
                <style>
                  body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f9f9f9; margin: 0; padding: 0; }}
                  .container {{ max-width: 800px; margin: 20px auto; padding: 20px; background-color: #fff; border-radius: 5px; border-top: 5px solid #48c774; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); }}
                  h1 {{ color: #48c774; margin-top: 0; }}
                  .logo {{ text-align: center; margin-bottom: 20px; }}
                  .logo img {{ width: 150px; height: auto; }}
                  .server-section {{ background-color: #f5f5f5; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                  .server-name {{ font-size: 18px; font-weight: bold; color: #333; }}
                  .resolution-item {{ margin: 10px 0; padding: 10px; border-left: 4px solid #48c774; background-color: #fff; }}
                  .metric-info {{ margin-top: 5px; font-size: 14px; color: #666; }}
                  .duration {{ color: #777; font-style: italic; }}
                  .timestamp {{ color: #777; font-size: 14px; margin-top: 20px; }}
                  .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #777; }}
                  .summary {{ background-color: #f8f9fa; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                  .summary-count {{ font-size: 24px; font-weight: bold; color: #48c774; }}
                  .summary-label {{ font-size: 14px; color: #666; }}
                </style>
              </head>
              <body>
                <div class="container">
                  <div class="logo">
                    <img src="https://raw.githubusercontent.com/bnesim/heimdall-monitoring/refs/heads/main/HEIMDALL.png" alt="Heimdall Logo">
                  </div>
                  <h1>✅ Alerts Resolved</h1>
                  
                  <div class="summary">
                    <div class="summary-count">{total_resolved}</div>
                    <div class="summary-label">Issues Resolved on {len(resolutions_by_server)} server(s)</div>
                  </div>
            """
            
            # Add resolutions by server
            for server_key, resolutions in sorted(resolutions_by_server.items()):
                html += f"""
                  <div class="server-section">
                    <div class="server-name">{server_key}</div>
                """
                
                for resolution in resolutions:
                    html += f"""
                    <div class="resolution-item">
                      <strong>{resolution['metric']}</strong> has returned to normal
                      <div class="metric-info">
                        Current: {resolution['current_value']:.1f}% (threshold: {resolution['threshold']}%)
                        <br><span class="duration">Problem duration: {resolution['duration']}</span>
                      </div>
                    </div>
                    """
                
                html += "</div>"
            
            html += f"""
                  <div class="timestamp">
                    Resolved: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                  </div>
                  
                  {open_alerts_html}
                  
                  <div class="footer">
                    This is an automated resolution notification from Heimdall monitoring system.
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
            
            logger.info(f"Batch resolution email sent with {total_resolved} resolved alerts")
            return True
        except Exception as e:
            logger.error(f"Failed to send batch resolution email: {str(e)}")
            return False
    
    def _send_batch_telegram_alerts(self, alerts_by_server):
        """Send batch Telegram message with all alerts."""
        try:
            # Count alerts
            new_count = sum(len(alerts["new"]) for alerts in alerts_by_server.values())
            recurring_count = sum(len(alerts["recurring"]) for alerts in alerts_by_server.values())
            
            # Build message
            if new_count > 0 and recurring_count > 0:
                message = f"<b>⚠️ HEIMDALL ALERT SUMMARY</b>\n\n"
                message += f"<b>{new_count}</b> new issues, <b>{recurring_count}</b> recurring issues\n"
            elif new_count > 0:
                message = f"<b>⚠️ NEW HEIMDALL ALERTS</b>\n\n"
                message += f"<b>{new_count}</b> new issues detected\n"
            else:
                message = f"<b>⚠️ RECURRING HEIMDALL ALERTS</b>\n\n"
                message += f"<b>{recurring_count}</b> issues persist\n"
            
            message += f"<b>{len(alerts_by_server)}</b> servers affected\n\n"
            
            # Add alerts by server
            for server_key, alerts in sorted(alerts_by_server.items()):
                if not alerts["new"] and not alerts["recurring"]:
                    continue
                
                message += f"<b>{server_key}</b>\n"
                
                # Add new alerts
                for alert in alerts["new"]:
                    message += f"  🔴 <b>NEW:</b> {alert['message']}\n"
                
                # Add recurring alerts
                for alert in alerts["recurring"]:
                    message += f"  🟡 <b>RECURRING:</b> {alert['message']}\n"
                
                message += "\n"
            
            # Add open alerts
            message += self.format_open_alerts_text()
            
            # Send to all subscribers
            sent_count = 0
            for subscriber in self.telegram_bot.subscribers:
                if self.telegram_bot.send_message(subscriber['chat_id'], message):
                    sent_count += 1
            
            logger.info(f"Batch alert sent to {sent_count} Telegram subscribers")
            return sent_count > 0
        except Exception as e:
            logger.error(f"Failed to send batch Telegram alerts: {str(e)}")
            return False
    
    def _send_batch_telegram_resolutions(self, resolutions_by_server):
        """Send batch Telegram message with all resolutions."""
        try:
            # Count resolutions
            total_resolved = sum(len(resolutions) for resolutions in resolutions_by_server.values())
            
            message = f"<b>✅ HEIMDALL RESOLVED</b>\n\n"
            message += f"<b>{total_resolved}</b> issues resolved on <b>{len(resolutions_by_server)}</b> server(s)\n\n"
            
            # Add resolutions by server
            for server_key, resolutions in sorted(resolutions_by_server.items()):
                message += f"<b>{server_key}</b>\n"
                
                for resolution in resolutions:
                    message += f"  ✅ <b>{resolution['metric']}</b>: {resolution['current_value']:.1f}% (threshold: {resolution['threshold']}%)\n"
                    message += f"     Duration: {resolution['duration']}\n"
                
                message += "\n"
            
            # Add open alerts
            message += self.format_open_alerts_text()
            
            # Send to all subscribers
            sent_count = 0
            for subscriber in self.telegram_bot.subscribers:
                if self.telegram_bot.send_message(subscriber['chat_id'], message):
                    sent_count += 1
            
            logger.info(f"Batch resolution sent to {sent_count} Telegram subscribers")
            return sent_count > 0
        except Exception as e:
            logger.error(f"Failed to send batch Telegram resolutions: {str(e)}")
            return False