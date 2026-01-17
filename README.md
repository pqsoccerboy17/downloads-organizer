# Downloads Organizer

Unified Downloads folder organizer that automatically categorizes and moves PDFs and media files to organized Google Drive folders.

## Features

### PDF Organizer
- Bank statement detection and organization by year
- Tax document categorization (W-2, 1099, receipts)
- Duplicate detection via MD5 checksums
- Work document exclusion (proposals, SOWs, etc.)

### Media Organizer
- Photo/video/audio organization by date
- EXIF metadata extraction
- Year/Month folder structure
- Support for RAW formats and HEIC

### Unified Watcher
- Watches Downloads folder for new files
- Automatically routes PDFs and media to respective organizers
- Debouncing for in-progress downloads
- Push notifications on completion

## Installation

```bash
# Clone the repository
git clone https://github.com/pqsoccerboy17/downloads-organizer.git
cd downloads-organizer

# Install dependencies
pip install -e .

# Install ExifTool (required for media organization)
brew install exiftool
```

## Usage

```bash
# Organize PDFs
python -m downloads_organizer pdf

# Organize media
python -m downloads_organizer media

# Run watcher (both types)
python -m downloads_organizer watch

# Dry run (preview only)
python -m downloads_organizer pdf --dry-run
python -m downloads_organizer media --dry-run
```

## Configuration

Edit `src/downloads_organizer/config.py` to customize:
- Source folders to scan
- Destination paths
- Bank account patterns
- File type extensions

## Destination Structure

### PDFs (Tax Documents)
```
~/Google Drive/Personal/Taxes/
├── 2024 Tax Year/
│   ├── Bank Statements/
│   │   ├── Colonial Checking - 0675/
│   │   ├── Chase Credit Card/
│   │   └── ...
│   ├── Tax Forms/
│   └── Receipts/
└── 2025 Tax Year/
    └── ...
```

### Media
```
~/Google Drive/Personal/Media/
├── 2024/
│   ├── January/
│   │   ├── Photos/
│   │   ├── Videos/
│   │   └── Audio/
│   └── February/
│       └── ...
└── 2025/
    └── ...
```

## Notifications

Supports push notifications via:
- **Pushover** (mobile/desktop) - requires API credentials
- **macOS Notification Center** (fallback)

Configure in `~/scripts/ecosystem.env`:
```bash
export PUSHOVER_USER_KEY="your-key"
export PUSHOVER_APP_TOKEN="your-token"
```

## Migration from Legacy Repos

This repo consolidates:
- [tax-pdf-organizer](https://github.com/pqsoccerboy17/tax-pdf-organizer)
- [media-organizer](https://github.com/pqsoccerboy17/media-organizer)

Both legacy repos will be deprecated after migration is complete.

## License

MIT
