"""
AWS Lambda Function — Telegram Bot Webhook Handler

Full-featured Telegram bot interface for the RSS news feed system.

Commands:
    Keyword Alerts:
        /add <keyword>    — Add a keyword alert
        /remove <keyword> — Remove a keyword alert
        /list             — List all active keywords

    Query:
        /latest [ticker|source] — Latest 10 headlines
        /search <query>         — Search stored news
        /why [article_id]       — Explain why an alert triggered
        /summary [Nd] [TICKER]  — Digest summary
        /top [Nd]               — Top movers by price impact

    Settings:
        /settings               — Show current preferences
        /mode quiet|normal      — Alert mode
        /threshold N            — Min keyword matches for alert
        /sources name on|off    — Toggle a feed source
        /digest type on|off     — Toggle morning/eod/weekly digest

Setup:
    1. Deploy this Lambda behind an API Gateway (POST endpoint)
    2. Set the Telegram webhook:
       curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
            -d '{"url": "https://<api-gateway-url>/webhook"}'

Environment Variables Required:
    - DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
    - TELEGRAM_BOT_TOKEN
    - TELEGRAM_CHAT_ID (optional — restricts commands to this chat only)
"""

import json
import logging
import os
from typing import Dict, Any, Optional
from urllib.request import urlopen, Request

from bot_handlers import (
    handle_add, handle_remove, handle_list, handle_score,
    handle_latest, handle_search, handle_why, handle_summary, handle_top,
    handle_settings, handle_mode, handle_threshold, handle_sources, handle_digest,
    handle_help
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_db_config() -> Dict[str, str]:
    return {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', ''),
        'database': os.environ.get('DB_NAME', 'test'),
        'port': int(os.environ.get('DB_PORT', '3306'))
    }


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def send_telegram_message(chat_id: int, text: str, parse_mode: str = 'HTML') -> Optional[Dict]:
    """Send a message back to the Telegram chat."""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set")
        return None

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Telegram has a 4096 char limit per message — split if needed
    if len(text) > 4000:
        chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
        result = None
        for chunk in chunks:
            result = _send_single_message(url, chat_id, chunk, parse_mode)
        return result

    return _send_single_message(url, chat_id, text, parse_mode)


def _send_single_message(url: str, chat_id: int, text: str, parse_mode: str) -> Optional[Dict]:
    payload = json.dumps({
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }).encode('utf-8')

    try:
        req = Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        response = urlopen(req, timeout=10)
        return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return None


# ---------------------------------------------------------------------------
# Command routing
# ---------------------------------------------------------------------------

# Map of command → (handler_function, needs_chat_id, arg_extraction)
# This keeps the handler dispatch clean and extensible.

def _parse_command(text: str) -> tuple:
    """Parse command and arguments from message text.
    Returns (command, args) where command is lowercase without '/'.
    Handles @botname suffixes (e.g. /help@MyBot).
    """
    if not text.startswith('/'):
        return ('', text)

    parts = text.split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ''

    # Strip @botname suffix
    if '@' in cmd:
        cmd = cmd.split('@')[0]

    # Remove leading /
    cmd = cmd.lstrip('/')
    return (cmd, args)


def route_command(db_config: Dict, chat_id: str, user_name: str,
                  command: str, args: str) -> str:
    """Route a parsed command to the appropriate handler."""

    # --- Keyword management ---
    if command == 'add':
        return handle_add(db_config, args, user_name)
    elif command == 'remove':
        return handle_remove(db_config, args)
    elif command == 'score':
        return handle_score(db_config, args)
    elif command == 'list':
        return handle_list(db_config)

    # --- Query ---
    elif command == 'latest':
        return handle_latest(db_config, args)
    elif command == 'search':
        return handle_search(db_config, args)
    elif command == 'why':
        return handle_why(db_config, args)
    elif command == 'summary':
        return handle_summary(db_config, args)
    elif command == 'top':
        return handle_top(db_config, args)

    # --- Settings ---
    elif command == 'settings':
        return handle_settings(db_config, chat_id)
    elif command == 'mode':
        return handle_mode(db_config, chat_id, args)
    elif command == 'threshold':
        return handle_threshold(db_config, chat_id, args)
    elif command == 'sources':
        return handle_sources(db_config, chat_id, args)
    elif command == 'digest':
        return handle_digest(db_config, chat_id, args)

    # --- Help ---
    elif command in ('help', 'start'):
        return handle_help()

    else:
        return (
            "❓ Unknown command.\n\n"
            "Use <code>/help</code> to see available commands."
        )


# ---------------------------------------------------------------------------
# Lambda Handler
# ---------------------------------------------------------------------------

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle incoming Telegram webhook updates.
    The event body contains the Telegram Update object.
    """
    logger.info("Telegram webhook received")

    # Parse the Telegram update from the event body
    try:
        if isinstance(event.get('body'), str):
            update = json.loads(event['body'])
        elif isinstance(event.get('body'), dict):
            update = event['body']
        else:
            update = event
    except (json.JSONDecodeError, KeyError):
        logger.error("Failed to parse webhook body")
        return {'statusCode': 400, 'body': 'Bad request'}

    # Extract message
    message = update.get('message')
    if not message or not message.get('text'):
        return {'statusCode': 200, 'body': 'OK'}

    chat_id = message['chat']['id']
    text = message['text'].strip()
    user = message.get('from', {})
    user_name = user.get('username') or user.get('first_name') or str(user.get('id', 'unknown'))

    # Optional: restrict to a specific chat
    allowed_chat = os.environ.get('TELEGRAM_CHAT_ID', '')
    if allowed_chat and str(chat_id) != allowed_chat:
        logger.warning(f"Unauthorized chat_id: {chat_id}")
        send_telegram_message(chat_id, "⛔ Unauthorized. This bot is restricted to a specific chat.")
        return {'statusCode': 200, 'body': 'OK'}

    db_config = get_db_config()
    command, args = _parse_command(text)

    try:
        response = route_command(db_config, str(chat_id), user_name, command, args)
    except Exception as e:
        logger.error(f"Command error: {command} — {e}", exc_info=True)
        response = f"❌ Error processing <code>/{command}</code>: {str(e)[:200]}"

    send_telegram_message(chat_id, response)
    return {'statusCode': 200, 'body': 'OK'}
