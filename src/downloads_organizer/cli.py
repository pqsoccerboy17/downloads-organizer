"""
Command-line interface for Downloads Organizer.

Provides unified CLI for both PDF and media organization.
"""

import argparse
import sys


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="downloads-organizer",
        description="Unified Downloads folder organizer for PDFs and media",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # PDF organizer
    pdf_parser = subparsers.add_parser("pdf", help="Organize PDF documents")
    pdf_parser.add_argument("--dry-run", action="store_true", help="Preview without moving files")
    pdf_parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm all actions")
    pdf_parser.add_argument("--audit", action="store_true", help="Audit existing folders")
    pdf_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Media organizer
    media_parser = subparsers.add_parser("media", help="Organize media files")
    media_parser.add_argument("--dry-run", action="store_true", help="Preview without moving files")
    media_parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm all actions")
    media_parser.add_argument("--audit", action="store_true", help="Audit existing folders")
    media_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Watcher
    watch_parser = subparsers.add_parser("watch", help="Watch Downloads folder")
    watch_parser.add_argument("--pdf-only", action="store_true", help="Only watch for PDFs")
    watch_parser.add_argument("--media-only", action="store_true", help="Only watch for media")
    watch_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    # Status
    subparsers.add_parser("status", help="Show organizer status")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "pdf":
        from . import pdf_organizer
        pdf_organizer.run(
            dry_run=args.dry_run,
            auto_yes=args.yes,
            audit=args.audit,
            verbose=args.verbose,
        )

    elif args.command == "media":
        from . import media_organizer
        media_organizer.run(
            dry_run=args.dry_run,
            auto_yes=args.yes,
            audit=args.audit,
            verbose=args.verbose,
        )

    elif args.command == "watch":
        from . import watcher
        watcher.run(
            pdf_only=args.pdf_only,
            media_only=args.media_only,
            verbose=args.verbose,
        )

    elif args.command == "status":
        print_status()

    else:
        parser.print_help()
        sys.exit(1)


def print_status():
    """Print current organizer status."""
    from pathlib import Path
    from . import config

    print("=" * 50)
    print("Downloads Organizer Status")
    print("=" * 50)

    # Check Downloads folder
    pdf_count = len(list(config.DOWNLOADS_FOLDER.glob("*.pdf")))
    media_count = sum(
        len(list(config.DOWNLOADS_FOLDER.glob(f"*{ext}")))
        for ext in config.ALL_MEDIA_EXTENSIONS
    )

    print(f"\nDownloads folder: {config.DOWNLOADS_FOLDER}")
    print(f"  PDFs pending: {pdf_count}")
    print(f"  Media pending: {media_count}")

    # Check destinations
    print(f"\nTax folder: {config.TAX_BASE_FOLDER}")
    print(f"  Exists: {config.TAX_BASE_FOLDER.exists()}")

    print(f"\nMedia folder: {config.MEDIA_BASE_FOLDER}")
    print(f"  Exists: {config.MEDIA_BASE_FOLDER.exists()}")

    # Check notifications
    from . import notifications
    print(f"\nNotifications: {'Available' if notifications.notifications_available() else 'Not configured'}")

    print("=" * 50)


if __name__ == "__main__":
    main()
