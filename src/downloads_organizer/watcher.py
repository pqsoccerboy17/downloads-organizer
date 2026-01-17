"""
Unified Downloads Folder Watcher.

This module watches the Downloads folder for new files and automatically
routes them to the appropriate organizer (PDF or media).

Migrated from: tax-pdf-organizer/watch_downloads.py
"""

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from . import config
from . import utils
from . import notifications

logger = logging.getLogger(__name__)


def run(
    pdf_only: bool = False,
    media_only: bool = False,
    verbose: bool = False,
) -> None:
    """
    Run the Downloads folder watcher.

    Args:
        pdf_only: Only watch for PDF files
        media_only: Only watch for media files
        verbose: Enable verbose logging
    """
    utils.setup_logging("watcher", verbose)

    logger.info("=" * 60)
    logger.info("Downloads Folder Watcher")
    logger.info("=" * 60)

    # TODO: Migrate watch_downloads.py logic here
    # For now, this is a placeholder

    logger.warning("Unified watcher migration not yet complete")
    logger.info("Please use the original tax-pdf-organizer watcher for now:")
    logger.info("  python ~/Documents/tax-pdf-organizer/watch_downloads.py")

    # Placeholder - keep running to simulate watcher
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Watcher stopped")


class DownloadsHandler:
    """
    File system event handler for Downloads folder.

    Handles new file detection and routes to appropriate organizer.
    """

    def __init__(self, pdf_enabled: bool = True, media_enabled: bool = True):
        self.pdf_enabled = pdf_enabled
        self.media_enabled = media_enabled
        self.pending_files = set()
        self.lock = threading.Lock()
        self.last_run = 0

    def on_created(self, file_path: Path) -> None:
        """Handle new file creation."""
        if not file_path.is_file():
            return

        ext = file_path.suffix.lower()

        # Check if this is a file type we care about
        if ext == config.PDF_EXTENSION and self.pdf_enabled:
            logger.info(f"New PDF detected: {file_path.name}")
            self.schedule_processing(file_path, "pdf")

        elif ext in config.ALL_MEDIA_EXTENSIONS and self.media_enabled:
            logger.info(f"New media file detected: {file_path.name}")
            self.schedule_processing(file_path, "media")

    def schedule_processing(self, file_path: Path, file_type: str) -> None:
        """Schedule a file for processing after debounce delay."""
        file_key = (str(file_path), file_type)

        with self.lock:
            if file_key in self.pending_files:
                return
            self.pending_files.add(file_key)

        def process_after_debounce():
            try:
                time.sleep(config.DEBOUNCE_SECONDS)

                with self.lock:
                    self.pending_files.discard(file_key)

                if not file_path.exists():
                    logger.debug(f"File no longer exists: {file_path.name}")
                    return

                # Wait for file to finish downloading (check size stability)
                if not self._wait_for_stable_size(file_path):
                    logger.debug(f"File still changing: {file_path.name}")
                    return

                self._run_organizer(file_type)

            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                with self.lock:
                    self.pending_files.discard(file_key)

        thread = threading.Thread(target=process_after_debounce, daemon=True)
        thread.start()

    def _wait_for_stable_size(self, file_path: Path, timeout: int = 10) -> bool:
        """Wait for file size to stabilize (download complete)."""
        try:
            size1 = file_path.stat().st_size
            time.sleep(1)
            size2 = file_path.stat().st_size
            return size1 == size2
        except OSError:
            return False

    def _run_organizer(self, file_type: str) -> None:
        """Run the appropriate organizer."""
        current_time = time.time()

        # Throttle organizer runs
        if current_time - self.last_run < config.MIN_RUN_INTERVAL:
            logger.debug("Skipping organizer run (too soon)")
            return

        self.last_run = current_time

        if file_type == "pdf":
            from . import pdf_organizer
            pdf_organizer.run(auto_yes=True)

        elif file_type == "media":
            from . import media_organizer
            media_organizer.run(auto_yes=True)
