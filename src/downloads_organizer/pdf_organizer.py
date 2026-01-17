"""
PDF Organizer - Tax document and bank statement organization.

This module handles the organization of PDF files from Downloads into
a structured Google Drive tax folder hierarchy.

Migrated from: tax-pdf-organizer
"""

import logging
from pathlib import Path
from typing import List, Tuple

from . import config
from . import utils
from . import notifications

logger = logging.getLogger(__name__)


def run(
    dry_run: bool = False,
    auto_yes: bool = False,
    audit: bool = False,
    verbose: bool = False,
) -> Tuple[int, int, int]:
    """
    Run the PDF organizer.

    Args:
        dry_run: Preview without moving files
        auto_yes: Auto-confirm all actions
        audit: Audit existing folders for misplaced files
        verbose: Enable verbose logging

    Returns:
        Tuple of (moved_files, categorized_files, uncategorized_files)
    """
    utils.setup_logging("pdf_organizer", verbose)

    logger.info("=" * 60)
    logger.info("PDF Organizer")
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN MODE - No files will be moved")

    # TODO: Migrate organize_statements.py logic here
    # For now, this is a placeholder

    logger.warning("PDF organizer migration not yet complete")
    logger.info("Please use the original tax-pdf-organizer for now:")
    logger.info("  python ~/Documents/tax-pdf-organizer/organize_statements.py")

    return (0, 0, 0)


def scan_downloads() -> List[Path]:
    """
    Scan Downloads folder for PDF files.

    Returns:
        List of PDF file paths
    """
    pdfs = list(config.DOWNLOADS_FOLDER.glob("*.pdf"))
    return sorted(pdfs, key=lambda p: p.stat().st_mtime)


def is_bank_statement(text: str) -> Tuple[bool, str]:
    """
    Check if PDF text matches any bank statement patterns.

    Args:
        text: Extracted PDF text

    Returns:
        Tuple of (is_match, bank_config_key)
    """
    text_lower = text.lower()

    for key, cfg in config.BANK_CONFIGS.items():
        patterns = cfg.get("patterns", [])
        if all(pattern.lower() in text_lower for pattern in patterns):
            return True, key

    return False, ""


def is_work_document(text: str) -> bool:
    """
    Check if PDF appears to be a work document (should be excluded).

    Args:
        text: Extracted PDF text

    Returns:
        True if this appears to be a work document
    """
    text_lower = text.lower()
    return any(pattern in text_lower for pattern in config.WORK_EXCLUSION_PATTERNS)
