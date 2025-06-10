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

# Configure Telegram bot
./heimdall.py --configure-telegram

# Run Telegram bot (for handling subscriptions)
./heimdall.py --telegram-bot

# Test Telegram configuration
./heimdall.py --test-telegram

# Configure OpenRouter AI
./heimdall.py --configure-openrouter
```

### Development
```bash
# Install dependencies
pip install paramiko requests

# Run with Python directly
python heimdall.py [options]

# Run Telegram bot as a service (CentOS/systemd)
sudo systemctl start heimdall-telegram
sudo systemctl status heimdall-telegram
```

## Architecture

Heimdall is a server monitoring system that uses SSH to connect to remote servers and monitor resources (CPU, memory, disk) and services.

### Core Components

- **heimdall.py**: Main entry point, handles CLI arguments and interactive menu
- **heimdall/config.py**: Manages server configurations (servers.json) and application settings (config.json)
- **heimdall/monitor.py**: Core monitoring logic - SSH connections, resource checks, service monitoring
- **heimdall/alerts.py**: Alert management - tracks alert state, sends email notifications, manages cooldowns
- **heimdall/utils.py**: Logging setup and terminal color utilities
- **heimdall/telegram.py**: Telegram bot integration - handles subscriptions and sends alerts
- **heimdall/ai_assistant.py**: OpenRouter AI integration for intelligent disk usage analysis

### Data Flow

1. User runs heimdall.py with --check or selects check from interactive menu
2. ServerMonitor connects to each server via SSH (using paramiko)
3. Executes commands to check CPU (top), memory (free), disk (df), and services (systemctl/service)
4. For disk alerts, optionally gets AI analysis via OpenRouter
5. AlertManager evaluates thresholds and manages alert state
6. Sends notifications via email and/or Telegram (respecting cooldown periods)

### Key Implementation Details

- **SSH Authentication**: Supports both SSH key (preferred) and password authentication
- **Alert State**: Tracked in alert_status.json to prevent duplicate alerts and track resolutions
- **Filesystem Monitoring**: Intelligently skips special filesystems (squashfs, snap mounts)
- **Service Detection**: Automatically detects available services using systemctl or service commands
- **Email Templates**: HTML-formatted emails with embedded Heimdall logo
- **Telegram Bot**: Handles user subscriptions via commands (/start, /stop, /status, /help)
- **AI Analysis**: OpenRouter integration provides intelligent disk usage analysis for disk alerts
- **Alert Cooldown**: Configurable cooldown period (default 8 hours) prevents notification spam

### Configuration Files

- **config.json**: Application settings (email, telegram, openrouter, thresholds, intervals)
- **servers.json**: List of servers to monitor with their SSH credentials
- **alert_status.json**: Current alert state (auto-generated)

### Telegram Bot Implementation

- **Polling Mode**: Bot uses long polling to receive commands
- **Subscriber Management**: Stores subscribers in config.json with chat_id
- **Commands**: /start (subscribe), /stop (unsubscribe), /status (check status), /help
- **Standalone Mode**: Run with --telegram-bot or interactive menu option 9
- **Service Mode**: Can run as systemd service for continuous operation

### OpenRouter AI Integration

- **Disk Analysis**: When disk usage exceeds threshold, runs du and df commands
- **AI Processing**: Sends disk usage data to OpenRouter for analysis
- **Smart Suggestions**: AI identifies causes, suggests cleanup actions
- **Model Support**: Default uses free deepseek model, supports GPT-3.5, Claude, etc.
- **Alert Enhancement**: AI suggestions appended to disk alert messages

### Testing Changes

When modifying monitoring logic:
1. Test with a single server first using interactive mode
2. Verify email alerts work with --test-email
3. Test Telegram with --test-telegram
4. Check logs in logs/ directory for debugging
5. Ensure special filesystems are properly skipped
6. Test both systemd and non-systemd service detection
7. Verify AI suggestions appear in disk alerts (when configured)

### systemd Service Configuration

For running Telegram bot as a service on CentOS:

```ini
[Unit]
Description=Heimdall Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/heimdall-monitoring
ExecStart=/usr/bin/python3 /root/heimdall-monitoring/heimdall.py --telegram-bot
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
```