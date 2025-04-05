# Heimdall - The Watchful Server Monitor

<p align="center">
  <img src="HEIMDALL.png" alt="Heimdall Logo" width="200">
</p>

Like the Norse god who watches over Bifröst, Heimdall keeps a vigilant eye on your servers. This Python-based monitoring tool allows you to monitor multiple servers for CPU, memory, disk usage, and service status with email alerts when thresholds are exceeded.

## Features

- **Multi-Server Monitoring**: Monitor an unlimited number of servers from a single installation
- **Resource Monitoring**: Track CPU, memory, and disk usage across all your servers
- **Service Monitoring**: Monitor the status of specific services on each server
- **Email Alerts**: Receive notifications when resources exceed defined thresholds
- **Alert Management**: Smart alert tracking with cooldown periods to prevent alert storms
- **Secure Connections**: Connect to servers using SSH key authentication or password
- **Interactive Mode**: Easily add, remove, and manage servers through an interactive CLI
- **Flexible Authentication**: Support for both SSH key and password authentication

## Installation

### Prerequisites

- Python 3.6 or higher
- SSH access to the servers you want to monitor
- SMTP server for email alerts (optional)

### Installation Steps

1. Clone the repository:

```bash
git clone https://github.com/bnesim/heimdall-monitoring.git
cd heimdall-monitoring
```

2. Install the required dependencies:

```bash
pip install paramiko
```

3. Make the main script executable:

```bash
chmod +x heimdall.py
```

## Configuration

Heimdall uses two configuration files:

- `config.json`: Contains general settings like email configuration and thresholds
- `servers.json`: Contains the list of servers to monitor

Both files will be created automatically with default values when you first run Heimdall.

### Email Configuration

To configure email alerts:

```bash
./heimdall.py --configure-smtp
```

Follow the interactive prompts to set up your SMTP server details.

### Adding Servers

To add servers to monitor:

```bash
./heimdall.py --interactive
```

Select option 1 to add a new server and follow the prompts. You can choose between SSH key authentication (recommended) or password authentication.

## Usage

### Interactive Mode

Run Heimdall in interactive mode to manage servers:

```bash
./heimdall.py --interactive
```

This will present a menu with options to:

1. Add a new server
2. Remove a server
3. List configured servers
4. Check all servers
5. Configure email settings
6. Exit

### Check Mode

To check all configured servers without the interactive menu:

```bash
./heimdall.py --check
```

This is useful for running Heimdall from cron jobs or other schedulers.

### Automated Monitoring

To set up automated monitoring, add a cron job:

```bash
# Edit crontab
crontab -e

# Add a line to run Heimdall every 15 minutes
*/15 * * * * /path/to/heimdall-monitoring/heimdall.py --check
```

## Alert Thresholds

Default thresholds are:

- CPU: 80%
- Memory: 80%
- Disk: 85%

Other configurable settings:

- Alert Cooldown: 1 hour (minimum time between repeated alerts for the same issue)

You can modify these in the `config.json` file.

## Logs

Heimdall maintains logs in the `logs` directory:

- `heimdall.log`: General application logs
- `alerts.log`: Record of all alerts

## About BNESIM

<p align="center">
  <a href="https://www.bnesim.com">
    <img src="https://www.bnesim.com/wp-content/uploads/2025/02/BNESIMLOGO.svg" alt="BNESIM Logo" width="200">
  </a>
</p>

Heimdall is developed by [BNESIM](https://www.bnesim.com), providing:

- 🌍 **Global Coverage**: Connect seamlessly in over 200 countries.
- 🏆 **Award-Winning Service**: Recognized multiple times as the "World's Best Travel eSIM Provider".
- 📱 **eSIM Convenience**: Instant activation without the need for a physical SIM card.
- 🔒 **Secure Connectivity**: Enjoy encrypted communications for your peace of mind.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2023 BNESIM

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```