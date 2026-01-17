"""
Media Organizer - Photo, video, and audio file organization.

This module handles the organization of media files from Downloads into
a structured Google Drive media folder hierarchy using EXIF metadata.

Migrated from: media-organizer
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    Run the media organizer.

    Args:
        dry_run: Preview without moving files
        auto_yes: Auto-confirm all actions
        audit: Audit existing folders for misplaced files
        verbose: Enable verbose logging

    Returns:
        Tuple of (photos_moved, videos_moved, audio_moved)
    """
    utils.setup_logging("media_organizer", verbose)

    logger.info("=" * 60)
    logger.info("Media Organizer")
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN MODE - No files will be moved")

    # Check for ExifTool
    if not check_exiftool():
        logger.error("ExifTool not found. Install with: brew install exiftool")
        return (0, 0, 0)

    # TODO: Migrate organize_media.py logic here
    # For now, this is a placeholder

    logger.warning("Media organizer migration not yet complete")
    logger.info("Please use the original media-organizer for now:")
    logger.info("  python ~/Documents/media-organizer/organize_media.py")

    return (0, 0, 0)


def check_exiftool() -> bool:
    """Check if ExifTool is installed and available."""
    try:
        result = subprocess.run(
            ["exiftool", "-ver"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def scan_downloads() -> Dict[str, List[Path]]:
    """
    Scan Downloads folder for media files.

    Returns:
        Dict with keys 'photos', 'videos', 'audio' containing file paths
    """
    result = {"photos": [], "videos": [], "audio": []}

    for file_path in config.DOWNLOADS_FOLDER.iterdir():
        if not file_path.is_file():
            continue

        ext = file_path.suffix.lower()
        if ext in config.PHOTO_EXTENSIONS:
            result["photos"].append(file_path)
        elif ext in config.VIDEO_EXTENSIONS:
            result["videos"].append(file_path)
        elif ext in config.AUDIO_EXTENSIONS:
            result["audio"].append(file_path)

    return result


def get_media_type(file_path: Path) -> Optional[str]:
    """
    Determine the media type of a file.

    Args:
        file_path: Path to the file

    Returns:
        'photo', 'video', 'audio', or None
    """
    ext = file_path.suffix.lower()
    if ext in config.PHOTO_EXTENSIONS:
        return "photo"
    elif ext in config.VIDEO_EXTENSIONS:
        return "video"
    elif ext in config.AUDIO_EXTENSIONS:
        return "audio"
    return None


def get_exif_date(file_path: Path) -> Optional[datetime]:
    """
    Extract date from file EXIF/metadata using ExifTool.

    Args:
        file_path: Path to the media file

    Returns:
        datetime if found, None otherwise
    """
    try:
        # Try multiple date tags in order of preference
        date_tags = [
            "-DateTimeOriginal",
            "-CreateDate",
            "-MediaCreateDate",
            "-FileModifyDate",
        ]

        result = subprocess.run(
            ["exiftool", "-s", "-s", "-s"] + date_tags + [str(file_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            # Parse first valid date found
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        return datetime.strptime(line.strip(), "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        continue

    except (subprocess.SubprocessError, Exception) as e:
        logger.debug(f"ExifTool error for {file_path}: {e}")

    return None


def build_destination_path(file_path: Path, date: datetime, media_type: str) -> Path:
    """
    Build the destination path for a media file.

    Args:
        file_path: Original file path
        date: Date to use for folder structure
        media_type: 'photo', 'video', or 'audio'

    Returns:
        Full destination path
    """
    year = str(date.year)
    month = config.MONTH_NAMES[date.month - 1]

    type_folder = {
        "photo": "Photos",
        "video": "Videos",
        "audio": "Audio",
    }.get(media_type, "Other")

    # Build new filename: YYYY-MM-DD_HH-MM-SS_OriginalName.ext
    timestamp = date.strftime("%Y-%m-%d_%H-%M-%S")
    new_name = f"{timestamp}_{file_path.name}"

    return config.MEDIA_BASE_FOLDER / year / month / type_folder / new_name
