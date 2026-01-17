"""
Media Organizer - Photo, video, and audio file organization.

This module handles the organization of media files from Downloads into
a structured Google Drive media folder hierarchy using EXIF metadata.

Migrated from: media-organizer/organize_media.py

WHAT IT DOES:
    1. Scans source folders for media files
    2. Extracts dates from EXIF/metadata (photos, videos, audio)
    3. Creates year/month folder structure automatically
    4. Renames files to standard format: YYYY-MM-DD_HH-MM-SS_OriginalName.ext
    5. Organizes by media type (Photos, Videos, Audio)
    6. Audits existing folders to fix misplaced files
    7. Prevents duplicate files using MD5 hash comparison
    8. Uses copy-then-delete strategy for safety
"""

import hashlib
import json
import logging
import re
import shutil
import subprocess
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config
from . import utils
from . import notifications

logger = logging.getLogger(__name__)

# Global lookup table for Facebook HTML dates (built once, reused for all files)
FACEBOOK_HTML_DATE_LOOKUP: Dict[str, datetime] = {}
FACEBOOK_HTML_LOOKUP_BUILT = False


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run(
    dry_run: bool = False,
    auto_yes: bool = False,
    audit: bool = False,
    no_audit: bool = False,
    verbose: bool = False,
    source_path: Optional[Path] = None,
    dest_base: Optional[Path] = None,
    event: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Tuple[int, int, int]:
    """
    Run the media organizer.

    Args:
        dry_run: Preview without moving files
        auto_yes: Auto-confirm all actions
        audit: Audit-only mode (skip source folders, only audit existing)
        no_audit: Skip audit phase entirely (faster, just process source folders)
        verbose: Enable verbose logging
        source_path: Custom source folder (overrides defaults)
        dest_base: Custom destination base folder
        event: Optional event/source name (creates subfolder)
        tags: Optional EXIF tags to write to files

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

    # Set destination base
    if dest_base is None:
        dest_base = config.MEDIA_BASE_FOLDER

    logger.info(f"Media folder: {dest_base}")

    if not dest_base.exists():
        logger.warning(f"Media folder does not exist. Creating: {dest_base}")
        dest_base.mkdir(parents=True, exist_ok=True)

    if auto_yes:
        logger.info("AUTO-YES MODE: Skipping all prompts")

    # Prepare tags list
    if tags is None:
        tags = []
    if event and event not in tags:
        tags.append(event)

    # Build Facebook HTML lookup if needed
    global FACEBOOK_HTML_DATE_LOOKUP, FACEBOOK_HTML_LOOKUP_BUILT
    if not FACEBOOK_HTML_LOOKUP_BUILT:
        facebook_base = _detect_facebook_backup(dest_base, source_path)
        if facebook_base:
            logger.info("=" * 60)
            logger.info("DETECTED FACEBOOK BACKUP - Building date lookup table...")
            logger.info("=" * 60)
            FACEBOOK_HTML_DATE_LOOKUP = build_facebook_html_lookup(facebook_base)
            FACEBOOK_HTML_LOOKUP_BUILT = True

    # Track statistics
    stats = {
        "photos": 0,
        "videos": 0,
        "audio": 0,
        "errors": 0,
    }
    date_source_counts = {
        "facebook_html": 0,
        "facebook_sidecar": 0,
        "exif": 0,
        "file_mtime": 0,
        "current_date": 0,
        "unknown": 0,
    }

    def track_method(method: str):
        if not method:
            date_source_counts["unknown"] += 1
            return
        m = method.lower()
        if "facebook html" in m:
            date_source_counts["facebook_html"] += 1
        elif "facebook sidecar" in m:
            date_source_counts["facebook_sidecar"] += 1
        elif "exif" in m:
            date_source_counts["exif"] += 1
        elif "file modification" in m:
            date_source_counts["file_mtime"] += 1
        elif "current date" in m:
            date_source_counts["current_date"] += 1
        else:
            date_source_counts["unknown"] += 1

    def update_stats(result: Dict):
        media_type = result.get("media_type", "")
        if media_type == "photo":
            stats["photos"] += 1
        elif media_type == "video":
            stats["videos"] += 1
        elif media_type == "audio":
            stats["audio"] += 1
        track_method(result.get("date_method", ""))

    # Process source folders (unless audit-only)
    if not audit:
        source_folders = [source_path] if source_path else config.SOURCE_FOLDERS

        logger.info("=" * 60)
        logger.info("PROCESSING SOURCE FOLDERS")
        logger.info("=" * 60)

        all_source_files = []
        for folder in source_folders:
            if not folder or not folder.exists():
                continue

            logger.info(f"Scanning: {folder}")
            for ext in config.ALL_MEDIA_EXTENSIONS:
                all_source_files.extend(folder.rglob(f"*{ext}"))
                all_source_files.extend(folder.rglob(f"*{ext.upper()}"))

        if not all_source_files:
            logger.info("No media files found in source folders")
        else:
            logger.info(f"Found {len(all_source_files)} media files")

            organized = []
            errors = []

            for file_path in all_source_files:
                try:
                    result = organize_file(
                        file_path,
                        dry_run=dry_run,
                        copy_then_delete=True,
                        dest_base=dest_base,
                        event=event,
                        tags=tags if tags else None,
                    )

                    if result["status"] in ["moved", "would_move"]:
                        organized.append(result)
                        update_stats(result)
                        logger.info(
                            f"{'Would move' if dry_run else 'Moved'}: "
                            f"{result['file']} -> {result.get('new_name', '')}"
                        )
                    elif result["status"] == "error":
                        errors.append(result)
                        stats["errors"] += 1
                        logger.warning(f"Error: {result['file']} - {result.get('error', '')}")

                except Exception as e:
                    errors.append({"file": file_path.name, "error": str(e)})
                    stats["errors"] += 1
                    logger.error(f"Exception processing {file_path.name}: {e}")

            logger.info(f"Organized: {len(organized)} files")
            if errors:
                logger.warning(f"Errors: {len(errors)} files")

    # Run audit (skip if --no-audit is specified)
    if no_audit:
        logger.info("")
        logger.info("Skipping audit phase (--no-audit)")
        moved_files = []
        total_scanned = 0
    else:
        logger.info("")
        logger.info("=" * 60)
        logger.info("RUNNING FOLDER AUDIT...")
        logger.info("=" * 60)
        logger.info("Recursively scanning Media folder for misplaced files...")

        moved_files, total_scanned = scan_and_audit_folders(
            auto_yes=auto_yes,
            dry_run=dry_run,
            dest_base=dest_base,
            event=event,
            tags=tags if tags else None,
        )

        for move in moved_files:
            update_stats(move)

        # Report results
        logger.info("")
        logger.info("=" * 60)
        if dry_run:
            logger.info("DRY RUN PREVIEW - No files were actually moved")
        else:
            logger.info("AUDIT COMPLETE!")
        logger.info(f"Scanned: {total_scanned} files")
        logger.info(f"{'Would move' if dry_run else 'Moved'}: {len(moved_files)} files")

        if moved_files:
            # Group by type
            by_type: Dict[str, List[Dict]] = {}
            for move in moved_files:
                mtype = move.get("media_type", "Unknown")
                if mtype not in by_type:
                    by_type[mtype] = []
                by_type[mtype].append(move)

            for mtype, files in sorted(by_type.items()):
                logger.info(f"{mtype} ({len(files)} files):")
                for move in files[:5]:
                    logger.info(
                        f"  {move['file']} -> {move.get('year', '?')}/{move.get('month', 0):02d}"
                    )
                if len(files) > 5:
                    logger.info(f"  ... and {len(files) - 5} more")
        else:
            logger.info("No misplaced files found - all files are organized correctly!")

    # Date source breakdown
    logger.info("")
    logger.info("Date source breakdown:")
    logger.info(f"  Facebook HTML index:   {date_source_counts['facebook_html']}")
    logger.info(f"  Facebook sidecar JSON: {date_source_counts['facebook_sidecar']}")
    logger.info(f"  EXIF metadata:         {date_source_counts['exif']}")
    logger.info(f"  File modification:     {date_source_counts['file_mtime']}")
    logger.info(f"  Current date (warn):   {date_source_counts['current_date']}")
    logger.info(f"  Unknown:               {date_source_counts['unknown']}")
    logger.info("=" * 60)

    # Send notification if files were moved
    total_moved = stats["photos"] + stats["videos"] + stats["audio"]
    if total_moved > 0 and not dry_run:
        notifications.send(
            title="Media Organizer Complete",
            message=f"Moved {total_moved} files ({stats['photos']} photos, "
                    f"{stats['videos']} videos, {stats['audio']} audio)",
        )

    return (stats["photos"], stats["videos"], stats["audio"])


# =============================================================================
# EXIFTOOL FUNCTIONS
# =============================================================================

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


def extract_media_metadata(file_path: Path) -> Dict[str, str]:
    """
    Extract metadata from media file using ExifTool.

    Returns dictionary with metadata fields:
    - DateTimeOriginal, CreateDate, MediaCreateDate (dates)
    - Make, Model (camera info)
    - GPSLatitude, GPSLongitude (location)
    """
    if not check_exiftool():
        return {}

    try:
        result = subprocess.run(
            ["exiftool", "-j", "-n", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            if data and isinstance(data, list) and len(data) > 0:
                return data[0]

        return {}
    except Exception as e:
        logger.debug(f"ExifTool error for {file_path}: {e}")
        return {}


def write_exif_tags(file_path: Path, tags: List[str]) -> bool:
    """
    Write EXIF keywords/tags to a media file using ExifTool.

    Args:
        file_path: Path to the media file
        tags: List of keyword tags to write

    Returns:
        bool: True if successful, False otherwise
    """
    if not tags or not check_exiftool():
        return False

    try:
        tag_args = []
        for tag in tags:
            tag_args.extend([f"-Keywords+={tag}", f"-Subject+={tag}"])

        result = subprocess.run(
            ["exiftool", "-overwrite_original"] + tag_args + [str(file_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        return result.returncode == 0
    except Exception:
        return False


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_md5(file_path: Path) -> Optional[str]:
    """Calculate MD5 hash of a file for duplicate detection."""
    try:
        hasher = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None


def _detect_facebook_backup(
    dest_base: Path, source_path: Optional[Path]
) -> Optional[Path]:
    """Detect if we're processing a Facebook backup folder."""
    for folder in [dest_base, source_path]:
        if folder and folder.exists():
            photos_folder = folder / "photos"
            if photos_folder.exists() and list(photos_folder.rglob("index.htm")):
                return folder
    return None


# =============================================================================
# FACEBOOK BACKUP PROCESSING
# =============================================================================

def build_facebook_html_lookup(base_folder: Path) -> Dict[str, datetime]:
    """
    Build a lookup table of filename -> datetime from Facebook HTML index files.

    WHY: Facebook exports often lack EXIF dates. The HTML index.htm files
    contain the original upload dates. Building a lookup table once is more
    efficient than parsing HTML for each file.
    """
    lookup: Dict[str, datetime] = {}

    photos_folder = base_folder / "photos"
    if not photos_folder.exists():
        return lookup

    html_files = list(photos_folder.rglob("index.htm"))
    logger.info(f"Found {len(html_files)} HTML index files")

    for html_file in html_files:
        try:
            with open(html_file, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()

            # Parse HTML to extract date for each photo
            dates_in_file = _parse_facebook_html_dates(html_content)
            lookup.update(dates_in_file)

        except Exception as e:
            logger.debug(f"Error parsing {html_file}: {e}")

    logger.info(f"Built lookup table with {len(lookup)} entries")
    return lookup


def _parse_facebook_html_dates(html_content: str) -> Dict[str, datetime]:
    """Parse Facebook HTML to extract filename -> date mappings."""
    result: Dict[str, datetime] = {}

    class FacebookDateParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.current_img = None
            self.in_meta = False
            self.pending_filename = None

        def handle_starttag(self, tag, attrs):
            if tag == "img":
                for attr, value in attrs:
                    if attr == "src":
                        # Extract filename from src
                        self.pending_filename = Path(value).name
            elif tag == "div":
                for attr, value in attrs:
                    if attr == "class" and "meta" in value:
                        self.in_meta = True

        def handle_data(self, data):
            if self.pending_filename and self.in_meta:
                date_str = data.strip()
                if any(
                    day in date_str
                    for day in [
                        "Monday", "Tuesday", "Wednesday", "Thursday",
                        "Friday", "Saturday", "Sunday"
                    ]
                ):
                    parsed_date = _parse_facebook_date_string(date_str)
                    if parsed_date:
                        result[self.pending_filename] = parsed_date
                    self.pending_filename = None

        def handle_endtag(self, tag):
            if tag == "div":
                self.in_meta = False

    try:
        parser = FacebookDateParser()
        parser.feed(html_content)
    except Exception:
        pass

    return result


def _parse_facebook_date_string(date_str: str) -> Optional[datetime]:
    """Parse Facebook date format: 'Wednesday, August 4, 2010 at 2:20am CDT'."""
    # Try to extract just the date part
    match = re.search(r"(\w+day), (\w+) (\d+), (\d{4})", date_str)
    if match:
        try:
            month_name = match.group(2)
            day = int(match.group(3))
            year = int(match.group(4))
            month_num = config.MONTH_NAMES.index(month_name) + 1
            return datetime(year, month_num, day)
        except (ValueError, IndexError):
            pass
    return None


def extract_facebook_html_date(file_path: Path) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Look up date from the global Facebook HTML date lookup table.

    Returns:
        (datetime, method) if found, else (None, None)
    """
    if not FACEBOOK_HTML_DATE_LOOKUP:
        return None, None

    filename = file_path.name
    if filename in FACEBOOK_HTML_DATE_LOOKUP:
        return FACEBOOK_HTML_DATE_LOOKUP[filename], "Facebook HTML index"

    return None, None


def extract_facebook_sidecar_date(file_path: Path) -> Tuple[Optional[datetime], Optional[str]]:
    """
    Extract date from a Facebook sidecar JSON file (same basename with .json).

    Returns:
        (datetime, method) if found, else (None, None)
    """
    # Try both .ext.json and .json patterns
    candidate = file_path.with_suffix(file_path.suffix + ".json")
    if not candidate.exists():
        candidate = file_path.with_suffix(".json")
    if not candidate.exists():
        return None, None

    try:
        with open(candidate, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Common Facebook fields
        for key in ["creation_timestamp", "taken_timestamp", "media_created_timestamp"]:
            if key in data:
                ts = data[key]
                try:
                    dt = datetime.fromtimestamp(int(ts))
                    return dt, f"facebook sidecar: {key}"
                except Exception:
                    continue

        # Some exports nest under media_metadata/photo
        media_meta = data.get("media_metadata", {})
        photo_meta = media_meta.get("photo", {}) if isinstance(media_meta, dict) else {}
        for key in ["taken_timestamp", "creation_timestamp"]:
            if key in photo_meta:
                ts = photo_meta[key]
                try:
                    dt = datetime.fromtimestamp(int(ts))
                    return dt, f"facebook sidecar: media_metadata.photo.{key}"
                except Exception:
                    continue

    except Exception:
        pass

    return None, None


# =============================================================================
# DATE EXTRACTION
# =============================================================================

def get_media_date(
    file_path: Path, metadata: Optional[Dict] = None
) -> Tuple[Optional[datetime], str]:
    """
    Extract date from media file using fallback chain.

    Fallback order:
    1. Facebook HTML index (if available)
    2. Facebook sidecar JSON
    3. EXIF DateTimeOriginal
    4. EXIF CreateDate
    5. EXIF MediaCreateDate
    6. File modification time
    7. Current date (last resort)

    Args:
        file_path: Path to the media file
        metadata: Optional pre-extracted metadata dict

    Returns:
        (datetime, method_string) tuple
    """
    # 1. Try Facebook HTML lookup
    date_obj, method = extract_facebook_html_date(file_path)
    if date_obj:
        return date_obj, method

    # 2. Try Facebook sidecar JSON
    date_obj, method = extract_facebook_sidecar_date(file_path)
    if date_obj:
        return date_obj, method

    # 3. Try EXIF metadata
    if metadata is None:
        metadata = extract_media_metadata(file_path)

    if metadata:
        # Try date fields in order of preference
        date_fields = [
            "DateTimeOriginal",
            "CreateDate",
            "MediaCreateDate",
            "ModifyDate",
        ]

        for field in date_fields:
            if field in metadata:
                date_obj = parse_exif_date(str(metadata[field]))
                if date_obj:
                    return date_obj, f"EXIF {field}"

    # 4. Try file modification time
    try:
        mtime = file_path.stat().st_mtime
        date_obj = datetime.fromtimestamp(mtime)
        return date_obj, "file modification time"
    except Exception:
        pass

    # 5. Last resort: current date (with warning)
    logger.warning(f"Using current date for {file_path.name} (no date found)")
    return datetime.now(), "current date (fallback)"


def parse_exif_date(date_str: str) -> Optional[datetime]:
    """
    Parse EXIF date string to datetime.

    Common formats:
    - "2024:01:15 14:30:00"
    - "2024-01-15T14:30:00"
    - "2024-01-15 14:30:00"
    """
    if not date_str or date_str == "0000:00:00 00:00:00":
        return None

    formats = [
        "%Y:%m:%d %H:%M:%S",      # Standard EXIF format
        "%Y-%m-%dT%H:%M:%S",      # ISO format
        "%Y-%m-%d %H:%M:%S",      # Alternative format
        "%Y:%m:%d %H:%M:%S%z",    # With timezone
        "%Y-%m-%dT%H:%M:%S%z",    # ISO with timezone
    ]

    # Clean up string (remove timezone suffix like "+00:00" if not in format)
    clean_str = date_str.strip()

    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue

    # Try without timezone suffix
    if "+" in clean_str:
        clean_str = clean_str.split("+")[0]
    elif "-" in clean_str and clean_str.count("-") > 2:
        # Might have timezone like "-05:00"
        parts = clean_str.rsplit("-", 1)
        if ":" in parts[-1]:
            clean_str = parts[0]

    for fmt in formats[:3]:  # Try first 3 formats without timezone
        try:
            return datetime.strptime(clean_str, fmt)
        except ValueError:
            continue

    return None


# =============================================================================
# FILE TYPE DETECTION
# =============================================================================

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


# =============================================================================
# PATH BUILDING
# =============================================================================

def get_destination_folder(
    year: int,
    month: int,
    media_type: str,
    base_folder: Path,
    event: Optional[str] = None,
) -> Path:
    """
    Build the destination folder path.

    Structure: Year/MM_MonthName/MediaType[/Event]
    Example: 2024/01_January/Photos

    Args:
        year: Year number
        month: Month number (1-12)
        media_type: 'photo', 'video', or 'audio'
        base_folder: Base media folder path
        event: Optional event/source name

    Returns:
        Full destination folder path
    """
    month_name = config.MONTH_NAMES[month - 1]
    month_folder = f"{month:02d}_{month_name}"

    type_folder = {
        "photo": "Photos",
        "video": "Videos",
        "audio": "Audio",
    }.get(media_type, "Other")

    dest_folder = base_folder / str(year) / month_folder / type_folder

    if event:
        dest_folder = dest_folder / event

    # Create folder if it doesn't exist
    dest_folder.mkdir(parents=True, exist_ok=True)

    return dest_folder


def format_filename(date_obj: datetime, original_name: str) -> str:
    """
    Format filename with date prefix.

    Format: YYYY-MM-DD_HH-MM-SS_OriginalName.ext

    Args:
        date_obj: Date to use for prefix
        original_name: Original filename

    Returns:
        Formatted filename
    """
    timestamp = date_obj.strftime("%Y-%m-%d_%H-%M-%S")
    return f"{timestamp}_{original_name}"


def get_unique_filename(dest_folder: Path, filename: str) -> Path:
    """
    Get a unique filename in the destination folder.

    If file already exists, append _1, _2, etc.

    Args:
        dest_folder: Destination folder
        filename: Desired filename

    Returns:
        Full path with unique filename
    """
    dest_path = dest_folder / filename

    if not dest_path.exists():
        return dest_path

    # File exists, add suffix
    stem = dest_path.stem
    suffix = dest_path.suffix
    counter = 1

    while dest_path.exists():
        dest_path = dest_folder / f"{stem}_{counter}{suffix}"
        counter += 1

    return dest_path


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
    year = date.year
    month = date.month

    dest_folder = get_destination_folder(
        year, month, media_type, config.MEDIA_BASE_FOLDER
    )

    new_name = format_filename(date, file_path.name)

    return get_unique_filename(dest_folder, new_name)


# =============================================================================
# CORE ORGANIZATION LOGIC
# =============================================================================

def organize_file(
    file_path: Path,
    dry_run: bool = False,
    copy_then_delete: bool = True,
    dest_base: Optional[Path] = None,
    event: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict:
    """
    Organize a single media file.

    Args:
        file_path: Path to media file
        dry_run: Preview mode (don't move files)
        copy_then_delete: Copy first, then delete (safer)
        dest_base: Base destination folder
        event: Optional event/source name (creates subfolder)
        tags: Optional EXIF tags to write to file

    Returns dictionary with operation details:
    - status: 'moved', 'would_move', 'skipped', 'error'
    - from_path, to_path, new_name, etc.
    """
    if dest_base is None:
        dest_base = config.MEDIA_BASE_FOLDER

    result = {
        "file": file_path.name,
        "status": "error",
        "from_path": str(file_path),
        "to_path": None,
        "new_name": None,
        "error": None,
        "date_method": None,
        "media_type": None,
        "year": None,
        "month": None,
    }

    # Get media type
    media_type = get_media_type(file_path)
    if not media_type:
        result["error"] = "Unknown media type"
        return result

    result["media_type"] = media_type

    # Get date
    date_obj, method = get_media_date(file_path)
    if not date_obj:
        result["error"] = "Could not extract date"
        return result

    result["date_method"] = method
    result["year"] = date_obj.year
    result["month"] = date_obj.month

    # Get destination folder
    dest_folder = get_destination_folder(
        date_obj.year, date_obj.month, media_type, base_folder=dest_base, event=event
    )

    # Format filename
    new_name = format_filename(date_obj, file_path.name)

    # Get unique filename if needed
    dest_path = get_unique_filename(dest_folder, new_name)
    result["new_name"] = dest_path.name

    # Check if already in correct location
    try:
        if file_path.resolve() == dest_path.resolve():
            result["status"] = "skipped"
            result["error"] = "Already in correct location"
            return result
    except Exception:
        pass

    # Check for duplicate content (if file exists at destination)
    if dest_path.exists() and file_path.exists():
        source_hash = get_md5(file_path)
        dest_hash = get_md5(dest_path)

        if source_hash and dest_hash and source_hash == dest_hash:
            result["status"] = "skipped"
            result["error"] = "Duplicate content (same MD5 hash)"
            return result

    # Perform move/copy
    try:
        if not dry_run:
            if copy_then_delete:
                # Copy first
                shutil.copy2(file_path, dest_path)

                # Verify copy was successful
                if dest_path.exists() and dest_path.stat().st_size == file_path.stat().st_size:
                    # Write EXIF tags if specified
                    if tags:
                        write_exif_tags(dest_path, tags)
                    # Delete original
                    file_path.unlink()
                else:
                    result["error"] = "Copy verification failed"
                    return result
            else:
                # Direct move
                shutil.move(str(file_path), str(dest_path))
                # Write EXIF tags if specified
                if tags:
                    write_exif_tags(dest_path, tags)

        result["status"] = "moved" if not dry_run else "would_move"
        result["to_path"] = str(dest_path)

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error organizing {file_path.name}: {e}")

    return result


def scan_and_audit_folders(
    auto_yes: bool = False,
    dry_run: bool = False,
    dest_base: Optional[Path] = None,
    event: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Tuple[List[Dict], int]:
    """
    Recursively scan Media folder and fix misplaced files.

    Args:
        auto_yes: Skip prompts
        dry_run: Preview changes without moving files
        dest_base: Base folder to scan
        event: Optional event/source name
        tags: Optional EXIF tags to write

    Returns:
        tuple: (list of moved files, total scanned)
    """
    if dest_base is None:
        dest_base = config.MEDIA_BASE_FOLDER

    moved_files: List[Dict] = []
    total_scanned = 0

    if not dest_base.exists():
        return moved_files, total_scanned

    # Find all media files recursively
    all_files: List[Path] = []
    for ext in config.ALL_MEDIA_EXTENSIONS:
        all_files.extend(dest_base.rglob(f"*{ext}"))
        all_files.extend(dest_base.rglob(f"*{ext.upper()}"))

    total_files = len(all_files)

    if total_files == 0:
        return moved_files, 0

    logger.info(f"Scanning {total_files} media files...")

    for file_path in all_files:
        total_scanned += 1

        try:
            result = organize_file(
                file_path,
                dry_run=dry_run,
                copy_then_delete=True,
                dest_base=dest_base,
                event=event,
                tags=tags,
            )

            if result["status"] in ["moved", "would_move"]:
                moved_files.append(result)

        except Exception as e:
            logger.debug(f"Error auditing {file_path.name}: {e}")
            continue

    return moved_files, total_scanned
