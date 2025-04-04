#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Heimdall - The Watchful Server Monitor

This package provides server monitoring functionality with email alerts.
"""

from .config import load_config, ServerConfig
from .monitor import ServerMonitor
from .utils import setup_logging, Colors
from .alerts import AlertManager

__version__ = '1.0.0'
__author__ = 'BNEsim Team'