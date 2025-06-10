# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running the Application
```bash
# Interactive mode - manage servers and configuration
./heimdall.py --interactive

# Check all configured servers
./heimdall.py --check

# Configure SMTP settings
./heimdall.py --configure-smtp

# Test email configuration
./heimdall.py --test-email
```

### Development
```bash
# Install dependencies
pip install paramiko

# Run with Python directly
python heimdall.py [options]
```

## Architecture

Heimdall is a server monitoring system that uses SSH to connect to remote servers and monitor resources (CPU, memory, disk) and services.

### Core Components

- **heimdall.py**: Main entry point, handles CLI arguments and interactive menu
- **heimdall/config.py**: Manages server configurations (servers.json) and application settings (config.json)
- **heimdall/monitor.py**: Core monitoring logic - SSH connections, resource checks, service monitoring
- **heimdall/alerts.py**: Alert management - tracks alert state, sends email notifications, manages cooldowns
- **heimdall/utils.py**: Logging setup and terminal color utilities

### Data Flow

1. User runs heimdall.py with --check or selects check from interactive menu
2. ServerMonitor connects to each server via SSH (using paramiko)
3. Executes commands to check CPU (top), memory (free), disk (df), and services (systemctl/service)
4. AlertManager evaluates thresholds and manages alert state
5. Sends email notifications for new alerts or resolutions (respecting cooldown periods)

### Key Implementation Details

- **SSH Authentication**: Supports both SSH key (preferred) and password authentication
- **Alert State**: Tracked in alert_status.json to prevent duplicate alerts and track resolutions
- **Filesystem Monitoring**: Intelligently skips special filesystems (squashfs, snap mounts)
- **Service Detection**: Automatically detects available services using systemctl or service commands
- **Email Templates**: HTML-formatted emails with embedded Heimdall logo

### Configuration Files

- **config.json**: Application settings (email config, thresholds, intervals)
- **servers.json**: List of servers to monitor with their SSH credentials
- **alert_status.json**: Current alert state (auto-generated)

### Testing Changes

When modifying monitoring logic:
1. Test with a single server first using interactive mode
2. Verify email alerts work with --test-email
3. Check logs in logs/ directory for debugging
4. Ensure special filesystems are properly skipped
5. Test both systemd and non-systemd service detection