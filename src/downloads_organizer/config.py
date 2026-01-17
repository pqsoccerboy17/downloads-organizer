"""
Unified configuration for Downloads Organizer.

This module centralizes all configuration for both PDF and media organizers,
making it easy to modify paths and settings in one place.
"""

from pathlib import Path
from typing import Set

# =============================================================================
# BASE PATHS
# =============================================================================

HOME = Path.home()

# Google Drive base path (macOS CloudStorage)
GOOGLE_DRIVE_BASE = HOME / "Library/CloudStorage/GoogleDrive-michaelduncan17@gmail.com/My Drive"

# Source folders to watch/scan
DOWNLOADS_FOLDER = HOME / "Downloads"
DESKTOP_FOLDER = HOME / "Desktop"

SOURCE_FOLDERS = [DOWNLOADS_FOLDER, DESKTOP_FOLDER]

# =============================================================================
# PDF ORGANIZER CONFIGURATION
# =============================================================================

# Destination for tax documents
TAX_BASE_FOLDER = GOOGLE_DRIVE_BASE / "Personal/Taxes"

# PDF file extension
PDF_EXTENSION = ".pdf"

# Bank account configurations
# Each config defines how to identify and organize statements from a specific bank
BANK_CONFIGS = {
    "colonial_checking": {
        "name": "Colonial Checking",
        "patterns": ["colonial", "account.*0675"],
        "folder_name": "Colonial Checking - 0675",
        "destination_category": "Bank Statements",
    },
    "colonial_savings": {
        "name": "Colonial Savings",
        "patterns": ["colonial", "account.*5934"],
        "folder_name": "Colonial Savings - 5934",
        "destination_category": "Bank Statements",
    },
    "amex": {
        "name": "American Express",
        "patterns": ["american express", "amex"],
        "folder_name": "American Express",
        "destination_category": "Bank Statements",
    },
    "chase_checking": {
        "name": "Chase Checking",
        "patterns": ["chase", "checking"],
        "folder_name": "Chase Checking",
        "destination_category": "Bank Statements",
    },
    "chase_credit": {
        "name": "Chase Credit Card",
        "patterns": ["chase", "credit card", "sapphire"],
        "folder_name": "Chase Credit Card",
        "destination_category": "Bank Statements",
    },
}

# Document categories for non-bank PDFs
DOCUMENT_CATEGORIES = {
    "tax_forms": {
        "name": "Tax Forms",
        "patterns": ["1099", "w-2", "w2", "1098", "form 1040"],
        "folder": "Tax Forms",
        "confidence_threshold": 0.9,
    },
    "receipts": {
        "name": "Receipts",
        "patterns": ["receipt", "invoice", "payment confirmation"],
        "folder": "Receipts",
        "confidence_threshold": 0.9,
    },
    "insurance": {
        "name": "Insurance",
        "patterns": ["insurance", "policy", "coverage", "claim"],
        "folder": "Insurance",
        "confidence_threshold": 0.9,
    },
}

# Work document patterns to exclude (never categorize these)
WORK_EXCLUSION_PATTERNS = [
    "proposal",
    "sow",
    "statement of work",
    "contract",
    "agreement",
    "presentation",
    "deck",
    "yourco",
    "consulting",
]

# =============================================================================
# MEDIA ORGANIZER CONFIGURATION
# =============================================================================

# Destination for media files
MEDIA_BASE_FOLDER = GOOGLE_DRIVE_BASE / "Personal/Media"

# Supported file extensions by type
PHOTO_EXTENSIONS: Set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
    ".heic", ".heif",  # iPhone photos
    ".raw", ".cr2", ".nef", ".arw", ".orf", ".rw2", ".dng",  # RAW formats
    ".raf", ".srw", ".pef", ".x3f", ".3fr", ".mef", ".mrw",
}

VIDEO_EXTENSIONS: Set[str] = {
    ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".wmv",
    ".flv", ".webm", ".mts", ".m2ts", ".mpg", ".mpeg",
}

AUDIO_EXTENSIONS: Set[str] = {
    ".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".wma",
    ".aiff", ".aif", ".m4b", ".opus",
}

ALL_MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

# Month names for folder structure
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# =============================================================================
# WATCHER CONFIGURATION
# =============================================================================

# Debounce delay (wait for file to finish downloading)
DEBOUNCE_SECONDS = 5

# Periodic scan interval (fallback to catch missed files)
PERIODIC_SCAN_INTERVAL = 60  # 1 minute

# Minimum interval between organizer runs
MIN_RUN_INTERVAL = 10  # seconds

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOG_FILE = HOME / "downloads_organizer.log"
