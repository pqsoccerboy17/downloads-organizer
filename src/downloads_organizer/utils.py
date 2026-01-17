"""
Shared utilities for Downloads Organizer.

This module provides common functionality used by both PDF and media organizers:
- File operations (checksums, safe moves)
- Date parsing and extraction
- Logging setup
- Process locking
"""

import fcntl
import hashlib
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config

# =============================================================================
# LOGGING
# =============================================================================


def setup_logging(name: str = "downloads_organizer", verbose: bool = False) -> logging.Logger:
    """
    Set up logging with file and console handlers.

    Args:
        name: Logger name
        verbose: If True, set DEBUG level; otherwise INFO

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # File handler
    file_handler = logging.FileHandler(config.LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# =============================================================================
# FILE OPERATIONS
# =============================================================================


def get_file_checksum(file_path: Path, algorithm: str = "md5") -> str:
    """
    Calculate checksum of a file.

    Args:
        file_path: Path to the file
        algorithm: Hash algorithm (md5, sha256, etc.)

    Returns:
        Hex digest of the file's checksum
    """
    hash_func = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def files_are_identical(file1: Path, file2: Path) -> bool:
    """
    Check if two files have identical content using checksums.

    Args:
        file1: First file path
        file2: Second file path

    Returns:
        True if files have identical content
    """
    if not file1.exists() or not file2.exists():
        return False

    # Quick size check first
    if file1.stat().st_size != file2.stat().st_size:
        return False

    # Full checksum comparison
    return get_file_checksum(file1) == get_file_checksum(file2)


def safe_move(
    source: Path,
    destination: Path,
    verify: bool = True,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """
    Safely move a file using copy-then-delete strategy.

    Args:
        source: Source file path
        destination: Destination file path
        verify: If True, verify copy before deleting original
        logger: Optional logger for status messages

    Returns:
        True if move was successful
    """
    log = logger or logging.getLogger(__name__)

    if not source.exists():
        log.error(f"Source file does not exist: {source}")
        return False

    # Create destination directory if needed
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Copy file
        shutil.copy2(source, destination)

        # Verify copy if requested
        if verify:
            if not files_are_identical(source, destination):
                log.error(f"Copy verification failed: {source} -> {destination}")
                destination.unlink()  # Remove failed copy
                return False

        # Delete original
        source.unlink()
        log.debug(f"Moved: {source} -> {destination}")
        return True

    except Exception as e:
        log.error(f"Error moving {source} to {destination}: {e}")
        # Clean up partial copy if it exists
        if destination.exists() and source.exists():
            destination.unlink()
        return False


def get_unique_path(destination: Path) -> Path:
    """
    Get a unique file path by appending a number suffix if file exists.

    Args:
        destination: Desired destination path

    Returns:
        Unique path (original or with _N suffix)
    """
    if not destination.exists():
        return destination

    stem = destination.stem
    suffix = destination.suffix
    parent = destination.parent

    counter = 2
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        new_path = parent / new_name
        if not new_path.exists():
            return new_path
        counter += 1


# =============================================================================
# DATE UTILITIES
# =============================================================================


def parse_date_from_string(text: str) -> Optional[datetime]:
    """
    Try to parse a date from various common formats.

    Args:
        text: String that may contain a date

    Returns:
        datetime if found, None otherwise
    """
    import re

    # Common date patterns
    patterns = [
        # ISO format: 2024-01-15
        (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
        # US format: 01/15/2024 or 01-15-2024
        (r"(\d{2})[/-](\d{2})[/-](\d{4})", "%m-%d-%Y"),
        # Written: January 15, 2024
        (r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", None),
        # Compact: 20240115
        (r"(\d{4})(\d{2})(\d{2})", "%Y%m%d"),
    ]

    for pattern, date_format in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if date_format:
                    # Reconstruct the date string and parse
                    date_str = "-".join(match.groups())
                    return datetime.strptime(date_str, date_format.replace("/", "-"))
                else:
                    # Handle month name format
                    month_name, day, year = match.groups()
                    month = config.MONTH_NAMES.index(month_name.capitalize()) + 1
                    return datetime(int(year), month, int(day))
            except (ValueError, AttributeError):
                continue

    return None


def get_year_from_date(date: datetime) -> int:
    """Get the year from a datetime object."""
    return date.year


def get_month_name(date: datetime) -> str:
    """Get the full month name from a datetime object."""
    return config.MONTH_NAMES[date.month - 1]


# =============================================================================
# PROCESS LOCKING
# =============================================================================


class ProcessLock:
    """
    Cross-process file lock to prevent concurrent execution.

    Prevents race conditions when both the watcher and scheduled runs
    try to process the same files simultaneously.
    """

    def __init__(self, lock_file: Optional[Path] = None):
        self.lock_file = lock_file or (config.HOME / ".downloads_organizer.lock")
        self._lock_handle = None

    def acquire(self, timeout: int = 30) -> bool:
        """
        Attempt to acquire the lock.

        Args:
            timeout: Maximum seconds to wait for lock

        Returns:
            True if lock was acquired
        """
        import time

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                self._lock_handle = open(self.lock_file, "w")
                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (IOError, OSError):
                time.sleep(0.5)

        return False

    def release(self):
        """Release the lock."""
        if self._lock_handle:
            try:
                fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
                self._lock_handle.close()
                self.lock_file.unlink(missing_ok=True)
            except Exception:
                pass
            self._lock_handle = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Could not acquire process lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
