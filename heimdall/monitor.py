#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Server monitoring module for Heimdall.

This module handles the core server monitoring functionality,
including SSH connections, resource checks, and service monitoring.
"""

import os
import socket
import paramiko
import logging
from .utils import Colors
from .alerts import AlertManager
from .ai_assistant import AIAssistant

logger = logging.getLogger("Heimdall")

class ServerMonitor:
    def __init__(self, config, server_config):
        self.config = config
        self.server_config = server_config
        self.alert_manager = AlertManager(config)
        self.ai_assistant = AIAssistant(config)
        
        # Set thresholds
        self.cpu_threshold = config['thresholds']['cpu'] if config else 80
        self.mem_threshold = config['thresholds']['memory'] if config else 80
        self.disk_threshold = config['thresholds']['disk'] if config else 85
    
    def test_ssh_connection(self, hostname, port, username, password=None, key_path=None):
        """Test SSH connection to a server using password or SSH key."""
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
            if key_path:
                if os.path.exists(key_path):
                    connect_params['key_filename'] = key_path
                else:
                    logger.warning(f"SSH key file not found: {key_path}")
                    # Fall back to password if provided
                    if password:
                        connect_params['password'] = password
            # Otherwise use password authentication
            elif password:
                connect_params['password'] = password
            
            client.connect(**connect_params)
            client.close()
            return True
        except Exception as e:
            logger.error(f"SSH connection error to {hostname}: {str(e)}")
            print(Colors.red(f"SSH connection error: {str(e)}"))
            return False
    
    def get_running_services(self, client):
        """Get a list of running services on the server."""
        try:
            # Use systemctl to list running services on systemd-based systems
            # Set LANG=C to avoid Unicode characters in output
            stdin, stdout, stderr = client.exec_command("LANG=C LC_ALL=C systemctl list-units --type=service --state=running --no-pager --no-legend | grep \".service\" | awk '{print $1}'")
            systemd_services = stdout.read().decode('utf-8', errors='replace').strip().split('\n')
            
            # If no systemd services found, try using service command for older systems
            if not systemd_services or systemd_services == ['']:
                stdin, stdout, stderr = client.exec_command("LANG=C LC_ALL=C service --status-all 2>&1 | grep '\[ + \]' | awk '{print $4}'")
                sysv_services = stdout.read().decode('utf-8', errors='replace').strip().split('\n')
                if sysv_services and sysv_services != ['']:
                    return sysv_services
            else:
                return [s.replace('.service', '') for s in systemd_services if s]
                
            # As a last resort, try using ps to find processes that might be services
            stdin, stdout, stderr = client.exec_command("LANG=C LC_ALL=C ps -eo comm= | sort | uniq")
            processes = stdout.read().decode('utf-8', errors='replace').strip().split('\n')
            return [p for p in processes if p and not p.startswith('[')][:20]  # Limit to first 20 to avoid overwhelming
            
        except Exception as e:
            logger.error(f"Error getting running services: {str(e)}")
            return []
    
    def select_services_to_monitor(self, hostname, port, username, password=None, key_path=None):
        """Connect to server and let user select which services to monitor."""
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
            if key_path:
                if os.path.exists(key_path):
                    connect_params['key_filename'] = key_path
                else:
                    logger.warning(f"SSH key file not found: {key_path}")
                    # Fall back to password if provided
                    if password:
                        connect_params['password'] = password
            # Otherwise use password authentication
            elif password:
                connect_params['password'] = password
            
            client.connect(**connect_params)
            
            # Get running services
            services = self.get_running_services(client)
            client.close()
            
            if not services:
                print(Colors.yellow("No services found on the server."))
                return []
            
            print(f"\n{Colors.bold(Colors.blue('Select services to monitor:'))}")
            print("Select services by entering their numbers separated by spaces.")
            print("For example: 1 3 5")
            
            # Display services with numbers
            for i, service in enumerate(services):
                print(f"  {i+1}. {service}")
            
            # Get user selection
            selection = input("\nEnter numbers of services to monitor (or 'all' for all): ").strip()
            
            if selection.lower() == 'all':
                return services
            
            try:
                selected_indices = [int(x) - 1 for x in selection.split()]
                return [services[i] for i in selected_indices if 0 <= i < len(services)]
            except (ValueError, IndexError):
                print(Colors.red("Invalid selection. No services will be monitored."))
                return []
                
        except Exception as e:
            logger.error(f"Error connecting to server to select services: {str(e)}")
            print(Colors.red(f"Error connecting to server: {str(e)}"))
            return []
    
    def check_service_status(self, client, service):
        """Check if a service is running on the server."""
        try:
            # Try systemctl first (for systemd systems)
            stdin, stdout, stderr = client.exec_command(f"LANG=C LC_ALL=C systemctl is-active {service} 2>/dev/null || echo 'inactive'")
            status = stdout.read().decode('utf-8', errors='replace').strip()
            
            if status == 'inactive':
                # Try service command for older systems
                stdin, stdout, stderr = client.exec_command(f"LANG=C LC_ALL=C service {service} status 2>/dev/null | grep -q 'running' && echo 'active' || echo 'inactive'")
                status = stdout.read().decode('utf-8', errors='replace').strip()
                
                if status == 'inactive':
                    # Last resort: check if process is running
                    stdin, stdout, stderr = client.exec_command(f"LANG=C LC_ALL=C ps -ef | grep -v grep | grep -q '{service}' && echo 'active' || echo 'inactive'")
                    status = stdout.read().decode('utf-8', errors='replace').strip()
            
            return status == 'active'
            
        except Exception as e:
            logger.error(f"Error checking service status for {service}: {str(e)}")
            return False
    
    def check_server(self, server):
        """Check a single server for CPU, memory, disk usage, and monitored services."""
        hostname = server['hostname']
        port = server['port']
        username = server['username']
        password = server.get('password')
        key_path = server.get('key_path')
        nickname = server['nickname']
        
        print(f"\n{Colors.bold(Colors.yellow('Checking server:'))} {Colors.green(nickname)} ({hostname})")
        logger.info(f"Checking server: {nickname} ({hostname})")
        
        # Check if the server is reachable
        try:
            socket.create_connection((hostname, port), timeout=5)
        except Exception as e:
            error_msg = f"Server is not reachable: {str(e)}"
            logger.error(f"{nickname} ({hostname}): {error_msg}")
            print(Colors.red(f"ERROR: {error_msg}"))
            self.alert_manager.send_alert(nickname, hostname, error_msg)
            return False
        
        # SSH connection and checks
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            print(f"SSH Connection: ", end='')
            
            # Connection parameters
            connect_params = {
                'hostname': hostname,
                'port': port,
                'username': username,
                'timeout': 5
            }
            
            # Try SSH key authentication if key_path is provided
            if key_path:
                if os.path.exists(key_path):
                    connect_params['key_filename'] = key_path
                else:
                    logger.warning(f"SSH key file not found: {key_path}, falling back to password")
                    if password:
                        connect_params['password'] = password
            # Otherwise use password authentication
            elif password:
                connect_params['password'] = password
            
            client.connect(**connect_params)
            print(Colors.green("Success"))
            
            # Check CPU usage
            print(f"CPU Usage: ", end='')
            stdin, stdout, stderr = client.exec_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}'")
            cpu_output = stdout.read().decode('utf-8', errors='replace').strip()
            
            if cpu_output:
                cpu_usage = float(cpu_output)
                if cpu_usage >= self.cpu_threshold:
                    logger.warning(f"{nickname} ({hostname}): High CPU usage: {cpu_usage:.1f}%")
                    print(Colors.red(f"{cpu_usage:.1f}% (ALERT - above threshold)"))
                    self.alert_manager.send_alert(nickname, hostname, 
                        f"CPU usage at {cpu_usage:.1f}%, threshold is {self.cpu_threshold}%")
                else:
                    logger.info(f"{nickname} ({hostname}): CPU usage: {cpu_usage:.1f}%")
                    print(Colors.green(f"{cpu_usage:.1f}%"))
                    self.alert_manager.check_alert_resolution(nickname, hostname, "CPU", 
                        cpu_usage, self.cpu_threshold)
            else:
                logger.error(f"{nickname} ({hostname}): Failed to get CPU data")
                print(Colors.red("Failed to get CPU data"))
            
            # Check Memory usage
            print(f"Memory Usage: ", end='')
            stdin, stdout, stderr = client.exec_command("free | grep Mem")
            mem_output = stdout.read().decode('utf-8', errors='replace').strip()
            
            if mem_output:
                mem_parts = mem_output.split()
                mem_total = int(mem_parts[1])
                mem_used = int(mem_parts[2])
                mem_usage = (mem_used * 100) / mem_total
                
                if mem_usage >= self.mem_threshold:
                    logger.warning(f"{nickname} ({hostname}): High memory usage: {mem_usage:.1f}%")
                    print(Colors.red(f"{mem_usage:.1f}% (ALERT - above threshold)"))
                    self.alert_manager.send_alert(nickname, hostname, 
                        f"Memory usage at {mem_usage:.1f}%, threshold is {self.mem_threshold}%")
                else:
                    logger.info(f"{nickname} ({hostname}): Memory usage: {mem_usage:.1f}%")
                    print(Colors.green(f"{mem_usage:.1f}%"))
                    self.alert_manager.check_alert_resolution(nickname, hostname, "Memory", 
                        mem_usage, self.mem_threshold)
            else:
                logger.error(f"{nickname} ({hostname}): Failed to get memory data")
                print(Colors.red("Failed to get Memory data"))
            
            # Check Disk usage
            print(f"Disk Usage: ")
            stdin, stdout, stderr = client.exec_command(
                "df -h | grep -v tmpfs | grep -v devtmpfs |grep -v snapd | grep -v Filesystem")
            disk_output_all = stdout.read().decode('utf-8', errors='replace').strip().split('\n')
            
            if disk_output_all:
                critical_disks = []
                
                for disk_line in disk_output_all:
                    if not disk_line.strip():
                        continue
                    
                    parts = disk_line.split()
                    if len(parts) >= 5:
                        filesystem = parts[0]
                        mount_point = parts[5] if len(parts) >= 6 else parts[0]
                        usage_str = parts[4].rstrip('%')
                        
                        # Skip monitoring for special filesystems that are expected to be full
                        should_skip = False
                        
                        # Skip if filesystem is squashfs (typically read-only and 100% full)
                        if 'squashfs' in filesystem.lower():
                            should_skip = True
                            logger.debug(f"Skipping squashfs filesystem: {filesystem} at {mount_point}")
                            print(f"  {mount_point}: {Colors.yellow(f'Skipped (squashfs)')}")
                            
                        # Skip if filesystem is a snap (typically read-only and 100% full)
                        if '/snap/' in mount_point or mount_point.startswith('/snap'):
                            should_skip = True
                            logger.debug(f"Skipping snap filesystem: {filesystem} at {mount_point}")
                            print(f"  {mount_point}: {Colors.yellow(f'Skipped (snap)')}")
                        
                        if not should_skip:
                            try:
                                disk_usage = float(usage_str)
                                
                                if disk_usage >= self.disk_threshold:
                                    critical_disks.append({
                                        "mount": mount_point,
                                        "usage": disk_usage,
                                        "filesystem": filesystem
                                    })
                                    print(f"  {mount_point}: {Colors.red(f'{disk_usage:.1f}% (ALERT - above threshold)')}")
                                else:
                                    print(f"  {mount_point}: {Colors.green(f'{disk_usage:.1f}%')}")
                                    self.alert_manager.check_alert_resolution(
                                        nickname, hostname, f"Disk ({mount_point})",
                                        disk_usage, self.disk_threshold)
                            except ValueError:
                                print(f"  {mount_point}: {Colors.yellow('Unable to parse usage')}")
                
                # Send alerts for critical disks with AI suggestions
                for disk in critical_disks:
                    alert_msg = f"Disk usage for {disk['mount']} at {disk['usage']:.1f}%, threshold is {self.disk_threshold}%"
                    
                    # Get AI suggestion if OpenRouter is configured
                    # Always try to get AI analysis for disk alerts (not just new ones)
                    ai_suggestion = None
                    if self.ai_assistant.is_configured():
                        try:
                            print(f"  Getting AI analysis for {disk['mount']}...")
                            
                            # Get df -h output for this specific filesystem
                            stdin, stdout, stderr = client.exec_command(f"df -h {disk['mount']}")
                            df_output = stdout.read().decode('utf-8', errors='replace').strip()
                            
                            # Get du -sh output for top directories
                            # For root filesystem, use a more targeted approach to avoid long scans
                            if disk['mount'] == '/':
                                # Check specific directories that commonly grow large
                                du_command = "du -sh /var /tmp /home /opt /usr /root 2>/dev/null | sort -rh"
                            else:
                                du_command = f"du -sh {disk['mount']}/* 2>/dev/null | sort -rh | head -20"
                            
                            print(f"    Running disk analysis...")
                            try:
                                stdin, stdout, stderr = client.exec_command(du_command, timeout=30)
                                du_output = stdout.read().decode('utf-8', errors='replace').strip()
                            except Exception as e:
                                logger.warning(f"Disk analysis command timed out or failed: {str(e)}")
                                du_output = ""
                            
                            # If du command failed or timed out, try a simpler command
                            if not du_output or len(du_output) < 10:
                                print(f"    Using quick analysis mode...")
                                # Just get the largest subdirectories without recursion
                                if disk['mount'] == '/':
                                    du_command = "ls -la / | grep '^d' | awk '{print $9}' | grep -v '^\\.\\.$' | xargs -I {} du -sh /{} 2>/dev/null | sort -rh | head -10"
                                else:
                                    du_command = f"ls -la {disk['mount']} | grep '^d' | awk '{{print $9}}' | grep -v '^\\.\\.$$' | xargs -I {{}} du -sh {disk['mount']}/{{}} 2>/dev/null | sort -rh | head -10"
                                stdin, stdout, stderr = client.exec_command(du_command, timeout=10)
                                du_output = stdout.read().decode('utf-8', errors='replace').strip()
                            
                            # Get AI analysis
                            ai_suggestion = self.ai_assistant.analyze_disk_usage(
                                nickname, disk['filesystem'], disk['usage'], 
                                du_output, df_output
                            )
                            
                            if ai_suggestion:
                                # Format and append AI suggestion to alert message
                                formatted_suggestion = self.ai_assistant.format_suggestion_for_alert(ai_suggestion)
                                alert_msg += formatted_suggestion
                                print(f"  {Colors.green('AI analysis completed')}")
                            else:
                                print(f"  {Colors.yellow('AI analysis not available')}")
                                
                        except Exception as e:
                            logger.error(f"Error getting AI suggestion: {str(e)}")
                            print(f"  {Colors.yellow('AI analysis failed')}")
                    
                    logger.warning(f"{nickname} ({hostname}): {alert_msg}")
                    self.alert_manager.send_alert(nickname, hostname, alert_msg,
                        alert_type=f"disk:{disk['mount']}")
            else:
                logger.error(f"{nickname} ({hostname}): Failed to get disk data")
                print(Colors.red("  Failed to get Disk data"))
            
            # Check monitored services if any are configured
            if 'monitored_services' in server and server['monitored_services']:
                print(f"\nMonitored Services:")
                services_down = []
                
                for service in server['monitored_services']:
                    print(f"  {service}: ", end='')
                    is_running = self.check_service_status(client, service)
                    
                    if is_running:
                        print(Colors.green("Running"))
                        # Check if this resolves an existing alert
                        self.alert_manager.check_alert_resolution(nickname, hostname, 
                            f"Service ({service})", 0, 1)
                    else:
                        print(Colors.red("Not Running"))
                        services_down.append(service)
                        alert_msg = f"Service {service} is not running"
                        logger.warning(f"{nickname} ({hostname}): {alert_msg}")
                        self.alert_manager.send_alert(nickname, hostname, alert_msg, 
                            alert_type=f"service:{service}")
                
                if not services_down:
                    print(Colors.green("All monitored services are running"))
            
            client.close()
            return True
            
        except Exception as e:
            error_msg = f"Error checking server: {str(e)}"
            logger.error(f"{nickname} ({hostname}): {error_msg}")
            print(Colors.red(error_msg))
            self.alert_manager.send_alert(nickname, hostname, error_msg)
            return False
    
    def check_all_servers(self):
        """Check all configured servers."""
        servers = self.server_config.get_servers()
        if not servers:
            logger.warning("No servers configured")
            print(f"\n{Colors.yellow('No servers configured. Use interactive mode to add servers.')}")
            return
        
        print(f"\n{Colors.bold(Colors.green('Checking All Servers'))}")
        print("=" * 25)
        logger.info(f"Starting check of all servers ({len(servers)} total)")
        
        for server in servers:
            self.check_server(server)