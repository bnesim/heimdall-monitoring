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
import time
import json
import logging
import argparse
import paramiko
from heimdall.config import load_config, ServerConfig, CONFIG_FILE
from heimdall.monitor import ServerMonitor
from heimdall.utils import setup_logging, Colors, LOG_FILE
from heimdall.alerts import AlertManager

# Setup logging
logger = setup_logging()

def interactive_menu(monitor):
    """Display interactive menu"""
    server_config = monitor.server_config
    
    while True:
        print(f"\n{Colors.green(Colors.bold('Heimdall Server Monitoring'))}")
        print("="*30)
        print("1. Add a new server")
        print("2. Remove a server")
        print("3. Edit a server (add/remove services)")
        print("4. List all servers")
        print("5. Check all servers")
        print("6. Configure SMTP settings")
        print("7. Configure Telegram bot")
        print("8. Exit")
        
        option = input("\nSelect an option: ").strip()
        
        if option == '1':
            add_server(monitor)
        elif option == '2':
            remove_server(server_config)
        elif option == '3':
            edit_server(monitor)
        elif option == '4':
            list_servers(server_config)
        elif option == '5':
            monitor.check_all_servers()
        elif option == '6':
            configure_smtp()
        elif option == '7':
            configure_telegram()
        elif option == '8':
            print(f"\n{Colors.green('Heimdall will continue watching your realms from Asgard. Farewell!')}")
            logger.info("Exiting Heimdall")
            break
        else:
            print(f"\n{Colors.red('Invalid option, please try again.')}")


def add_server(monitor):
    """Add a new server interactively"""
    print(f"\n{Colors.green(Colors.bold('Add New Server'))}")
    print("="*20)
    
    hostname = input("Server Hostname/IP: ").strip()
    if not hostname:
        print(f"{Colors.red('Error: Hostname cannot be empty')}")
        return
        
    port_input = input("SSH Port (default: 22): ").strip()
    port = 22 if not port_input else int(port_input)
    
    username = input("Username (default: root): ").strip() or "root"
    
    # Ask for authentication method
    print(f"\n{Colors.blue('Authentication Method:')}")
    print("1. SSH Key (recommended)")
    print("2. Password")
    auth_method = input("Select authentication method [1]: ").strip() or "1"
    
    password = None
    key_path = None
    
    if auth_method == "1":
        key_path = input("SSH Key Path (default: ~/.ssh/id_rsa): ").strip() or os.path.expanduser("~/.ssh/id_rsa")
        if not os.path.exists(key_path):
            print(f"{Colors.yellow('Warning: SSH key file not found: ' + key_path)}")
            use_password = input("Would you like to use password authentication instead? (y/n): ").strip().lower()
            if use_password == 'y':
                password = input("Password: ").strip()
            else:
                print(f"{Colors.red('Cannot proceed without valid authentication.')}")
                return
    else:
        password = input("Password: ").strip()
    
    # Test connection
    if not monitor.test_ssh_connection(hostname, port, username, password, key_path):
        print(f"\n{Colors.red('Server not added.')}")
        return
    
    # Get the real hostname for nickname
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
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
        
        client.connect(**connect_params)
        
        # Get the real hostname
        stdin, stdout, stderr = client.exec_command("hostname")
        real_hostname = stdout.read().decode('utf-8').strip()
        
        # If we got a hostname, use it as the nickname
        if real_hostname:
            nickname = real_hostname
            print(f"\nDetected server hostname: {Colors.green(nickname)}")
        else:
            # Fall back to using the IP/hostname as the nickname
            nickname = hostname
            print(f"\nCouldn't detect hostname, using: {Colors.yellow(nickname)}")
        
        # Let user select services to monitor
        monitored_services = monitor.select_services_to_monitor(hostname, port, username, password, key_path)
        
        # Create server data
        server_data = {
            'hostname': hostname,
            'port': port,
            'username': username,
            'nickname': nickname,
            'monitored_services': monitored_services
        }
        
        # Add authentication details
        if key_path and os.path.exists(key_path):
            server_data['key_path'] = key_path
        if password:
            server_data['password'] = password
        
        # Add the server to configuration
        monitor.server_config.add_server(server_data)
        
        if monitored_services:
            print(f"\n{Colors.green('Server ' + nickname + ' added successfully with ' + str(len(monitored_services)) + ' monitored services!')}")
        else:
            print(f"\n{Colors.green('Server ' + nickname + ' added successfully!')}")
        
        return True
    except Exception as e:
        logger.error(f"Error adding server {hostname}: {str(e)}")
        print(f"\n{Colors.red('Error: ' + str(e))}")
        print(f"\n{Colors.red('Server not added.')}")
        return False


def remove_server(server_config):
    """Remove a server interactively"""
    servers = server_config.get_servers()
    if not servers:
        print(f"\n{Colors.yellow('No servers configured yet.')}")
        return
        
    print(f"\n{Colors.yellow(Colors.bold('Remove Server'))}")
    print("="*20)
    
    list_servers(server_config)
    
    selection = input("\nEnter the number of the server to remove: ").strip()
    
    # Find the server by number
    try:
        index = int(selection) - 1  # Convert to 0-based index
        if 0 <= index < len(servers):
            server = servers[index]
            nickname = server['nickname']  # Get the nickname for later use
            
            # Remove the server
            if server_config.remove_server(nickname):
                print(f"\n{Colors.green('Server ' + nickname + ' removed successfully!')}")
            else:
                print(f"\n{Colors.red('Failed to remove server ' + nickname)}")
        else:
            logger.warning(f"Server index out of range: {selection}")
            print(f"\n{Colors.red('Invalid server number. Please enter a number between 1 and ' + str(len(servers)) + '.')}")
    except ValueError:
        logger.warning(f"Invalid server selection: {selection}")
        print(f"\n{Colors.red('Please enter a valid server number.')}")


def list_servers(server_config):
    """List all configured servers"""
    servers = server_config.get_servers()
    if not servers:
        print(f"\n{Colors.yellow('No servers configured yet.')}")
        return
        
    print(f"\n{Colors.green(Colors.bold('Server List'))}")
    print("="*20)
    
    for i, server in enumerate(servers):
        print(f"  {i+1}. {Colors.bold(server['nickname'])} - {server['hostname']}:{server['port']} ({server['username']})")


def edit_server(monitor):
    """Edit a server to add/remove monitored services"""
    server_config = monitor.server_config
    servers = server_config.get_servers()
    
    if not servers:
        print(f"\n{Colors.yellow('No servers configured yet.')}")
        return
        
    print(f"\n{Colors.blue(Colors.bold('Edit Server'))}")
    print("="*20)
    
    list_servers(server_config)
    
    selection = input("\nEnter the number of the server to edit: ").strip()
    
    # Find the server by number
    try:
        index = int(selection) - 1  # Convert to 0-based index
        if 0 <= index < len(servers):
            server = servers[index]
            nickname = server['nickname']  # Get the nickname for later use
        else:
            logger.warning(f"Server index out of range: {selection}")
            print(f"\n{Colors.red('Invalid server number. Please enter a number between 1 and ' + str(len(servers)) + '.')}")
            return
    except ValueError:
        logger.warning(f"Invalid server selection: {selection}")
        print(f"\n{Colors.red('Please enter a valid server number.')}")
        return
    
    # Connect to the server
    hostname = server['hostname']
    port = server['port']
    username = server['username']
    password = server.get('password')
    key_path = server.get('key_path')
    
    print(f"\nConnecting to {hostname}:{port} with user {username}...")
    
    try:
        # Get running services
        print(f"\n{Colors.blue('Getting running services...')}")
        services = monitor.select_services_to_monitor(hostname, port, username, password, key_path)
        
        if services:
            # Update the server's monitored services
            if monitor.server_config.update_server_services(nickname, services):
                print(f"\n{Colors.green('Server ' + nickname + ' updated successfully with ' + str(len(services)) + ' monitored services!')}")
            else:
                print(f"\n{Colors.red('Failed to update server ' + nickname)}")
        else:
            print(f"\n{Colors.yellow('No services selected. Server not updated.')}")
            
    except Exception as e:
        logger.error(f"Error editing server {nickname}: {str(e)}")
        print(f"\n{Colors.red('Failed to connect to server: ' + str(e))}")
        print(f"\n{Colors.red('Server not updated.')}")


def configure_telegram():
    """Configure Telegram bot settings interactively"""
    print(f"\n{Colors.green(Colors.bold('Configure Telegram Bot'))}")
    print("="*30)
    
    # Load current config
    current_config = load_config()
    if not current_config:
        print(f"{Colors.red('Error loading configuration')}")
        return
    
    # Get current Telegram settings
    telegram_config = current_config.get('telegram', {})
    
    # Display current settings
    if telegram_config:
        print(f"\n{Colors.blue('Current Telegram settings:')}")
        print(f"  Enabled: {Colors.green('Yes') if telegram_config.get('enabled') else Colors.red('No')}")
        print(f"  Bot Token: {'*' * 10 + telegram_config.get('bot_token', '')[-4:] if telegram_config.get('bot_token') else 'Not set'}")
        print(f"  Subscribers: {len(telegram_config.get('subscribers', []))}")
    else:
        print(f"  {Colors.yellow('No Telegram settings found')}")
    
    # Ask if user wants to update settings
    update = input("\nDo you want to update Telegram settings? (y/n): ").strip().lower()
    if update != 'y':
        return
    
    # Update settings
    if 'telegram' not in current_config:
        current_config['telegram'] = {}
    
    telegram_config = current_config['telegram']
    
    # Enable/disable Telegram alerts
    enable = input("Enable Telegram alerts? (y/n): ").strip().lower()
    telegram_config['enabled'] = (enable == 'y')
    
    if enable == 'y':
        # Bot token
        print(f"\n{Colors.blue('To create a Telegram bot:')}")
        print("1. Open Telegram and search for @BotFather")
        print("2. Send /newbot and follow the instructions")
        print("3. Copy the bot token provided by BotFather")
        
        token_input = input("\nBot Token (leave empty to keep current): ").strip()
        if token_input:
            telegram_config['bot_token'] = token_input
        
        # Keep existing subscribers
        if 'subscribers' not in telegram_config:
            telegram_config['subscribers'] = []
    
    # Save config
    with open(CONFIG_FILE, 'w') as f:
        json.dump(current_config, f, indent=2)
    
    print(f"\n{Colors.green('Telegram settings updated successfully!')}")
    
    # Test bot connection if enabled
    if telegram_config['enabled'] and telegram_config.get('bot_token'):
        test = input("\nDo you want to test the Telegram bot connection? (y/n): ").strip().lower()
        if test == 'y':
            try:
                from heimdall.telegram import TelegramBot
                bot = TelegramBot(current_config)
                success, info = bot.test_connection()
                
                if success:
                    print(f"\n{Colors.green('Bot connected successfully!')}")
                    print(f"Bot name: @{info.get('username', 'Unknown')}")
                    print(f"\n{Colors.blue('To subscribe to alerts:')}")
                    print(f"1. Open Telegram and search for @{info.get('username', 'your_bot')}")
                    print("2. Send /start to the bot")
                    print("3. The bot will confirm your subscription")
                else:
                    print(f"\n{Colors.red('Failed to connect to bot: ' + str(info))}")
            except Exception as e:
                logger.error(f"Error testing Telegram bot: {str(e)}")
                print(f"\n{Colors.red('Error testing bot: ' + str(e))}")
    
    # Send test message if there are subscribers
    if telegram_config['enabled'] and telegram_config.get('bot_token') and telegram_config.get('subscribers'):
        test_msg = input("\nDo you want to send a test message to all subscribers? (y/n): ").strip().lower()
        if test_msg == 'y':
            try:
                # Create alert manager
                alert_manager = AlertManager(current_config)
                
                # Send test message
                if alert_manager.send_test_telegram():
                    print(f"\n{Colors.green('Test message sent successfully!')}")
                else:
                    print(f"\n{Colors.red('Failed to send test message.')}")
            except Exception as e:
                logger.error(f"Error sending test message: {str(e)}")
                print(f"\n{Colors.red('Error sending test message: ' + str(e))}")


def configure_smtp():
    """Configure SMTP settings interactively"""
    print(f"\n{Colors.green(Colors.bold('SMTP Configuration'))}")
    print("="*25)
    
    # Load existing config
    current_config = load_config()
    
    # Get current email settings
    email_config = current_config.get('email', {})
    
    # Display current settings
    print("\nCurrent SMTP Settings:")
    if current_config and 'email' in current_config:
        email_config = current_config['email']
        print(f"  Enabled: {Colors.green('Yes') if email_config.get('enabled') else Colors.red('No')}")
        print(f"  SMTP Server: {email_config.get('smtp_server', 'Not set')}")
        print(f"  SMTP Port: {email_config.get('smtp_port', 'Not set')}")
        print(f"  Use TLS: {Colors.green('Yes') if email_config.get('use_tls') else Colors.red('No')}")
        print(f"  Username: {email_config.get('username', 'Not set')}")
        print(f"  Sender: {email_config.get('sender', 'Not set')}")
        recipients = email_config.get('recipients', [])
        print(f"  Recipients: {', '.join(recipients) if recipients else 'None'}")
    else:
        print(f"  {Colors.yellow('No SMTP settings found')}")
    
    # Ask if user wants to update settings
    update = input("\nDo you want to update SMTP settings? (y/n): ").strip().lower()
    if update != 'y':
        return
    
    # Update settings
    if not current_config:
        current_config = {}
    if 'email' not in current_config:
        current_config['email'] = {}
    
    email_config = current_config['email']
    
    # Enable/disable email alerts
    enable = input("Enable email alerts? (y/n): ").strip().lower()
    email_config['enabled'] = (enable == 'y')
    
    if enable == 'y':
        # SMTP server
        email_config['smtp_server'] = input(f"SMTP Server [{email_config.get('smtp_server', 'smtp.example.com')}]: ").strip() or email_config.get('smtp_server', 'smtp.example.com')
        
        # SMTP port
        port_input = input(f"SMTP Port [{email_config.get('smtp_port', 587)}]: ").strip()
        email_config['smtp_port'] = int(port_input) if port_input else email_config.get('smtp_port', 587)
        
        # Use TLS
        use_tls = input(f"Use TLS? (y/n) [{email_config.get('use_tls', True) and 'y' or 'n'}]: ").strip().lower()
        email_config['use_tls'] = (use_tls == 'y' or (not use_tls and email_config.get('use_tls', True)))
        
        # Username
        email_config['username'] = input(f"SMTP Username [{email_config.get('username', 'user@example.com')}]: ").strip() or email_config.get('username', 'user@example.com')
        
        # Password
        password = input("SMTP Password (leave empty to keep current): ").strip()
        if password:
            email_config['password'] = password
        
        # Sender
        email_config['sender'] = input(f"Sender Email [{email_config.get('sender', 'heimdall@example.com')}]: ").strip() or email_config.get('sender', 'heimdall@example.com')
        
        # Recipients
        current_recipients = ', '.join(email_config.get('recipients', ['admin@example.com']))
        recipients_input = input(f"Recipients (comma separated) [{current_recipients}]: ").strip()
        if recipients_input:
            email_config['recipients'] = [r.strip() for r in recipients_input.split(',')]
    
    # Save config
    with open(CONFIG_FILE, 'w') as f:
        json.dump(current_config, f, indent=2)
    
    print(f"\n{Colors.green('SMTP settings updated successfully!')}")
    
    # Test email if enabled
    if email_config['enabled']:
        test = input("\nDo you want to send a test email? (y/n): ").strip().lower()
        if test == 'y':
            try:
                # Create alert manager
                alert_manager = AlertManager(current_config)
                
                # Send test email
                if alert_manager.send_test_email():
                    print(f"\n{Colors.green('Test email sent successfully!')}")
                else:
                    print(f"\n{Colors.red('Failed to send test email.')}")
            except Exception as e:
                logger.error(f"Error sending test email: {str(e)}")
                print(f"\n{Colors.red('Error sending test email: ' + str(e))}")


def main():
    parser = argparse.ArgumentParser(
        description='Heimdall - The Watchful Server Monitor',
        epilog='Like the Norse god who watches over Bifröst, Heimdall keeps a vigilant eye on your servers.'
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-i', '--interactive', action='store_true', help='Run in interactive mode')
    group.add_argument('-c', '--check', action='store_true', help='Check all servers (non-interactive)')
    group.add_argument('--configure-smtp', action='store_true', help='Configure SMTP settings interactively')
    group.add_argument('--configure-telegram', action='store_true', help='Configure Telegram bot settings interactively')
    group.add_argument('--test-email', action='store_true', help='Send a test email to verify SMTP settings')
    group.add_argument('--test-telegram', action='store_true', help='Send a test Telegram message to all subscribers')
    
    args = parser.parse_args()
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Log startup
    logger.info("Heimdall starting up")
    
    # Configure SMTP if requested
    if args.configure_smtp:
        configure_smtp()
        return
    
    # Configure Telegram if requested
    if args.configure_telegram:
        configure_telegram()
        return
    
    # Load configuration
    config = load_config()
    
    # Test email if requested
    if args.test_email:
        if config and config.get('email', {}).get('enabled', False):
            alert_manager = AlertManager(config)
            if alert_manager.send_test_email():
                print(f"{Colors.green('Test email sent successfully!')}")
            else:
                print(f"{Colors.red('Failed to send test email.')}")
        else:
            print(f"{Colors.red('Email alerts are not enabled. Use --configure-smtp to enable.')}")
        return
    
    # Test Telegram if requested
    if args.test_telegram:
        if config and config.get('telegram', {}).get('enabled', False) and config.get('telegram', {}).get('bot_token'):
            alert_manager = AlertManager(config)
            if alert_manager.send_test_telegram():
                print(f"{Colors.green('Test message sent successfully!')}")
            else:
                print(f"{Colors.red('Failed to send test message.')}")
        else:
            print(f"{Colors.red('Telegram alerts are not enabled. Use --configure-telegram to enable.')}")
        return
    
    server_config = ServerConfig()
    
    # Create a monitor instance from the heimdall.monitor module
    monitor = ServerMonitor(config, server_config)
    
    if args.interactive:
        logger.info("Starting in interactive mode")
        interactive_menu(monitor)
    elif args.check:
        logger.info("Starting in check mode")
        monitor.check_all_servers()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
