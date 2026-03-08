"""
LADA - Messaging Platform Connectors
Multi-platform messaging integration for Telegram, Discord, WhatsApp, and Slack.
"""

from modules.messaging.message_router import MessageRouter, get_message_router

__all__ = ['MessageRouter', 'get_message_router']
