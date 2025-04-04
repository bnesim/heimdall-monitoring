#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Server monitoring module for Heimdall.

This module handles the core server monitoring functionality,
including SSH connections and resource checks.
"""

import os
import socket
import paramiko
import logging
from .utils import Colors
from .alerts import AlertManager

logger = logging.getLogger("Heimdall")

class ServerMonitor:
    def __init__(self, config, server_config):
        self.config = config
        self.server_config = server_config
        self.alert_manager = AlertManager(config)
        
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
    
    def check_server(self, server):
        """Check a single server for CPU, memory and disk usage."""
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
            cpu_output = stdout.read().decode('utf-8').strip()
            
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
            mem_output = stdout.read().decode('utf-8').strip()
            
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
                "df -h | grep -v tmpfs | grep -v devtmpfs | grep -v Filesystem")
            disk_output_all = stdout.read().decode('utf-8').strip().split('\n')
            
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
                
                # Send alerts for critical disks
                for disk in critical_disks:
                    alert_msg = f"Disk usage for {disk['mount']} at {disk['usage']:.1f}%, threshold is {self.disk_threshold}%"
                    logger.warning(f"{nickname} ({hostname}): {alert_msg}")
                    self.alert_manager.send_alert(nickname, hostname, alert_msg,
                        alert_type=f"disk:{disk['mount']}")
            else:
                logger.error(f"{nickname} ({hostname}): Failed to get disk data")
                print(Colors.red("  Failed to get Disk data"))
            
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