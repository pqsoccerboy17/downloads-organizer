"""
PDF Organizer - Tax document and bank statement organization.

This module handles the organization of PDF files from Downloads into
a structured Google Drive tax folder hierarchy.

Migrated from: tax-pdf-organizer/organize_statements.py

DOCUMENT TYPES SUPPORTED:
- Bank statements (Chase, Colonial, AMEX)
- Investment tax forms (Fidelity 1099, Vanguard 1099/5498)
- STR rental income (Airbnb/VRBO via STR Management)
- General tax documents (W-2, 1099, receipts, insurance, etc.)

DESIGN PRINCIPLES:
- Conservative categorization (90%+ confidence threshold)
- Global exclusions for work documents (proposals, SOWs, etc.)
- Strict IRS form patterns to avoid false positives
- Duplicate detection via MD5 checksums
"""

import hashlib
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from downloads_organizer import config
from downloads_organizer import utils
from downloads_organizer import notifications

logger = logging.getLogger(__name__)

# =============================================================================
# DOCUMENT TYPE CONFIGURATIONS
# =============================================================================
# Each document type needs specific patterns for identification and date extraction.
# Order matters - more specific patterns should come before general ones.

DOCUMENT_TYPES = {
    'STR_RENTAL': {
        'name': 'STR Rental Income',
        'account_number': 'Montclaire',
        'folder_name': 'STR Management',
        'filename_patterns': ['STR', 'MONTCLAIRE', 'AIRBNB'],
        'content_keywords': [
            'STR MANAGEMENT', 'S.T.R. MANAGEMENT', 'STRMANAGEMENT.COM',
            'SHORT TERM RENTAL MANAGEMENT', '2200 MONTCLAIRE',
            'STATEMENT OF ACCOUNT', 'RENTAL INCOME', 'DISTRIBUTION', 'RENTS'
        ],
        'date_extraction': 'str_rental',
        'destination_category': 'Bank Statements'
    },
    'VANGUARD_TAX_FORMS': {
        'name': 'Vanguard Brokerage',
        'account_number': 'extracted',
        'folder_name_template': 'PERS | Vanguard Brokerage ({account})',
        'filename_patterns': ['VANGUARD', '1099', '5498', 'BROKERAGE'],
        'content_keywords': ['VANGUARD', 'FORM 1099', 'FORM 5498', 'VANGUARD BROKERAGE SERVICES'],
        'date_extraction': 'vanguard_tax_forms',
        'destination_category': 'Tax Forms',
        'account_identifier': 'account_extraction'
    },
    'FIDELITY_1099': {
        'name': 'Fidelity Brokerage',
        'account_number': 'extracted',
        'folder_name_template': 'PERS | Fidelity Brokerage ({account})',
        'filename_patterns': ['TAX REPORTING STATEMENT', 'FIDELITY', '1099', '5498'],
        'content_keywords': ['FIDELITY', 'FORM 1099', 'FORM 5498', 'TAX REPORTING STATEMENT', 'NATIONAL FINANCIAL SERVICES'],
        'date_extraction': 'fidelity_1099',
        'destination_category': 'Tax Forms',
        'account_identifier': 'account_extraction'
    },
    'COLONIAL': {
        'name': 'Colonial Loan',
        'account_number': '7063',
        'folder_name': 'TH | Colonial Loan (7063)',
        'filename_patterns': ['LIS VIEW DOCUMENT', 'COLONIAL', '7063'],
        'content_keywords': ['COLONIAL', 'MONTHLY BILLING STATEMENT', 'ACCOUNT NUMBER 30197063'],
        'date_extraction': 'generic',
        'account_identifier': '7063'
    },
    'AMEX_PERS': {
        'name': 'AMEX CC',
        'account_number': '91004',
        'folder_name': 'PERS | AMEX CC (91004)',
        'filename_patterns': ['ACCOUNT ACTIVITY'],
        'content_keywords': ['AMERICAN EXPRESS', 'AMEX'],
        'date_extraction': 'amex',
        'account_identifier': '91004'
    },
    'AMEX_BIZ': {
        'name': 'AMEX Amazon CC',
        'account_number': '41004',
        'folder_name': 'TH | AMEX Amazon CC (41004)',
        'filename_patterns': ['ACCOUNT ACTIVITY'],
        'content_keywords': ['AMERICAN EXPRESS', 'AMEX'],
        'date_extraction': 'amex',
        'account_identifier': '41004'
    },
    'CHASE_LOAN': {
        'name': 'Chase Loan',
        'account_number': '0675',
        'folder_name': 'PERS | Chase Loan (0675)',
        'filename_patterns': ['STATEMENTS', 'ESCROW', 'MORTGAGE'],
        'content_keywords': ['JPMORGAN CHASE', 'CHASE HOME LENDING', 'CHASE MORTGAGE', 'ESCROW'],
        'date_extraction': 'chase',
        'account_identifier': '0675'
    },
    'CHASE_CC': {
        'name': 'Chase CC',
        'account_number': '5934',
        'folder_name': 'PERS | Chase CC (5934)',
        'filename_patterns': ['CHASE', 'CREDIT CARD'],
        'content_keywords': ['JPMORGAN CHASE', 'CHASE.COM', 'CREDIT CARD ACCOUNT'],
        'date_extraction': 'chase'
    },
    'FREEDOM_MORTGAGE': {
        'name': 'Freedom Mortgage',
        'account_number': '5438',
        'folder_name': 'PERS | Freedom Mortgage (5438)',
        'filename_patterns': ['BILLING', 'FREEDOM', 'MORTGAGE'],
        'content_keywords': ['FREEDOM MORTGAGE', 'FREEDOMMORTGAGE.COM', 'MORTGAGE STATEMENT'],
        'date_extraction': 'generic',
        'account_identifier': '5438'
    },
}

# =============================================================================
# DOCUMENT CATEGORY CONFIGURATIONS (Non-Bank Documents)
# =============================================================================
# Conservative categorization to prevent false positives.

DOCUMENT_CATEGORIES = {
    'TAX_FORMS': {
        'folder': 'Tax Forms',
        'patterns': [
            'FORM W-2', 'W-2 WAGE', 'WAGE AND TAX STATEMENT',
            'FORM 1099', '1099-INT', '1099-DIV', '1099-MISC', '1099-NEC', '1099-B', '1099-R',
            'FORM 1040', 'FORM 1098', '1098-E', '1098-T',
            'FORM 5498', 'IRA CONTRIBUTION', 'FORM 1095',
            'SCHEDULE K-1', 'IRS FORM', 'INTERNAL REVENUE SERVICE'
        ],
        'filename_patterns': ['w-2', 'w2', '1099', '1040', '1098', '5498', '1095', 'k-1'],
        'exclude_patterns': [
            'PROPOSAL', 'SOW', 'STATEMENT OF WORK', 'PRESENTATION',
            'INFOCENTER', 'MANAGED SERVICES', 'EXECUTIVE', 'VENDOR'
        ]
    },
    'RECEIPTS': {
        'folder': 'Receipts',
        'patterns': [
            'RECEIPT FOR PAYMENT', 'PAYMENT RECEIPT',
            'PAID IN FULL', 'INVOICE PAID', 'TRANSACTION RECEIPT'
        ],
        'filename_patterns': ['receipt', 'paid'],
        'exclude_patterns': ['PROPOSAL', 'QUOTE', 'ESTIMATE', 'SOW', 'DRAFT']
    },
    'INSURANCE': {
        'folder': 'Insurance',
        'patterns': [
            'INSURANCE POLICY', 'POLICY NUMBER', 'COVERAGE SUMMARY',
            'INSURANCE PREMIUM', 'DECLARATIONS PAGE'
        ],
        'filename_patterns': ['insurance policy', 'coverage'],
        'exclude_patterns': ['PROPOSAL', 'QUOTE', 'ESTIMATE']
    },
    'MEDICAL': {
        'folder': 'Medical',
        'patterns': [
            'EXPLANATION OF BENEFITS', 'EOB', 'PATIENT STATEMENT',
            'MEDICAL BILL', 'HEALTHCARE STATEMENT'
        ],
        'filename_patterns': ['eob', 'patient statement', 'medical bill'],
        'exclude_patterns': ['PROPOSAL', 'ESTIMATE']
    },
    'LEGAL': {
        'folder': 'Legal',
        'patterns': [
            'LEASE AGREEMENT', 'RENTAL AGREEMENT',
            'PROPERTY DEED', 'WARRANTY DEED', 'TITLE INSURANCE', 'NOTARIZED'
        ],
        'filename_patterns': ['lease', 'deed', 'title'],
        'exclude_patterns': ['PROPOSAL', 'SOW', 'BUSINESS', 'CORPORATE', 'VENDOR']
    },
    'PROPERTY': {
        'folder': 'Property',
        'patterns': [
            'PROPERTY TAX STATEMENT', 'PROPERTY TAX BILL', 'TAX ASSESSOR',
            'REAL ESTATE TAX', 'COUNTY TAX', 'APPRAISAL DISTRICT'
        ],
        'filename_patterns': ['property tax', 'real estate tax'],
        'exclude_patterns': ['PROPOSAL', 'ESTIMATE']
    },
}

# Global exclusions - NEVER categorize these as tax documents
GLOBAL_EXCLUSIONS = [
    'PROPOSAL', 'SOW', 'STATEMENT OF WORK',
    'INFOCENTER', 'BUC-EE', 'BUCEE',
    '.PPT', 'POWERPOINT', 'PRESENTATION',
    'EXECUTIVE SUMMARY', 'MANAGED SERVICES',
    'PARTNERSHIP AGREEMENT', 'VENDOR', 'CLIENT',
    'NIKE', 'ZILLOW', 'CODEIUM', 'SERVICENOW',
    'BETTER CHAT', 'DREAM BIGGER', 'URBANE',
]


# =============================================================================
# PDF TEXT EXTRACTION
# =============================================================================

def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract text from PDF using PyMuPDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Extracted text, "NO_TEXT" if empty, or "ERROR: ..." on failure
    """
    if fitz is None:
        return "ERROR: PyMuPDF not installed"

    doc = None
    try:
        doc = fitz.open(str(pdf_path))
        text = ""
        for page_num in range(len(doc)):
            page = doc[page_num]
            text += page.get_text()
        return text if text.strip() else "NO_TEXT"
    except Exception as e:
        return f"ERROR: {str(e)}"
    finally:
        if doc is not None:
            doc.close()


# =============================================================================
# DOCUMENT TYPE DETECTION
# =============================================================================

def detect_document_type(filename: str, text: str) -> Tuple[Optional[str], Optional[dict]]:
    """
    Detect which document type this PDF is.

    Args:
        filename: PDF filename
        text: Extracted PDF text

    Returns:
        Tuple of (doc_type_id, config) or (None, None) if not recognized
    """
    filename_upper = filename.upper()
    text_upper = text.upper() if text and text != "NO_TEXT" and not text.startswith("ERROR:") else ""

    for doc_type, doc_config in DOCUMENT_TYPES.items():
        # Check filename patterns
        filename_match = any(pattern in filename_upper for pattern in doc_config['filename_patterns'])

        # Check content keywords
        content_match = any(keyword in text_upper for keyword in doc_config['content_keywords']) if text_upper else False

        # Special validation for AMEX
        if doc_type.startswith('AMEX') and (filename_match or content_match):
            if 'CLOSING DATE' not in text_upper:
                continue
            if 'account_identifier' in doc_config:
                account_id = doc_config['account_identifier']
                if account_id not in text_upper and f'9-{account_id}' not in text_upper:
                    continue

        # Special validation for Chase
        if doc_type.startswith('CHASE') and (filename_match or content_match):
            has_statement = any(ind in text_upper for ind in ['STATEMENT DATE', 'CLOSING DATE', 'ACCOUNT STATEMENT'])
            is_chase_file = any(p in filename_upper for p in ['BILLING', 'ESCROW', 'STATEMENTS'])
            if not (has_statement or is_chase_file):
                continue
            if doc_type == 'CHASE_LOAN' and 'account_identifier' in doc_config:
                if doc_config['account_identifier'] not in text_upper:
                    continue

        # Special validation for Vanguard
        if doc_type == 'VANGUARD_TAX_FORMS' and (filename_match or content_match):
            has_tax_forms = any(form in text_upper for form in ['FORM 1099', 'FORM 5498', '1099-DIV', '1099-INT', '1099-B'])
            has_vanguard = 'VANGUARD' in text_upper
            if not (has_tax_forms and has_vanguard):
                continue
            if not extract_vanguard_account(text_upper):
                continue

        # Special validation for Fidelity
        if doc_type == 'FIDELITY_1099' and (filename_match or content_match):
            has_fidelity_forms = any(form in text_upper for form in ['FORM 1099-DIV', 'FORM 1099-INT', 'FORM 1099-B', 'FORM 5498'])
            has_fidelity = any(kw in text_upper for kw in ['FIDELITY BROKERAGE', 'NATIONAL FINANCIAL SERVICES'])
            if not (has_fidelity_forms and has_fidelity):
                continue
            if not extract_fidelity_account(text_upper):
                continue

        # Special validation for STR Rental
        if doc_type == 'STR_RENTAL' and (filename_match or content_match):
            is_legal = any(term in text_upper for term in ['PROPERTY MANAGEMENT AGREEMENT', 'THIS AGREEMENT', 'HEREBY APPOINTS'])
            if is_legal:
                continue
            has_str_company = any(kw in text_upper for kw in ['STR MANAGEMENT', 'S.T.R. MANAGEMENT', 'STRMANAGEMENT.COM'])
            has_rental = any(kw in text_upper for kw in ['RENTAL INCOME', 'AIRBNB', 'VRBO', 'DISTRIBUTION', 'RENTS'])
            if not (has_str_company and has_rental):
                continue

        if filename_match or content_match:
            return doc_type, doc_config

    return None, None


def categorize_document(filename: str, text: str) -> Tuple[Optional[str], int]:
    """
    Categorize non-bank documents using strict three-layer validation.

    Args:
        filename: PDF filename
        text: Extracted PDF text

    Returns:
        Tuple of (category_id, confidence_score) or (None, 0)
    """
    filename_upper = filename.upper()

    # Handle missing/empty text - try filename-only categorization
    no_text = not text or text == "NO_TEXT" or text.startswith("ERROR:")
    text_upper = "" if no_text else text.upper()

    # Layer 1: Global exclusions (check filename even without text)
    for exclusion in GLOBAL_EXCLUSIONS:
        if exclusion in filename_upper or (text_upper and exclusion in text_upper):
            return None, 0

    # Layer 2: Try each category
    for category_id, cat_config in DOCUMENT_CATEGORIES.items():
        # Check category-specific exclusions
        if 'exclude_patterns' in cat_config:
            excluded = any(p in filename_upper or (text_upper and p in text_upper) for p in cat_config['exclude_patterns'])
            if excluded:
                continue

        filename_match = any(p.upper() in filename_upper for p in cat_config['filename_patterns'])
        content_match = text_upper and any(p in text_upper for p in cat_config['patterns'])

        if filename_match or content_match:
            # Lower confidence for filename-only matches (scanned PDFs)
            if filename_match and content_match:
                confidence = 95
            elif filename_match and no_text:
                confidence = 75  # Filename match but couldn't read PDF content
            else:
                confidence = 85
            return category_id, confidence

    return None, 0


# =============================================================================
# ACCOUNT NUMBER EXTRACTION
# =============================================================================

def extract_fidelity_account(text: str) -> Optional[str]:
    """Extract Fidelity account number from tax forms."""
    if not text:
        return None

    # Pattern 1: X##-###### (1099 forms)
    match = re.search(r'([A-Z]\d{2}-(\d{6}))', text, re.IGNORECASE)
    if match:
        return match.group(2)

    # Pattern 2: ###-###### (5498 forms)
    match = re.search(r'(\d{3}-(\d{6}))', text, re.IGNORECASE)
    if match:
        return match.group(2)

    # Fallback
    match = re.search(r'(?:Account|Recipient\s+ID)[^\d]{0,50}(\d{6})', text, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def extract_vanguard_account(text: str) -> Optional[str]:
    """Extract Vanguard account number from tax forms."""
    if not text:
        return None

    match = re.search(r'Account\s+(?:Number|No\.?)[:\s]+([A-Z]{0,3}-)?(\d{4,8})', text, re.IGNORECASE)
    if match:
        return match.group(2).zfill(8)

    # Fallback: standalone 8-digit number
    match = re.search(r'\b(\d{8})\b', text)
    if match:
        return match.group(1)

    return None


# =============================================================================
# DATE EXTRACTION
# =============================================================================

def extract_statement_date(text: str, filename: str, doc_config: dict) -> Tuple[Optional[str], str]:
    """
    Extract statement date based on document type.

    Args:
        text: PDF text content
        filename: PDF filename
        doc_config: Document type configuration

    Returns:
        Tuple of (date_string in MM/DD/YYYY, extraction_method) or (None, error_message)
    """
    if not text or "ERROR" in text[:100]:
        return None, "Could not read PDF"

    date_method = doc_config.get('date_extraction', 'generic')

    # STR Rental
    if date_method == 'str_rental':
        month_match = re.search(r'(\w+)\s+\d{1,2},\s+(20\d{2})\s+to\s+\w+\s+(\d{1,2}),\s+(20\d{2})', text, re.IGNORECASE)
        if month_match:
            month_name = month_match.group(1).upper()
            year = month_match.group(4)
            end_day = month_match.group(3)
            month_map = {'JANUARY': '01', 'FEBRUARY': '02', 'MARCH': '03', 'APRIL': '04',
                         'MAY': '05', 'JUNE': '06', 'JULY': '07', 'AUGUST': '08',
                         'SEPTEMBER': '09', 'OCTOBER': '10', 'NOVEMBER': '11', 'DECEMBER': '12'}
            month_num = month_map.get(month_name)
            if month_num:
                return f"{month_num}/{end_day.zfill(2)}/{year}", "STR statement period end"

        year_match = re.search(r'Tax Year[:\s]+(20\d{2})', text, re.IGNORECASE)
        if year_match:
            return f"12/31/{year_match.group(1)}", "STR tax year"

    # Vanguard tax forms
    if date_method == 'vanguard_tax_forms':
        year_match = re.search(r'(?:Tax\s+Year\s+)?(20\d{2})', text, re.IGNORECASE)
        if year_match:
            return f"12/31/{year_match.group(1)}", "Vanguard Tax Year"

    # Fidelity tax forms
    if date_method == 'fidelity_1099':
        year_match = re.search(r'(20\d{2})\s+TAX REPORTING STATEMENT', text, re.IGNORECASE)
        if year_match:
            return f"12/31/{year_match.group(1)}", "Fidelity Tax Year"
        year_match = re.search(r'(20\d{2})\s+Form\s+5498', text, re.IGNORECASE)
        if year_match:
            return f"12/31/{year_match.group(1)}", "Fidelity Form 5498 Year"

    # AMEX
    if date_method == 'amex':
        match = re.search(r'Closing Date\s+(\d{1,2}/\d{1,2}/\d{2,4})', text, re.IGNORECASE)
        if match:
            parts = match.group(1).split('/')
            if len(parts) == 3:
                month, day, year = parts
                if len(year) == 2:
                    year = f"20{year}"
                return f"{month.zfill(2)}/{day.zfill(2)}/{year}", "AMEX Closing Date"

    # Chase
    if date_method == 'chase':
        match = re.search(r'Statement Date[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})', text, re.IGNORECASE)
        if match:
            parts = match.group(1).split('/')
            if len(parts) == 3:
                month, day, year = parts
                if len(year) == 2:
                    year = f"20{year}"
                return f"{month.zfill(2)}/{day.zfill(2)}/{year}", "Chase Statement Date"

        match = re.search(r'Closing Date[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})', text, re.IGNORECASE)
        if match:
            parts = match.group(1).split('/')
            if len(parts) == 3:
                month, day, year = parts
                if len(year) == 2:
                    year = f"20{year}"
                return f"{month.zfill(2)}/{day.zfill(2)}/{year}", "Chase Closing Date"

    # Generic date extraction
    matches = re.findall(r'\b(\d{1,2}/\d{1,2}/\d{4})\b', text)
    if matches:
        parts = matches[0].split('/')
        month, day, year = parts
        return f"{month.zfill(2)}/{day.zfill(2)}/{year}", "first date in document"

    # Filename fallback
    match = re.search(r'(\d{4})(\d{2})(\d{2})', filename)
    if match:
        year, month, day = match.groups()
        return f"{month}/{day}/{year}", "filename"

    match = re.search(r'\b(20\d{2})\b', filename)
    if match:
        return f"12/31/{match.group(1)}", "filename year"

    return None, "No date found"


# =============================================================================
# FOLDER AND FILE OPERATIONS
# =============================================================================

def get_destination_folder(doc_config: dict, year: int, account_number: Optional[str] = None) -> Path:
    """
    Build destination path for a given year and create if needed.

    Args:
        doc_config: Document type configuration
        year: Year for the tax folder
        account_number: Optional account number for dynamic folder names

    Returns:
        Full destination folder path
    """
    category = doc_config.get('destination_category', 'Bank Statements')

    # Determine folder name
    if 'folder_name_template' in doc_config and account_number:
        folder_name = doc_config['folder_name_template'].format(account=account_number)
    else:
        folder_name = doc_config.get('folder_name', doc_config['name'])

    year_folder = config.TAX_BASE_FOLDER / f"{year} Tax Year" / category
    destination = year_folder / folder_name
    destination.mkdir(parents=True, exist_ok=True)

    return destination


def format_date_for_filename(date_str: str) -> Optional[str]:
    """Convert MM/DD/YYYY to MM_DD_YYYY."""
    try:
        date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        return date_obj.strftime("%m_%d_%Y")
    except ValueError:
        return None


def extract_year_from_date(date_str: str) -> Optional[int]:
    """Extract year from MM/DD/YYYY date string."""
    try:
        date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        return date_obj.year
    except ValueError:
        return None


# =============================================================================
# MAIN PROCESSING
# =============================================================================

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
        Tuple of (moved_files_count, categorized_files_count, uncategorized_count)
    """
    utils.setup_logging("pdf_organizer", verbose)

    logger.info("=" * 60)
    logger.info("PDF Organizer")
    logger.info("=" * 60)

    if fitz is None:
        logger.error("PyMuPDF not installed. Run: pip install PyMuPDF")
        return (0, 0, 0)

    if dry_run:
        logger.info("DRY RUN MODE - No files will be moved")

    moved_files, categorized_files, uncategorized_files = process_downloads(
        dry_run=dry_run,
        auto_yes=auto_yes,
    )

    if audit and config.TAX_BASE_FOLDER.exists():
        audit_moved, audit_cat, audit_uncat = audit_tax_folders(
            dry_run=dry_run,
            auto_yes=auto_yes,
        )
        moved_files.extend(audit_moved)
        categorized_files.extend(audit_cat)
        uncategorized_files.extend(audit_uncat)

    # Print summary
    print_summary(moved_files, categorized_files, uncategorized_files, dry_run)

    # Send notification
    if not dry_run and len(moved_files) + len(categorized_files) > 0:
        notifications.notify_pdf_organization(
            files_organized=len(moved_files) + len(categorized_files),
            pending_review=len(uncategorized_files),
        )

    return (len(moved_files), len(categorized_files), len(uncategorized_files))


def process_downloads(
    dry_run: bool = False,
    auto_yes: bool = False,
) -> Tuple[List[dict], List[dict], List[str]]:
    """
    Process PDF files in all source folders (Downloads, Desktop, Drive Inbox).

    Returns:
        Tuple of (moved_files, categorized_files, uncategorized_files)
    """
    moved_files = []
    categorized_files = []
    uncategorized_files = []

    # Collect PDFs from all source folders
    pdf_files = []
    for folder in config.SOURCE_FOLDERS:
        if folder.exists():
            folder_pdfs = list(folder.glob("*.pdf"))
            if folder_pdfs:
                logger.info(f"Found {len(folder_pdfs)} PDF files in {folder.name}")
                pdf_files.extend(folder_pdfs)

    if not pdf_files:
        logger.info("No PDF files found in any source folder")
        return moved_files, categorized_files, uncategorized_files

    logger.info(f"Found {len(pdf_files)} total PDF files across all source folders")

    for pdf_file in pdf_files:
        result = process_single_pdf(pdf_file, dry_run=dry_run)
        if result:
            if result['type'] == 'bank_statement':
                moved_files.append(result)
            elif result['type'] == 'categorized':
                categorized_files.append(result)
            else:
                uncategorized_files.append(pdf_file.name)
        else:
            uncategorized_files.append(pdf_file.name)

    return moved_files, categorized_files, uncategorized_files


def process_single_pdf(pdf_file: Path, dry_run: bool = False) -> Optional[dict]:
    """
    Process a single PDF file.

    Returns:
        Result dictionary or None if could not process
    """
    text = extract_text_from_pdf(pdf_file)

    # Try to detect as bank statement first
    doc_type, doc_config = detect_document_type(pdf_file.name, text)

    if doc_type:
        return process_bank_statement(pdf_file, text, doc_type, doc_config, dry_run)
    else:
        return process_general_document(pdf_file, text, dry_run)


def process_bank_statement(
    pdf_file: Path,
    text: str,
    doc_type: str,
    doc_config: dict,
    dry_run: bool = False,
) -> Optional[dict]:
    """Process a bank statement or investment tax form."""
    # Extract date
    date_str, method = extract_statement_date(text, pdf_file.name, doc_config)
    if not date_str:
        return None

    year = extract_year_from_date(date_str)
    if not year:
        return None

    # Extract account number
    if doc_config.get('account_number') == 'extracted':
        if doc_type == 'FIDELITY_1099':
            account_number = extract_fidelity_account(text)
        elif doc_type == 'VANGUARD_TAX_FORMS':
            account_number = extract_vanguard_account(text)
        elif doc_type == 'STR_RENTAL':
            account_number = 'Montclaire'
        else:
            account_number = None

        if not account_number:
            return None
    else:
        account_number = doc_config['account_number']

    # Get destination
    destination_folder = get_destination_folder(doc_config, year, account_number)

    # Format filename
    formatted_date = format_date_for_filename(date_str)
    if not formatted_date:
        return None

    new_name = f"{formatted_date} - {account_number}.pdf"
    new_path = destination_folder / new_name

    # Skip if already exists
    if new_path.exists():
        # Check if identical
        if utils.files_are_identical(pdf_file, new_path):
            logger.debug(f"Skipping duplicate: {pdf_file.name}")
            return None
        logger.debug(f"Skipping (file exists): {new_name}")
        return None

    # Move file
    if not dry_run:
        try:
            shutil.move(str(pdf_file), str(new_path))
            logger.info(f"Moved: {pdf_file.name} -> {new_path.relative_to(config.TAX_BASE_FOLDER)}")
        except Exception as e:
            logger.error(f"Failed to move {pdf_file.name}: {e}")
            return None
    else:
        logger.info(f"Would move: {pdf_file.name} -> {new_path.relative_to(config.TAX_BASE_FOLDER)}")

    return {
        'file': pdf_file.name,
        'from_location': 'Downloads',
        'to_year': year,
        'account': doc_config['name'],
        'new_name': new_name,
        'type': 'bank_statement',
        'dry_run': dry_run,
    }


def process_general_document(pdf_file: Path, text: str, dry_run: bool = False) -> Optional[dict]:
    """Process a general (non-bank) document."""
    category_id, confidence = categorize_document(pdf_file.name, text)

    # Accept 75%+ confidence (allows filename-only matches for scanned PDFs)
    if not category_id or confidence < 75:
        return None

    cat_config = DOCUMENT_CATEGORIES[category_id]

    # Extract year from document
    date_matches = re.findall(r'\b(\d{1,2}/\d{1,2}/\d{4})\b', text)
    if date_matches:
        try:
            date_obj = datetime.strptime(date_matches[0], "%m/%d/%Y")
            doc_year = date_obj.year
        except ValueError:
            doc_year = datetime.now().year
    else:
        year_match = re.search(r'\b(20\d{2})\b', pdf_file.name)
        doc_year = int(year_match.group(1)) if year_match else datetime.now().year

    # Create destination
    dest_folder = config.TAX_BASE_FOLDER / f"{doc_year} Tax Year" / cat_config['folder']
    dest_folder.mkdir(parents=True, exist_ok=True)

    dest_path = dest_folder / pdf_file.name

    # Handle duplicates
    if dest_path.exists():
        dest_path = utils.get_unique_path(dest_path)

    # Move file
    if not dry_run:
        try:
            shutil.move(str(pdf_file), str(dest_path))
            logger.info(f"Categorized: {pdf_file.name} -> {cat_config['folder']}")
        except Exception as e:
            logger.error(f"Failed to move {pdf_file.name}: {e}")
            return None
    else:
        logger.info(f"Would categorize: {pdf_file.name} -> {cat_config['folder']}")

    return {
        'file': pdf_file.name,
        'from_location': 'Downloads',
        'to_year': doc_year,
        'category': cat_config['folder'],
        'confidence': confidence,
        'new_name': dest_path.name,
        'type': 'categorized',
        'dry_run': dry_run,
    }


def audit_tax_folders(
    dry_run: bool = False,
    auto_yes: bool = False,
) -> Tuple[List[dict], List[dict], List[str]]:
    """
    Audit existing tax folders for misplaced files.

    Returns:
        Tuple of (moved_files, categorized_files, uncategorized_files)
    """
    moved_files = []
    categorized_files = []
    uncategorized_files = []

    logger.info("Auditing tax folders for misplaced files...")

    for pdf_file in config.TAX_BASE_FOLDER.rglob("*.pdf"):
        text = extract_text_from_pdf(pdf_file)
        if not text or text == "NO_TEXT" or text.startswith("ERROR:"):
            continue

        doc_type, doc_config = detect_document_type(pdf_file.name, text)

        if doc_type:
            date_str, _ = extract_statement_date(text, pdf_file.name, doc_config)
            if not date_str:
                continue

            year = extract_year_from_date(date_str)
            if not year:
                continue

            # Check if in correct location
            account_number = doc_config.get('account_number')
            if account_number == 'extracted':
                if doc_type == 'FIDELITY_1099':
                    account_number = extract_fidelity_account(text)
                elif doc_type == 'VANGUARD_TAX_FORMS':
                    account_number = extract_vanguard_account(text)

            correct_folder = get_destination_folder(doc_config, year, account_number)
            formatted_date = format_date_for_filename(date_str)
            if not formatted_date:
                continue

            correct_name = f"{formatted_date} - {account_number}.pdf"
            correct_path = correct_folder / correct_name

            if pdf_file.resolve() == correct_path.resolve():
                continue

            if pdf_file.parent.resolve() == correct_folder.resolve():
                continue

            if correct_path.exists():
                if utils.files_are_identical(pdf_file, correct_path):
                    continue
                continue

            # Move misplaced file
            if not dry_run:
                try:
                    shutil.move(str(pdf_file), str(correct_path))
                    logger.info(f"Fixed: {pdf_file.name} -> {correct_path.relative_to(config.TAX_BASE_FOLDER)}")
                except Exception:
                    continue
            else:
                logger.info(f"Would fix: {pdf_file.name} -> {correct_path.relative_to(config.TAX_BASE_FOLDER)}")

            moved_files.append({
                'file': pdf_file.name,
                'from_location': str(pdf_file.relative_to(config.TAX_BASE_FOLDER).parent),
                'to_year': year,
                'account': doc_config['name'],
                'new_name': correct_name,
                'type': 'bank_statement',
                'dry_run': dry_run,
            })

    return moved_files, categorized_files, uncategorized_files


def print_summary(
    moved_files: List[dict],
    categorized_files: List[dict],
    uncategorized_files: List[str],
    dry_run: bool,
) -> None:
    """Print summary of processing results."""
    print()
    print("=" * 60)
    print("SUMMARY" + (" (DRY RUN)" if dry_run else ""))
    print("=" * 60)

    if moved_files:
        print(f"\nBank Statements/Tax Forms: {len(moved_files)}")
        for f in moved_files[:10]:
            print(f"  - {f['file']} -> {f['to_year']} / {f['account']}")
        if len(moved_files) > 10:
            print(f"  ... and {len(moved_files) - 10} more")

    if categorized_files:
        print(f"\nCategorized Documents: {len(categorized_files)}")
        for f in categorized_files[:10]:
            print(f"  - {f['file']} -> {f['to_year']} / {f['category']}")
        if len(categorized_files) > 10:
            print(f"  ... and {len(categorized_files) - 10} more")

    if uncategorized_files:
        print(f"\nUncategorized (manual review): {len(uncategorized_files)}")
        for f in uncategorized_files[:5]:
            print(f"  - {f}")
        if len(uncategorized_files) > 5:
            print(f"  ... and {len(uncategorized_files) - 5} more")

    if not moved_files and not categorized_files:
        print("\nNo files to organize.")

    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PDF Organizer for tax documents")
    parser.add_argument("--dry-run", action="store_true", help="Preview without moving")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm all actions")
    parser.add_argument("--audit", action="store_true", help="Audit existing folders")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    run(dry_run=args.dry_run, auto_yes=args.yes, audit=args.audit, verbose=args.verbose)
