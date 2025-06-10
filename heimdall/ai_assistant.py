#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""AI Assistant module for Heimdall using OpenRouter.

This module provides AI-powered suggestions for disk usage analysis.
"""

import json
import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger("Heimdall")

class AIAssistant:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.openrouter_config = config.get('openrouter', {})
        self.api_key = self.openrouter_config.get('api_key', '')
        self.model = self.openrouter_config.get('model', 'deepseek/deepseek-r1-0528:free')
        self.enabled = self.openrouter_config.get('enabled', False)
        self.base_url = "https://openrouter.ai/api/v1"
        
    def is_configured(self) -> bool:
        """Check if OpenRouter is properly configured."""
        configured = bool(self.api_key) and self.enabled
        if not configured:
            logger.debug(f"OpenRouter not configured - enabled: {self.enabled}, has_key: {bool(self.api_key)}")
        return configured
    
    def analyze_disk_usage(self, server_name: str, filesystem: str, usage_percent: float, 
                          du_output: str, df_output: str) -> Optional[str]:
        """Analyze disk usage and provide AI suggestions."""
        if not self.is_configured():
            logger.info("OpenRouter not configured, skipping AI analysis")
            return None
        
        try:
            # Prepare the prompt
            prompt = f"""You are a Linux system administrator helping to analyze disk usage issues.

Server: {server_name}
Filesystem: {filesystem}
Current Usage: {usage_percent}%

Disk usage summary (df -h):
{df_output}

Top directories by size (du -sh):
{du_output}

Please analyze this disk usage data and provide:
1. The most likely causes of high disk usage
2. Specific directories or files that appear to be consuming excessive space
3. Safe cleanup suggestions (logs, caches, temp files)
4. Any patterns or anomalies you notice

Keep your response concise and actionable, focusing on the most important findings."""

            # Make API request to OpenRouter
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/bnesim/heimdall-monitoring",
                "X-Title": "Heimdall Monitoring"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful Linux system administrator specializing in disk usage analysis and optimization."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3,  # Lower temperature for more focused responses
                "max_tokens": 500
            }
            
            logger.info(f"Sending disk analysis request to OpenRouter for {server_name}")
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                suggestion = result['choices'][0]['message']['content']
                logger.info(f"AI suggestion generated for {server_name} disk usage")
                return suggestion
            else:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error("OpenRouter API request timed out")
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"OpenRouter HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error getting AI suggestion: {type(e).__name__}: {str(e)}")
            # Log the prompt size to debug
            logger.debug(f"Prompt length: {len(prompt)}, du_output length: {len(du_output)}")
            return None
    
    def format_suggestion_for_alert(self, suggestion: str) -> str:
        """Format AI suggestion for inclusion in alerts."""
        if not suggestion:
            return ""
        
        # Add a header and format the suggestion
        formatted = "\n\n🤖 AI Analysis:\n" + "-" * 40 + "\n"
        formatted += suggestion.strip()
        formatted += "\n" + "-" * 40
        
        return formatted
    
    def test_connection(self) -> tuple[bool, str]:
        """Test the OpenRouter connection."""
        if not self.api_key:
            return False, "No API key configured"
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/bnesim/heimdall-monitoring",
                "X-Title": "Heimdall Monitoring"
            }
            
            # Simple test request
            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello, this is a test message. Please respond with 'Connection successful'."
                    }
                ],
                "max_tokens": 50
            }
            
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                return True, f"Connected successfully using model: {self.model}"
            else:
                return False, f"API error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return False, str(e)