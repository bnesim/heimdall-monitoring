#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Heimdall - The Watchful Server Monitor

Created: April 4, 2025
Author: BNEsim Team

This script allows monitoring multiple servers for CPU, memory, and disk usage.
It can be run in interactive mode to add/remove servers or in check mode to monitor all servers.
"""

import os
import sys
import json
import time
import socket
import hashlib
import logging
import argparse
import paramiko
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from heimdall.config import load_config, ServerConfig, CONFIG_FILE, SERVERS_FILE
from heimdall.monitor import ServerMonitor
from heimdall.utils import setup_logging, Colors, LOG_FILE
from heimdall.alerts import AlertManager, ALERT_STATUS_FILE, ALERT_COOLDOWN

# Load configuration
def load_config():
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
        print(f"Error loading configuration: {str(e)}")
        return None

# Load configuration
config = load_config()

# Thresholds
CPU_THRESHOLD = config['thresholds']['cpu'] if config else 80  # 80%
MEM_THRESHOLD = config['thresholds']['memory'] if config else 80  # 80%
DISK_THRESHOLD = config['thresholds']['disk'] if config else 85  # 85%

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Heimdall")

# ANSI Colors for terminal output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


class ServerMonitor:
    def __init__(self):
        self.servers = []
        self.load_servers()

    def load_servers(self):
        """Load servers from the JSON file"""
        if os.path.exists(SERVERS_FILE):
            try:
                with open(SERVERS_FILE, 'r') as f:
                    data = json.load(f)
                    self.servers = data.get('servers', [])
                logger.info(f"Loaded {len(self.servers)} servers from configuration")
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {SERVERS_FILE}")
                print(f"{Colors.RED}Error: Invalid JSON in {SERVERS_FILE}{Colors.END}")
                self.servers = []
        else:
            # Create an empty servers file
            logger.info(f"Creating new servers file: {SERVERS_FILE}")
            self.save_servers()

    def save_servers(self):
        """Save servers to the JSON file"""
        data = {'servers': self.servers}
        with open(SERVERS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(self.servers)} servers to configuration")

    def add_server(self):
        """Add a new server interactively"""
        print(f"\n{Colors.GREEN}{Colors.BOLD}Add New Server{Colors.END}")
        print("="*20)
        
        hostname = input("Server Hostname/IP: ").strip()
        if not hostname:
            print(f"{Colors.RED}Error: Hostname cannot be empty{Colors.END}")
            return
            
        port_input = input("SSH Port (default: 22): ").strip()
        port = 22 if not port_input else int(port_input)
        
        username = input("Username: ").strip()
        if not username:
            print(f"{Colors.RED}Error: Username cannot be empty{Colors.END}")
            return
        
        # Ask for authentication method
        print(f"\n{Colors.BLUE}Authentication Method:{Colors.END}")
        print("1. SSH Key (recommended)")
        print("2. Password")
        auth_method = input("Select authentication method [1]: ").strip() or "1"
        
        password = None
        key_path = None
        
        if auth_method == "1":
            key_path = input("SSH Key Path (default: ~/.ssh/id_rsa): ").strip() or os.path.expanduser("~/.ssh/id_rsa")
            if not os.path.exists(key_path):
                print(f"{Colors.YELLOW}Warning: SSH key file not found: {key_path}{Colors.END}")
                use_password = input("Would you like to use password authentication instead? (y/n): ").strip().lower()
                if use_password == 'y':
                    password = input("Password: ").strip()
                else:
                    print(f"{Colors.RED}Cannot proceed without valid authentication.{Colors.END}")
                    return
        else:
            password = input("Password: ").strip()
        
        # Connect and get the real hostname
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            print(f"\nConnecting to {hostname}:{port} with user {username}...")
            
            # Connection parameters
            connect_params = {
                'hostname': hostname,
                'port': port,
                'username': username,
                'timeout': 5
            }
            
            # Try SSH key authentication if key_path is provided
            if key_path and os.path.exists(key_path):
                connect_params['key_filename'] = key_path
            elif password:
                connect_params['password'] = password
            else:
                print(f"{Colors.RED}Error: No valid authentication method provided.{Colors.END}")
                return
                
            client.connect(**connect_params)
            
            # Get the real hostname
            stdin, stdout, stderr = client.exec_command("hostname")
            real_hostname = stdout.read().decode('utf-8').strip()
            
            # If we got a hostname, use it as the nickname
            if real_hostname:
                nickname = real_hostname
                print(f"\nDetected server hostname: {Colors.GREEN}{nickname}{Colors.END}")
            else:
                # Fall back to using the IP/hostname as the nickname
                nickname = hostname
                print(f"\nCouldn't detect hostname, using: {Colors.YELLOW}{nickname}{Colors.END}")
            
            client.close()
            
            server = {
                'hostname': hostname,
                'port': port,
                'username': username,
                'nickname': nickname
            }
            
            # Add authentication details
            if key_path and os.path.exists(key_path):
                server['key_path'] = key_path
            if password:
                server['password'] = password
            
            self.servers.append(server)
            self.save_servers()
            logger.info(f"Added new server: {nickname} ({hostname})")
            print(f"\n{Colors.GREEN}Server '{nickname}' added successfully!{Colors.END}")
            return True
        except Exception as e:
            logger.error(f"SSH connection error to {hostname}: {str(e)}")
            print(f"\n{Colors.RED}Failed to connect to server: {str(e)}{Colors.END}")
            print(f"\n{Colors.RED}Server not added.{Colors.END}")
            return False

    def remove_server(self):
        """Remove a server interactively"""
        if not self.servers:
            print(f"\n{Colors.YELLOW}No servers configured yet.{Colors.END}")
            return
            
        print(f"\n{Colors.YELLOW}{Colors.BOLD}Remove Server{Colors.END}")
        print("="*20)
        
        self.list_servers()
        
        nickname = input("\nEnter the nickname of the server to remove: ").strip()
        
        for i, server in enumerate(self.servers):
            if server['nickname'] == nickname:
                del self.servers[i]
                self.save_servers()
                logger.info(f"Removed server: {nickname}")
                print(f"\n{Colors.GREEN}Server '{nickname}' removed successfully!{Colors.END}")
                return
                
        logger.warning(f"Server not found: {nickname}")
        print(f"\n{Colors.RED}Server with nickname '{nickname}' not found!{Colors.END}")

    def list_servers(self):
        """List all configured servers"""
        if not self.servers:
            print(f"\n{Colors.YELLOW}No servers configured yet.{Colors.END}")
            return
            
        print(f"\n{Colors.GREEN}{Colors.BOLD}Server List{Colors.END}")
        print("="*20)
        
        for i, server in enumerate(self.servers):
            print(f"  {i+1}. {Colors.BOLD}{server['nickname']}{Colors.END} - {server['hostname']}:{server['port']} ({server['username']})")

    def test_ssh_connection(self, hostname, port, username, password):
        """Test SSH connection to a server"""
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname, port=port, username=username, password=password, timeout=5)
            client.close()
            return True
        except Exception as e:
            logger.error(f"SSH connection error to {hostname}: {str(e)}")
            print(f"{Colors.RED}SSH connection error: {str(e)}{Colors.END}")
            return False

    def check_server(self, server):
        """Check a single server for CPU, memory and disk usage"""
        hostname = server['hostname']
        port = server['port']
        username = server['username']
        password = server['password']
        nickname = server['nickname']
        
        print(f"\n{Colors.YELLOW}{Colors.BOLD}Checking server: {Colors.GREEN}{nickname}{Colors.END} ({hostname})")
        logger.info(f"Checking server: {nickname} ({hostname})")
        
        # Check if the server is reachable
        try:
            socket.create_connection((hostname, port), timeout=5)
        except Exception as e:
            error_msg = f"Server is not reachable: {str(e)}"
            logger.error(f"{nickname} ({hostname}): {error_msg}")
            print(f"{Colors.RED}ERROR: {error_msg}{Colors.END}")
            self.send_alert(nickname, hostname, error_msg)
            return False
            
        # SSH connection and checks
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            print(f"SSH Connection: ", end='')
            client.connect(hostname, port=port, username=username, password=password, timeout=5)
            print(f"{Colors.GREEN}Success{Colors.END}")
            
            # Check CPU usage
            print(f"CPU Usage: ", end='')
            stdin, stdout, stderr = client.exec_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}'")
            cpu_output = stdout.read().decode('utf-8').strip()
            
            if cpu_output:
                cpu_usage = float(cpu_output)
                if cpu_usage >= CPU_THRESHOLD:
                    logger.warning(f"{nickname} ({hostname}): High CPU usage: {cpu_usage:.1f}%")
                    print(f"{Colors.RED}{cpu_usage:.1f}% (ALERT - above threshold){Colors.END}")
                    self.send_alert(nickname, hostname, f"CPU usage at {cpu_usage:.1f}%, threshold is {CPU_THRESHOLD}%")
                else:
                    logger.info(f"{nickname} ({hostname}): CPU usage: {cpu_usage:.1f}%")
                    print(f"{Colors.GREEN}{cpu_usage:.1f}%{Colors.END}")
                    # Check if this resolves an existing alert
                    self.check_alert_resolution(nickname, hostname, "CPU", cpu_usage, CPU_THRESHOLD)
            else:
                logger.error(f"{nickname} ({hostname}): Failed to get CPU data")
                print(f"{Colors.RED}Failed to get CPU data{Colors.END}")
                
            # Check Memory usage
            print(f"Memory Usage: ", end='')
            stdin, stdout, stderr = client.exec_command("free | grep Mem")
            mem_output = stdout.read().decode('utf-8').strip()
            
            if mem_output:
                mem_parts = mem_output.split()
                mem_total = int(mem_parts[1])
                mem_used = int(mem_parts[2])
                mem_usage = (mem_used * 100) / mem_total
                
                if mem_usage >= MEM_THRESHOLD:
                    logger.warning(f"{nickname} ({hostname}): High memory usage: {mem_usage:.1f}%")
                    print(f"{Colors.RED}{mem_usage:.1f}% (ALERT - above threshold){Colors.END}")
                    self.send_alert(nickname, hostname, f"Memory usage at {mem_usage:.1f}%, threshold is {MEM_THRESHOLD}%")
                else:
                    logger.info(f"{nickname} ({hostname}): Memory usage: {mem_usage:.1f}%")
                    print(f"{Colors.GREEN}{mem_usage:.1f}%{Colors.END}")
                    # Check if this resolves an existing alert
                    self.check_alert_resolution(nickname, hostname, "Memory", mem_usage, MEM_THRESHOLD)
            else:
                logger.error(f"{nickname} ({hostname}): Failed to get memory data")
                print(f"{Colors.RED}Failed to get Memory data{Colors.END}")
                
            # Check Disk usage for all mounted filesystems
            print(f"Disk Usage: ")
            stdin, stdout, stderr = client.exec_command("df -h | grep -v tmpfs | grep -v devtmpfs | grep -v Filesystem")
            disk_output_all = stdout.read().decode('utf-8').strip().split('\n')
            
            # Check if we got any output
            if disk_output_all:
                critical_disks = []
                
                # Process each filesystem
                for disk_line in disk_output_all:
                    # Skip empty lines
                    if not disk_line.strip():
                        continue
                    
                    # Parse the disk information
                    parts = disk_line.split()
                    if len(parts) >= 5:  # Ensure we have enough parts to process
                        filesystem = parts[0]
                        mount_point = parts[5] if len(parts) >= 6 else parts[0]
                        usage_str = parts[4].rstrip('%')
                        
                        try:
                            disk_usage = float(usage_str)
                            
                            # Format for display
                            if disk_usage >= DISK_THRESHOLD:
                                critical_disks.append({"mount": mount_point, "usage": disk_usage, "filesystem": filesystem})
                                print(f"  {mount_point}: {Colors.RED}{disk_usage:.1f}% (ALERT - above threshold){Colors.END}")
                            else:
                                print(f"  {mount_point}: {Colors.GREEN}{disk_usage:.1f}%{Colors.END}")
                                
                                # Check if this resolves an existing alert
                                alert_id = self.get_alert_id(nickname, hostname, f"disk:{mount_point}")
                                self.check_alert_resolution(nickname, hostname, f"Disk ({mount_point})", disk_usage, DISK_THRESHOLD)
                                
                        except ValueError:
                            print(f"  {mount_point}: {Colors.YELLOW}Unable to parse usage{Colors.END}")
                
                # Send alerts for critical disks
                if critical_disks:
                    for disk in critical_disks:
                        alert_msg = f"Disk usage for {disk['mount']} at {disk['usage']:.1f}%, threshold is {DISK_THRESHOLD}%"
                        logger.warning(f"{nickname} ({hostname}): {alert_msg}")
                        self.send_alert(nickname, hostname, alert_msg, alert_type=f"disk:{disk['mount']}")
            else:
                logger.error(f"{nickname} ({hostname}): Failed to get disk data")
                print(f"  {Colors.RED}Failed to get Disk data{Colors.END}")
                
            client.close()
            return True
            
        except Exception as e:
            error_msg = f"Error checking server: {str(e)}"
            logger.error(f"{nickname} ({hostname}): {error_msg}")
            print(f"{Colors.RED}{error_msg}{Colors.END}")
            self.send_alert(nickname, hostname, error_msg)
            return False

    def check_all_servers(self):
        """Check all configured servers"""
        if not self.servers:
            logger.warning("No servers configured")
            print(f"\n{Colors.YELLOW}No servers configured. Use interactive mode to add servers.{Colors.END}")
            return
            
        print(f"\n{Colors.GREEN}{Colors.BOLD}Checking All Servers{Colors.END}")
        print("="*25)
        logger.info(f"Starting check of all servers ({len(self.servers)} total)")
        
        for server in self.servers:
            self.check_server(server)
            time.sleep(1)  # Small delay between servers

    def load_alert_status(self):
        """Load the alert status from file"""
        if os.path.exists(ALERT_STATUS_FILE):
            try:
                with open(ALERT_STATUS_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON in {ALERT_STATUS_FILE}")
                return {"active_alerts": {}, "resolved_alerts": {}}
        else:
            return {"active_alerts": {}, "resolved_alerts": {}}
    
    def save_alert_status(self, status):
        """Save the alert status to file"""
        with open(ALERT_STATUS_FILE, 'w') as f:
            json.dump(status, f, indent=2)
    
    def get_alert_id(self, nickname, hostname, alert_type):
        """Generate a unique ID for an alert"""
        alert_string = f"{nickname}:{hostname}:{alert_type}"
        return hashlib.md5(alert_string.encode()).hexdigest()
    
    def send_alert(self, nickname, hostname, message, alert_type=None):
        """Send an alert email with rate limiting and resolution tracking"""
        # Extract alert type from message (e.g., "CPU usage at 90%" -> "CPU")
        if not alert_type:
            alert_type = message.split()[0].lower()
        
        # Log to file
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("logs/alerts.log", "a") as log:
            log.write(f"[{timestamp}] {nickname} ({hostname}): {message}\n")
        
        logger.warning(f"Alert for {nickname} ({hostname}): {message}")
        
        # Generate alert ID
        alert_id = self.get_alert_id(nickname, hostname, alert_type)
        
        # Load current alert status
        alert_status = self.load_alert_status()
        
        # Check if this is a new alert or an existing one
        is_new_alert = alert_id not in alert_status["active_alerts"]
        
        # If it's in resolved alerts, it's a recurring issue
        is_recurring = alert_id in alert_status["resolved_alerts"]
        
        # Get current time
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # Check if we need to send an email (based on rate limiting)
        should_send_email = False
        
        if is_new_alert:
            # New alert, record and send email
            alert_status["active_alerts"][alert_id] = {
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
                del alert_status["resolved_alerts"][alert_id]
        else:
            # Existing alert, update timestamp
            alert_status["active_alerts"][alert_id]["last_detected"] = now_str
            
            # Check if we should send another notification (rate limiting)
            last_notified = datetime.strptime(
                alert_status["active_alerts"][alert_id]["last_notified"],
                "%Y-%m-%d %H:%M:%S"
            )
            
            hours_since_last_notification = (now - last_notified).total_seconds() / 3600
            
            if hours_since_last_notification >= ALERT_COOLDOWN:
                should_send_email = True
                alert_status["active_alerts"][alert_id]["last_notified"] = now_str
        
        # Save updated alert status
        self.save_alert_status(alert_status)
        
        # Check if email alerts are enabled and if we should send one
        if config and config.get('email', {}).get('enabled', False) and should_send_email:
            try:
                # Create a multipart message
                msg = MIMEMultipart('alternative')
                msg['From'] = config['email']['sender']
                msg['To'] = ", ".join(config['email']['recipients'])
                
                # Set subject based on whether it's new or recurring
                subject_prefix = "NEW ALERT" if is_new_alert else "RECURRING ALERT"
                msg['Subject'] = f"HEIMDALL {subject_prefix}: {nickname} - {message}"
                
                # Create HTML version of the message
                html = f'''
                <!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                            background-color: #f9f9f9;
                            margin: 0;
                            padding: 0;
                        }}
                        .container {{
                            max-width: 600px;
                            margin: 20px auto;
                            padding: 20px;
                            background-color: #fff;
                            border-radius: 5px;
                            border-top: 5px solid #ff3860;
                            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                        }}
                        h1 {{
                            color: #ff3860;
                            margin-top: 0;
                        }}
                        .logo {{
                            text-align: center;
                            margin-bottom: 20px;
                        }}
                        .logo img {{
                            width: 150px;
                            height: auto;
                        }}
                        .server-info {{
                            background-color: #f5f5f5;
                            padding: 15px;
                            border-radius: 4px;
                            margin: 20px 0;
                        }}
                        .server-name {{
                            font-size: 18px;
                            font-weight: bold;
                            color: #333;
                        }}
                        .server-hostname {{
                            color: #777;
                            font-family: monospace;
                        }}
                        .alert-message {{
                            font-size: 18px;
                            color: #ff3860;
                            background-color: #ffeeee;
                            padding: 10px;
                            border-radius: 4px;
                            margin: 15px 0;
                        }}
                        .timestamp {{
                            color: #777;
                            font-size: 14px;
                            margin-top: 20px;
                        }}
                        .footer {{
                            margin-top: 30px;
                            padding-top: 20px;
                            border-top: 1px solid #eee;
                            font-size: 12px;
                            color: #777;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="logo">
                            <img src="cid:heimdall_logo" alt="Heimdall Logo">
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
                            Detected: {timestamp}
                        </div>
                        
                        <div class="footer">
                            This is an automated message from Heimdall, the all-seeing guardian of your servers.
                            <br>You will not receive another notification about this issue for at least {ALERT_COOLDOWN} hour(s).
                        </div>
                    </div>
                </body>
                </html>
                '''
                
                # Attach HTML part
                msg.attach(MIMEText(html, 'html'))
                
                # Connect to SMTP server and send email
                server = smtplib.SMTP(config['email']['smtp_server'], config['email']['smtp_port'])
                
                if config['email']['use_tls']:
                    server.starttls()
                
                if config['email']['username'] and config['email']['password']:
                    server.login(config['email']['username'], config['email']['password'])
                
                server.send_message(msg)
                server.quit()
                
                logger.info(f"Alert email sent to {msg['To']}")
                print(f"{Colors.GREEN}Alert email sent to {msg['To']}{Colors.END}")
            except Exception as e:
                logger.error(f"Failed to send alert email: {str(e)}")
                print(f"{Colors.RED}Failed to send alert email: {str(e)}{Colors.END}")
        else:
            if not should_send_email and alert_id in alert_status["active_alerts"]:
                print(f"{Colors.YELLOW}Alert logged, but email suppressed (rate limited - only 1 per {ALERT_COOLDOWN} hour){Colors.END}")
            else:
                print(f"{Colors.YELLOW}Alert logged to logs/alerts.log (Email alerts disabled){Colors.END}")
    
    def check_alert_resolution(self, nickname, hostname, resource_type, current_value, threshold):
        """Check if an alert has been resolved and send resolution notification"""
        # Generate alert ID
        alert_id = self.get_alert_id(nickname, hostname, resource_type.lower())
        
        # Load current alert status
        alert_status = self.load_alert_status()
        
        # If this alert is active and the value is now below threshold, it's resolved
        if alert_id in alert_status["active_alerts"] and current_value < threshold:
            # Move from active to resolved
            resolved_alert = alert_status["active_alerts"][alert_id]
            resolved_alert["resolved_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            alert_status["resolved_alerts"][alert_id] = resolved_alert
            del alert_status["active_alerts"][alert_id]
            
            # Save updated status
            self.save_alert_status(alert_status)
            
            # Log resolution
            logger.info(f"{nickname} ({hostname}): {resource_type} alert resolved - now at {current_value:.1f}%, below threshold of {threshold}%")
            print(f"{Colors.GREEN}{resource_type} alert for {nickname} resolved!{Colors.END}")
            
            # Send resolution email
            self.send_resolution_email(nickname, hostname, resource_type, current_value, threshold, resolved_alert)
    
    def send_resolution_email(self, nickname, hostname, resource_type, current_value, threshold, alert_info):
        """Send an email notification that an alert has been resolved"""
        if not (config and config.get('email', {}).get('enabled', False)):
            return
        
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = config['email']['sender']
            msg['To'] = ", ".join(config['email']['recipients'])
            msg['Subject'] = f"HEIMDALL RESOLVED: {nickname} - {resource_type} issue resolved"
            
            # Calculate problem duration
            first_detected = datetime.strptime(alert_info["first_detected"], "%Y-%m-%d %H:%M:%S")
            resolved_time = datetime.strptime(alert_info["resolved_time"], "%Y-%m-%d %H:%M:%S")
            duration = resolved_time - first_detected
            hours, remainder = divmod(duration.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            duration_str = f"{duration.days} days, {hours} hours, {minutes} minutes" if duration.days > 0 else f"{hours} hours, {minutes} minutes"
            
            # HTML version
            html = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        background-color: #f9f9f9;
                        margin: 0;
                        padding: 0;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 20px auto;
                        padding: 20px;
                        background-color: #fff;
                        border-radius: 5px;
                        border-top: 5px solid #48c774;
                        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                    }}
                    h1 {{
                        color: #48c774;
                        margin-top: 0;
                    }}
                    .logo {{
                        text-align: center;
                        margin-bottom: 20px;
                    }}
                    .logo img {{
                        width: 150px;
                        height: auto;
                    }}
                    .server-info {{
                        background-color: #f5f5f5;
                        padding: 15px;
                        border-radius: 4px;
                        margin: 20px 0;
                    }}
                    .server-name {{
                        font-size: 18px;
                        font-weight: bold;
                        color: #333;
                    }}
                    .server-hostname {{
                        color: #777;
                        font-family: monospace;
                    }}
                    .resolve-message {{
                        font-size: 18px;
                        color: #48c774;
                        background-color: #effaf5;
                        padding: 10px;
                        border-radius: 4px;
                        margin: 15px 0;
                    }}
                    .alert-details {{
                        background-color: #f5f5f5;
                        padding: 12px;
                        border-radius: 4px;
                        margin: 15px 0;
                        font-size: 14px;
                    }}
                    .detail-row {{
                        display: flex;
                        justify-content: space-between;
                        margin-bottom: 5px;
                        border-bottom: 1px solid #eee;
                        padding-bottom: 5px;
                    }}
                    .detail-label {{
                        font-weight: bold;
                    }}
                    .timestamp {{
                        color: #777;
                        font-size: 14px;
                        margin-top: 20px;
                    }}
                    .footer {{
                        margin-top: 30px;
                        padding-top: 20px;
                        border-top: 1px solid #eee;
                        font-size: 12px;
                        color: #777;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="logo">
                        <img src="cid:heimdall_logo" alt="Heimdall Logo">
                    </div>
                    <h1>✅ Alert Resolved</h1>
                    <p>Heimdall has detected that a previous alert has been resolved.</p>
                    
                    <div class="server-info">
                        <div class="server-name">{nickname}</div>
                        <div class="server-hostname">{hostname}</div>
                    </div>
                    
                    <div class="resolve-message">
                        {resource_type} usage has returned to normal levels: {current_value:.1f}% (threshold: {threshold}%)
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
            '''
            
            # Attach HTML part
            msg.attach(MIMEText(html, 'html'))
            
            # Attach the logo image
            try:
                with open("HEIMDALL.png", 'rb') as img_file:
                    img_data = img_file.read()
                    image = MIMEImage(img_data)
                    image.add_header('Content-ID', '<heimdall_logo>')
                    image.add_header('Content-Disposition', 'inline', filename='HEIMDALL.png')
                    msg.attach(image)
            except Exception as e:
                logger.warning(f"Could not attach logo: {str(e)}")
            
            # Connect to SMTP server and send email
            server = smtplib.SMTP(config['email']['smtp_server'], config['email']['smtp_port'])
            
            if config['email']['use_tls']:
                server.starttls()
            
            if config['email']['username'] and config['email']['password']:
                server.login(config['email']['username'], config['email']['password'])
            
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Resolution email sent to {msg['To']}")
            print(f"{Colors.GREEN}Resolution email sent to {msg['To']}{Colors.END}")
        except Exception as e:
            logger.error(f"Failed to send resolution email: {str(e)}")
            print(f"{Colors.RED}Failed to send resolution email: {str(e)}{Colors.END}")

    def interactive_menu(self):
        """Display interactive menu"""
        while True:
            print(f"\n{Colors.GREEN}{Colors.BOLD}Heimdall Server Monitoring{Colors.END}")
            print("="*30)
            print("1. Add a new server")
            print("2. Remove a server")
            print("3. List all servers")
            print("4. Check all servers")
            print("5. Configure SMTP settings")
            print("6. Exit")
            
            option = input("\nSelect an option: ").strip()
            
            if option == '1':
                self.add_server()
            elif option == '2':
                self.remove_server()
            elif option == '3':
                self.list_servers()
            elif option == '4':
                self.check_all_servers()
            elif option == '5':
                configure_smtp()
            elif option == '6':
                print(f"\n{Colors.GREEN}Heimdall will continue watching your realms from Asgard. Farewell!{Colors.END}")
                logger.info("Exiting Heimdall")
                break
            else:
                print(f"\n{Colors.RED}Invalid option, please try again.{Colors.END}")


def configure_smtp():
    """Configure SMTP settings interactively"""
    print(f"\n{Colors.GREEN}{Colors.BOLD}SMTP Configuration{Colors.END}")
    print("="*25)
    
    # Load existing config
    current_config = load_config()
    
    # Get current email settings
    email_config = current_config.get('email', {})
    
    # Ask for SMTP settings
    print("\nPlease enter your SMTP settings (press Enter to keep current value):\n")
    
    # Enable/disable email alerts
    current_enabled = email_config.get('enabled', False)
    enabled_input = input(f"Enable email alerts? (y/n) [{current_enabled and 'y' or 'n'}]: ").strip().lower()
    email_config['enabled'] = enabled_input == 'y' if enabled_input else current_enabled
    
    if email_config['enabled']:
        # SMTP server
        current_server = email_config.get('smtp_server', 'smtp.example.com')
        server_input = input(f"SMTP Server [{current_server}]: ").strip()
        email_config['smtp_server'] = server_input or current_server
        
        # SMTP port
        current_port = email_config.get('smtp_port', 587)
        port_input = input(f"SMTP Port [{current_port}]: ").strip()
        email_config['smtp_port'] = int(port_input) if port_input.isdigit() else current_port
        
        # Use TLS
        current_tls = email_config.get('use_tls', True)
        tls_input = input(f"Use TLS? (y/n) [{current_tls and 'y' or 'n'}]: ").strip().lower()
        email_config['use_tls'] = tls_input == 'y' if tls_input else current_tls
        
        # Username
        current_username = email_config.get('username', '')
        username_input = input(f"SMTP Username [{current_username}]: ").strip()
        email_config['username'] = username_input or current_username
        
        # Password
        password_input = input("SMTP Password (leave empty to keep current): ").strip()
        if password_input:
            email_config['password'] = password_input
        elif 'password' not in email_config:
            email_config['password'] = ''
        
        # Sender
        current_sender = email_config.get('sender', 'heimdall@example.com')
        sender_input = input(f"Sender Email [{current_sender}]: ").strip()
        email_config['sender'] = sender_input or current_sender
        
        # Recipients
        current_recipients = email_config.get('recipients', [])
        current_recipients_str = ', '.join(current_recipients) if current_recipients else 'admin@example.com'
        recipients_input = input(f"Recipients (comma-separated) [{current_recipients_str}]: ").strip()
        email_config['recipients'] = [r.strip() for r in recipients_input.split(',')] if recipients_input else current_recipients
    
    # Update config
    current_config['email'] = email_config
    
    # Save config
    with open(CONFIG_FILE, 'w') as f:
        json.dump(current_config, f, indent=2)
    
    print(f"\n{Colors.GREEN}SMTP configuration saved!{Colors.END}")
    
    # Test email if enabled
    if email_config['enabled']:
        test_input = input("\nSend a test email? (y/n): ").strip().lower()
        if test_input == 'y':
            try:
                msg = MIMEMultipart()
                msg['From'] = email_config['sender']
                msg['To'] = ", ".join(email_config['recipients'])
                msg['Subject'] = "HEIMDALL TEST ALERT"
                
                body = f'''
                This is a test email from Heimdall Monitoring System.
                
                Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                
                If you're receiving this, your SMTP configuration is working correctly!
                '''
                
                msg.attach(MIMEText(body, 'plain'))
                
                # Connect to SMTP server and send email
                server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
                
                if email_config['use_tls']:
                    server.starttls()
                
                if email_config['username'] and email_config['password']:
                    server.login(email_config['username'], email_config['password'])
                
                server.send_message(msg)
                server.quit()
                
                print(f"\n{Colors.GREEN}Test email sent successfully!{Colors.END}")
            except Exception as e:
                print(f"\n{Colors.RED}Failed to send test email: {str(e)}{Colors.END}")


def main():
    parser = argparse.ArgumentParser(
        description='Heimdall - The Watchful Server Monitor',
        epilog='Like the Norse god who watches over Bifröst, Heimdall keeps a vigilant eye on your servers.'
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-i', '--interactive', action='store_true', help='Run in interactive mode')
    group.add_argument('-c', '--check', action='store_true', help='Check all servers (non-interactive)')
    group.add_argument('--configure-smtp', action='store_true', help='Configure SMTP settings interactively')
    
    args = parser.parse_args()
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Log startup
    logger.info("Heimdall starting up")
    
    # Configure SMTP if requested
    if args.configure_smtp:
        configure_smtp()
        return
    
    monitor = ServerMonitor()
    
    if args.interactive:
        logger.info("Starting in interactive mode")
        monitor.interactive_menu()
    elif args.check:
        logger.info("Starting in check mode")
        monitor.check_all_servers()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
