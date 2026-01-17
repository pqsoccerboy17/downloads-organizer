"""
Unified Downloads Folder Watcher.

This module watches the Downloads folder for new files and automatically
routes them to the appropriate organizer (PDF or media).

Migrated from: tax-pdf-organizer/watch_downloads.py

WHAT IT DOES:
    1. Monitors Downloads folder for new PDF and media files
    2. Tracks file renames during download
    3. Waits for file to finish downloading (debounce)
    4. Routes to appropriate organizer (PDF or media)
    5. Periodic fallback scan every minute (catches missed files)
    6. Comprehensive logging with debugging info
"""

import logging
import threading
import time
from pathlib import Path
from typing import Optional, Set

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from . import config
from . import utils
from . import notifications

logger = logging.getLogger(__name__)

# Track when organizers were last run (prevent rapid-fire runs)
last_pdf_run = 0
last_media_run = 0
organizer_lock = threading.Lock()


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

    # Verify Downloads folder exists
    if not config.DOWNLOADS_FOLDER.exists():
        logger.error(f"Downloads folder not found: {config.DOWNLOADS_FOLDER}")
        return

    logger.info("=" * 60)
    logger.info("Downloads Folder Watcher")
    logger.info("=" * 60)
    logger.info(f"Watching: {config.DOWNLOADS_FOLDER}")
    logger.info(f"Debounce delay: {config.DEBOUNCE_SECONDS} seconds")
    logger.info(f"Periodic scan: Every {config.PERIODIC_SCAN_INTERVAL} seconds")

    # Determine what to watch
    watch_pdf = not media_only
    watch_media = not pdf_only

    if watch_pdf:
        logger.info("PDF organizer: ENABLED")
    if watch_media:
        logger.info("Media organizer: ENABLED")

    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    # Create event handler and observer
    event_handler = DownloadsHandler(pdf_enabled=watch_pdf, media_enabled=watch_media)
    observer = Observer()
    observer.schedule(event_handler, str(config.DOWNLOADS_FOLDER), recursive=False)

    # Start periodic scan thread
    scan_thread = threading.Thread(
        target=event_handler.periodic_scan,
        daemon=True
    )
    scan_thread.start()
    logger.info("Periodic scan thread started")

    # Start watching
    observer.start()
    logger.info("File watcher started")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
        observer.stop()

    observer.join()
    logger.info("Watcher stopped")


class DownloadsHandler(FileSystemEventHandler):
    """
    File system event handler for Downloads folder.

    Handles new file detection and routes to appropriate organizer.
    """

    def __init__(self, pdf_enabled: bool = True, media_enabled: bool = True):
        super().__init__()
        self.pdf_enabled = pdf_enabled
        self.media_enabled = media_enabled
        self.pending_files: Set[str] = set()
        self.lock = threading.Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle new file creation."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        self._process_file_event(file_path, "created")

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file renames/moves - common during downloads."""
        if event.is_directory:
            return

        # Process the destination path (final filename)
        dest_path = Path(event.dest_path)
        src_name = Path(event.src_path).name
        logger.info(f"File renamed: {src_name} -> {dest_path.name}")
        self._process_file_event(dest_path, "renamed")

    def _process_file_event(self, file_path: Path, event_type: str) -> None:
        """Process a file event and route to appropriate organizer."""
        if not file_path.is_file():
            return

        ext = file_path.suffix.lower()

        # Check if this is a PDF
        if ext == config.PDF_EXTENSION and self.pdf_enabled:
            logger.info(f"New PDF {event_type}: {file_path.name}")
            self.schedule_processing(file_path, "pdf")
            return

        # Check if this is a media file
        if ext in config.ALL_MEDIA_EXTENSIONS and self.media_enabled:
            logger.info(f"New media file {event_type}: {file_path.name}")
            self.schedule_processing(file_path, "media")
            return

    def schedule_processing(self, file_path: Path, file_type: str) -> None:
        """Schedule a file for processing after debounce delay."""
        file_key = (str(file_path), file_type)

        with self.lock:
            if str(file_key) in self.pending_files:
                logger.debug(f"File already pending: {file_path.name}")
                return
            self.pending_files.add(str(file_key))

        def process_after_debounce():
            try:
                # Wait for file to finish downloading
                time.sleep(config.DEBOUNCE_SECONDS)

                with self.lock:
                    self.pending_files.discard(str(file_key))

                # Verify file exists (might have been renamed)
                if not file_path.exists():
                    logger.debug(f"File no longer exists: {file_path.name}")
                    return

                # Wait for file to finish downloading (check size stability)
                if not self._wait_for_stable_size(file_path):
                    logger.debug(f"File still changing: {file_path.name}")
                    return

                # Run the appropriate organizer
                logger.info(f"Triggering {file_type} organizer for: {file_path.name}")
                self._run_organizer(file_type)

            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                with self.lock:
                    self.pending_files.discard(str(file_key))

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
        global last_pdf_run, last_media_run
        current_time = time.time()

        with organizer_lock:
            if file_type == "pdf":
                if current_time - last_pdf_run < config.MIN_RUN_INTERVAL:
                    logger.debug("Skipping PDF organizer run (too soon)")
                    return
                last_pdf_run = current_time
            elif file_type == "media":
                if current_time - last_media_run < config.MIN_RUN_INTERVAL:
                    logger.debug("Skipping media organizer run (too soon)")
                    return
                last_media_run = current_time

        try:
            if file_type == "pdf":
                self._run_pdf_organizer()
            elif file_type == "media":
                self._run_media_organizer()
        except Exception as e:
            logger.error(f"Error running {file_type} organizer: {e}")

    def _run_pdf_organizer(self) -> None:
        """Run the PDF organizer on Downloads folder."""
        from . import pdf_organizer

        # Count PDFs before
        pdf_count_before = len(list(config.DOWNLOADS_FOLDER.glob("*.pdf")))
        logger.info(f"Running PDF organizer (PDFs before: {pdf_count_before})")

        try:
            moved, skipped, errors = pdf_organizer.run(auto_yes=True)

            # Count PDFs after
            pdf_count_after = len(list(config.DOWNLOADS_FOLDER.glob("*.pdf")))
            files_moved = pdf_count_before - pdf_count_after

            logger.info(f"PDF organizer complete (moved: {files_moved}, skipped: {skipped}, errors: {errors})")

            if pdf_count_before > 0 and files_moved == 0:
                logger.warning("PDFs found in Downloads but none were moved")
                logger.warning("Check organizer output for skip/error messages")

        except Exception as e:
            logger.error(f"PDF organizer failed: {e}")

    def _run_media_organizer(self) -> None:
        """Run the media organizer on Downloads folder."""
        from . import media_organizer

        # Count media files before
        media_count_before = sum(
            len(list(config.DOWNLOADS_FOLDER.glob(f"*{ext}")))
            for ext in config.ALL_MEDIA_EXTENSIONS
        )
        logger.info(f"Running media organizer (media files before: {media_count_before})")

        try:
            photos, videos, audio = media_organizer.run(auto_yes=True)

            # Count media files after
            media_count_after = sum(
                len(list(config.DOWNLOADS_FOLDER.glob(f"*{ext}")))
                for ext in config.ALL_MEDIA_EXTENSIONS
            )
            files_moved = media_count_before - media_count_after
            total_organized = photos + videos + audio

            logger.info(
                f"Media organizer complete (moved: {files_moved}, "
                f"photos: {photos}, videos: {videos}, audio: {audio})"
            )

            if media_count_before > 0 and files_moved == 0:
                logger.warning("Media files found in Downloads but none were moved")

        except Exception as e:
            logger.error(f"Media organizer failed: {e}")

    def periodic_scan(self) -> None:
        """
        Periodically scan Downloads folder and process files (fallback mechanism).

        This provides a safety net in case real-time file detection misses files due to:
        - Browser download quirks (Chrome, Safari handle temp files differently)
        - Files added while watcher was offline
        - Race conditions during file rename/move operations
        - Network drives with delayed file system events
        """
        logger.info(f"Periodic scan started (runs every {config.PERIODIC_SCAN_INTERVAL} seconds)")

        while True:
            try:
                time.sleep(config.PERIODIC_SCAN_INTERVAL)

                if not config.DOWNLOADS_FOLDER.exists():
                    logger.warning(f"Downloads folder not found: {config.DOWNLOADS_FOLDER}")
                    continue

                current_time = time.time()
                min_age = config.DEBOUNCE_SECONDS + 5

                # Scan for PDFs
                if self.pdf_enabled:
                    pdfs = list(config.DOWNLOADS_FOLDER.glob("*.pdf"))
                    old_pdfs = [
                        pdf for pdf in pdfs
                        if current_time - pdf.stat().st_mtime > min_age
                    ]
                    if old_pdfs:
                        logger.info(f"Periodic scan: Found {len(old_pdfs)} PDF(s), running organizer...")
                        for pdf in old_pdfs[:5]:
                            age = int(current_time - pdf.stat().st_mtime)
                            logger.debug(f"  - {pdf.name} (age: {age}s)")
                        self._run_organizer("pdf")

                # Scan for media files
                if self.media_enabled:
                    media_files = []
                    for ext in config.ALL_MEDIA_EXTENSIONS:
                        media_files.extend(config.DOWNLOADS_FOLDER.glob(f"*{ext}"))
                        media_files.extend(config.DOWNLOADS_FOLDER.glob(f"*{ext.upper()}"))

                    old_media = [
                        f for f in media_files
                        if current_time - f.stat().st_mtime > min_age
                    ]
                    if old_media:
                        logger.info(f"Periodic scan: Found {len(old_media)} media file(s), running organizer...")
                        for media in old_media[:5]:
                            age = int(current_time - media.stat().st_mtime)
                            logger.debug(f"  - {media.name} (age: {age}s)")
                        self._run_organizer("media")

            except OSError as e:
                logger.error(f"File system error in periodic scan: {e}")
                time.sleep(60)
            except Exception as e:
                logger.error(f"Unexpected error in periodic scan: {e}")
                time.sleep(60)
