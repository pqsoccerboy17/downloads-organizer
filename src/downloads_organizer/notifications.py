"""
Notification integration for Downloads Organizer.

This module provides a unified interface to the ecosystem notification system
(~/scripts/notify.py), supporting both Pushover and macOS notifications.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

# Try to import the ecosystem notification module
_notify_module = None
try:
    # Add scripts directory to path
    scripts_path = Path.home() / "scripts"
    if scripts_path.exists() and str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    from notify import send_notification, notify_organization_complete

    _notify_module = True
except ImportError:
    _notify_module = False

logger = logging.getLogger(__name__)


def notifications_available() -> bool:
    """Check if the notification system is available."""
    return _notify_module is True


def notify(
    title: str,
    message: str,
    priority: int = 0,
    url: Optional[str] = None,
) -> bool:
    """
    Send a notification using the ecosystem notification system.

    Args:
        title: Notification title
        message: Notification body
        priority: -2 (silent) to 2 (emergency), default 0
        url: Optional URL to include (Pushover only)

    Returns:
        True if notification was sent
    """
    if not notifications_available():
        logger.debug("Notifications not available (notify module not found)")
        return False

    try:
        return send_notification(title, message, priority, url)
    except Exception as e:
        logger.debug(f"Failed to send notification: {e}")
        return False


def notify_pdf_organization(
    files_organized: int,
    pending_review: int = 0,
    errors: int = 0,
) -> bool:
    """
    Send notification about PDF organization completion.

    Args:
        files_organized: Number of files successfully organized
        pending_review: Number of files still pending
        errors: Number of errors encountered

    Returns:
        True if notification was sent
    """
    if not notifications_available():
        return False

    try:
        return notify_organization_complete(
            organizer_name="Tax Organizer",
            files_organized=files_organized,
            pending_review=pending_review,
            errors=errors,
        )
    except Exception as e:
        logger.debug(f"Failed to send PDF organization notification: {e}")
        return False


def notify_media_organization(
    files_organized: int,
    categories: Optional[dict] = None,
    pending_review: int = 0,
    errors: int = 0,
) -> bool:
    """
    Send notification about media organization completion.

    Args:
        files_organized: Number of files successfully organized
        categories: Optional dict of category -> count (e.g., {"Photos": 10, "Videos": 5})
        pending_review: Number of files still pending
        errors: Number of errors encountered

    Returns:
        True if notification was sent
    """
    if not notifications_available():
        return False

    try:
        return notify_organization_complete(
            organizer_name="Media Organizer",
            files_organized=files_organized,
            categories=categories,
            pending_review=pending_review,
            errors=errors,
        )
    except Exception as e:
        logger.debug(f"Failed to send media organization notification: {e}")
        return False


def notify_watcher_event(event_type: str, file_count: int = 1) -> bool:
    """
    Send notification about a watcher event.

    Args:
        event_type: Type of event (e.g., "new_files", "error")
        file_count: Number of files involved

    Returns:
        True if notification was sent
    """
    if not notifications_available():
        return False

    titles = {
        "new_files": "New Files Detected",
        "error": "Organizer Error",
        "started": "Watcher Started",
        "stopped": "Watcher Stopped",
    }

    messages = {
        "new_files": f"Detected {file_count} new file(s) in Downloads",
        "error": f"Error processing {file_count} file(s)",
        "started": "Downloads folder watcher is now running",
        "stopped": "Downloads folder watcher has stopped",
    }

    title = titles.get(event_type, "Downloads Organizer")
    message = messages.get(event_type, f"Event: {event_type}")
    priority = 1 if event_type == "error" else -1

    return notify(title, message, priority)
