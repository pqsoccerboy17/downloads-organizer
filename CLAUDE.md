# Downloads Organizer

## Project Overview
Unified Downloads folder organizer that automatically categorizes and moves:
- **PDFs**: Bank statements, tax documents, receipts → Google Drive tax folders
- **Media**: Photos, videos, audio → Google Drive media folders

Consolidates functionality from tax-pdf-organizer and media-organizer into a single tool.

## About the Developer
- **Non-developer user** - I rely on Claude Code to write, test, and manage code
- Always explain what you're doing in plain English before executing
- Prefer small, incremental changes that can be easily reviewed
- Ask for confirmation before any destructive or irreversible actions

## Tech Stack
- **Language**: Python 3.10+
- **PDF Processing**: PyMuPDF (fitz)
- **Media Metadata**: ExifTool (system dependency)
- **File Watching**: watchdog
- **Notifications**: ~/scripts/notify.py (Pushover + macOS)

## Key Commands
```bash
# Run PDF organizer
python -m downloads_organizer pdf

# Run media organizer
python -m downloads_organizer media

# Run watcher (both)
python -m downloads_organizer watch

# Dry run (preview only)
python -m downloads_organizer pdf --dry-run
python -m downloads_organizer media --dry-run
```

## File Structure
```
src/downloads_organizer/
├── __init__.py
├── cli.py              # Command-line interface
├── config.py           # Unified configuration
├── utils.py            # Shared utilities
├── notifications.py    # Notification integration
├── pdf_organizer.py    # Tax PDF organization logic
├── media_organizer.py  # Media organization logic
└── watcher.py          # Unified Downloads watcher
```

## Destination Folders
- **PDFs**: ~/Library/CloudStorage/GoogleDrive-.../Personal/Taxes/{Year} Tax Year/
- **Media**: ~/Library/CloudStorage/GoogleDrive-.../Personal/Media/{Year}/{Month}/

## Development Workflow
1. **Understand** - Explain what needs to be done
2. **Plan** - Show approach before coding
3. **Implement** - Make small, focused changes
4. **Test** - Run with --dry-run first
5. **Commit** - Use clear, descriptive commit messages

## Code Style
- Python: Follow PEP 8, use type hints
- Keep functions focused and documented
- Add docstrings explaining purpose
- Use logging instead of print statements

## Safety Rules
- **Never** move files without user confirmation (unless --yes flag)
- **Always** support --dry-run mode
- **Always** check for duplicates before moving
- **Never** delete originals until copy is verified
- **Ask** before any destructive operations

## Dependencies
- PyMuPDF: PDF text extraction
- watchdog: File system monitoring
- tqdm: Progress bars
- ExifTool: Media metadata (install via `brew install exiftool`)

## Migration Notes
This repo consolidates:
- tax-pdf-organizer (bank statements, tax forms)
- media-organizer (photos, videos, audio)

Original repos will be deprecated after migration is complete and tested.
