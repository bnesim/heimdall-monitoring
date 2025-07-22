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

### Alert Notification Enhancements (2025-07-21)

Recent improvements to reduce notification spam while maintaining system awareness:

**Open Alerts Context:**
- NEW ALERT emails/Telegram include HTML table/text list of other currently open alerts
- ALERT RESOLVED emails/Telegram include remaining open alerts (excluding the resolved one)
- Provides full system context in every notification

**Smart Cooldown Management:**
- Any notification sent (NEW, RECURRING, or RESOLVED) resets cooldown timer for ALL active alerts
- Prevents multiple recurring alerts from firing simultaneously after any notification
- Significantly reduces notification volume while maintaining awareness

**Implementation Details:**
- `get_open_alerts()` - Retrieves all active alerts with duration calculation
- `format_open_alerts_html()` - Formats alerts as HTML table for emails
- `format_open_alerts_text()` - Formats alerts as text list for Telegram
- `reset_all_alert_cooldowns()` - Resets last_notified for all active alerts
- Alert duration shows days/hours/minutes since first detection

### Session-Based Alert Batching (2025-07-22)

Major enhancement to notification system that batches all alerts per monitoring session:

**Batch Notifications:**
- Single email/Telegram per check session containing ALL new/recurring alerts
- Single email/Telegram for ALL resolved alerts in the session
- Dramatically reduces notifications for shared resources (e.g., NFS mounts)
- Better overview of system state changes in one message

**Session Management:**
- `start_session()` - Begins collecting alerts instead of sending immediately
- `end_session()` - Sends batch notifications for all queued alerts
- Alerts grouped by server for better organization
- Preserves AI disk analysis and all alert details

**Notification Format:**
- **Alert Summary**: Shows counts of new/recurring/resolved issues
- **Server Sections**: Groups alerts by server with clear visual distinction
- **Alert Types**: NEW (red), RECURRING (yellow), RESOLVED (green)
- **Open Alerts**: Still includes list of all open alerts at bottom

**Benefits:**
- Reduces notification spam for shared disk issues
- Single comprehensive view per monitoring run
- Maintains detailed alert information
- Cooldown still resets for all active alerts

### Testing Changes

When modifying monitoring logic:
1. Test with a single server first using interactive mode
2. Verify email alerts work with --test-email
3. Test Telegram with --test-telegram
4. Check logs in logs/ directory for debugging
5. Ensure special filesystems are properly skipped
6. Test both systemd and non-systemd service detection
7. Verify AI suggestions appear in disk alerts (when configured)
8. Test open alerts context appears in NEW/RESOLVED notifications
9. Verify cooldown reset prevents notification spam
10. Test batch notifications work correctly with multiple alerts
11. Verify shared disk alerts only generate one notification per session

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