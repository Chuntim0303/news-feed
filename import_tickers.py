#!/usr/bin/env python3
"""
Bulk Import Stock Tickers into Database

Downloads and imports US-listed stock tickers from NASDAQ's public FTP data
into the companies and company_aliases tables.

Usage:
    # Download and import all NASDAQ/NYSE/AMEX listed stocks
    python import_tickers.py --download

    # Import from a local CSV file (ticker,name,exchange format)
    python import_tickers.py --file tickers.csv

    # Seed from existing stock_ticker_data.py (migration helper)
    python import_tickers.py --seed

    # Show current DB stats
    python import_tickers.py --stats
"""

import sys
import os
import csv
import re
import argparse
import io
from typing import List, Dict, Tuple
from urllib.request import urlopen, Request

import pymysql
from dotenv import load_dotenv


def load_env():
    """Load environment variables from .env file."""
    load_dotenv()
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'news_feed'),
        'port': int(os.getenv('DB_PORT', 3306))
    }


def get_db_connection():
    """Create a database connection."""
    db_config = load_env()
    return pymysql.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password'],
        database=db_config['database'],
        port=db_config['port'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def _is_common_stock(security_name: str, etf_flag: str) -> bool:
    """
    Check if a security is a common stock (not an ETF, warrant, trust, etc.).

    Args:
        security_name: Full security name from NASDAQ data
        etf_flag: 'Y' if ETF, 'N' otherwise

    Returns:
        True if this looks like a regular company common stock
    """
    if etf_flag == 'Y':
        return False

    name_lower = security_name.lower()

    # Exclude non-company security types
    exclude_patterns = [
        'warrant',
        'warrants',
        ' etf',
        ' etn',
        ' fund',
        ' trust',
        ' notes ',
        ' note ',
        'preferred',
        ' pfd',
        ' right',
        ' rights',
        ' unit',
        ' units',
        'depositary receipt',
        'acquisition corp',
        'blank check',
        ' lp',
        ' l.p.',
        'limited partnership',
        'royalty trust',
        'closed-end',
        'closed end',
        'municipal',
        'bond',
        'income fund',
        'debt',
        'debenture',
        'convertible',
        'fixed rate',
        'floating rate',
        'perpetual',
        'senior notes',
        'subordinated',
    ]

    for pattern in exclude_patterns:
        if pattern in name_lower:
            return False

    return True


def _clean_company_name(security_name: str) -> str:
    """
    Clean up a security name into a usable company name for matching.

    Args:
        security_name: Raw security name from NASDAQ data

    Returns:
        Cleaned company name (lowercase)
    """
    # Take the part before " - " (e.g., "Apple Inc. - Common Stock" -> "Apple Inc.")
    name = security_name.split(' - ')[0].strip()

    # Remove class designations first (before suffix stripping)
    name = re.sub(r'\s+Class\s+[A-Z]\b', '', name, flags=re.IGNORECASE)

    # Remove common corporate suffixes (order matters - longer first)
    suffixes = [
        ' Incorporated', ' incorporated',
        ' Corporation', ' corporation',
        ' Common Stock', ' common stock',
        ' Ordinary Shares', ' ordinary shares',
        ' American Depositary Shares',
        ' Holdings', ' holdings',
        ' Group', ' group',
        ' Inc.', ' inc.', ' Inc', ' inc',
        ' Corp.', ' corp.', ' Corp', ' corp',
        ' Ltd.', ' ltd.', ' Ltd', ' ltd',
        ' Limited', ' limited',
        ' PLC', ' plc', ' Plc',
        ' Co.', ' co.', ' Co', ' co',
        ' Company', ' company',
        ' S.A.', ' s.a.',
        ' N.V.', ' n.v.',
        ' SE', ' AG',
    ]

    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()

    # Clean up trailing punctuation and whitespace
    name = name.strip(' ,.')

    # Collapse multiple spaces
    name = ' '.join(name.split())

    return name.lower()


def download_nasdaq_tickers() -> List[Dict]:
    """
    Download ticker data from NASDAQ's public traded list.
    Filters to only include common stocks (no ETFs, warrants, trusts, etc.).

    Returns:
        List of dicts with keys: name, ticker, exchange
    """
    url = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
    print(f"Downloading from {url}...")

    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urlopen(req, timeout=30)
    content = response.read().decode('utf-8')

    tickers = []
    skipped = {'etf': 0, 'non_stock': 0, 'bad_symbol': 0, 'test': 0, 'short_name': 0}
    lines = content.strip().split('\n')

    # Skip header and footer
    for line in lines[1:]:
        if line.startswith('File Creation Time'):
            continue

        fields = line.split('|')
        if len(fields) < 8:
            continue

        # Fields: Nasdaq Traded|Symbol|Security Name|Listing Exchange|...
        symbol = fields[1].strip()
        security_name = fields[2].strip()
        listing_exchange = fields[3].strip()
        etf = fields[5].strip() if len(fields) > 5 else 'N'
        test_issue = fields[7].strip() if len(fields) > 7 else 'N'

        # Skip test issues
        if test_issue == 'Y':
            skipped['test'] += 1
            continue

        # Skip blank symbols and symbols with special chars (preferred shares, etc.)
        if not symbol or len(symbol) > 10:
            skipped['bad_symbol'] += 1
            continue
        if any(c in symbol for c in ['$', '.', ' ']):
            skipped['bad_symbol'] += 1
            continue

        # Filter to common stocks only
        if not _is_common_stock(security_name, etf):
            if etf == 'Y':
                skipped['etf'] += 1
            else:
                skipped['non_stock'] += 1
            continue

        # Map exchange codes
        exchange_map = {
            'Q': 'NASDAQ',
            'N': 'NYSE',
            'A': 'AMEX',
            'P': 'NYSE ARCA',
            'Z': 'BATS',
            'V': 'IEXG',
        }
        exchange = exchange_map.get(listing_exchange, listing_exchange)

        # Clean up the company name
        clean_name = _clean_company_name(security_name)

        # Skip entries with very short or empty names after cleanup
        if not clean_name or len(clean_name) < 2:
            skipped['short_name'] += 1
            continue

        tickers.append({
            'name': clean_name,
            'ticker': symbol,
            'exchange': exchange,
            'full_name': security_name,
        })

    print(f"Downloaded {len(tickers)} common stocks")
    print(f"Skipped: {skipped['etf']} ETFs, {skipped['non_stock']} non-stocks "
          f"(warrants/trusts/preferred/etc.), {skipped['bad_symbol']} bad symbols, "
          f"{skipped['test']} test issues, {skipped['short_name']} empty names")
    return tickers


def import_from_csv(filepath: str) -> List[Dict]:
    """
    Import tickers from a CSV file.
    Expected format: ticker,name,exchange (or ticker,name)

    Returns:
        List of dicts with keys: name, ticker, exchange
    """
    tickers = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)

        for row in reader:
            if len(row) < 2:
                continue
            ticker = row[0].strip()
            name = row[1].strip()
            exchange = row[2].strip() if len(row) > 2 else ''

            if ticker and name:
                tickers.append({
                    'name': name.lower(),
                    'ticker': ticker,
                    'exchange': exchange,
                    'full_name': name,
                })

    print(f"Read {len(tickers)} tickers from {filepath}")
    return tickers


def seed_from_hardcoded() -> List[Dict]:
    """
    Seed from the existing stock_ticker_data.py hardcoded data.

    Returns:
        List of dicts with keys: name, ticker, exchange, full_name, aliases
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from services.stock_ticker_data import COMPANY_TICKER_MAP

    tickers = []
    for name, data in COMPANY_TICKER_MAP.items():
        tickers.append({
            'name': name.lower(),
            'ticker': data['ticker'],
            'exchange': data['exchange'],
            'full_name': data['full_name'],
            'aliases': data.get('aliases', []),
        })

    print(f"Loaded {len(tickers)} companies from stock_ticker_data.py")
    return tickers


def bulk_insert(tickers: List[Dict], include_aliases: bool = True):
    """
    Insert tickers into the companies table, skipping duplicates.

    Args:
        tickers: List of ticker dicts
        include_aliases: Whether to also insert aliases
    """
    connection = get_db_connection()
    inserted = 0
    skipped = 0
    alias_count = 0

    try:
        with connection.cursor() as cursor:
            for t in tickers:
                try:
                    cursor.execute(
                        """INSERT INTO companies (name, ticker, exchange, full_name)
                           VALUES (%s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE
                               full_name = VALUES(full_name),
                               exchange = VALUES(exchange)""",
                        (t['name'], t['ticker'], t['exchange'], t['full_name'])
                    )
                    if cursor.rowcount > 0:
                        inserted += 1
                    else:
                        skipped += 1

                    # Insert aliases if provided
                    if include_aliases and t.get('aliases'):
                        company_id = cursor.lastrowid
                        if not company_id:
                            cursor.execute(
                                "SELECT id FROM companies WHERE name = %s",
                                (t['name'],)
                            )
                            row = cursor.fetchone()
                            if row:
                                company_id = row['id']

                        if company_id:
                            for alias in t['aliases']:
                                try:
                                    cursor.execute(
                                        """INSERT INTO company_aliases (company_id, alias)
                                           VALUES (%s, %s)
                                           ON DUPLICATE KEY UPDATE alias = VALUES(alias)""",
                                        (company_id, alias.lower())
                                    )
                                    alias_count += 1
                                except pymysql.err.IntegrityError:
                                    pass

                except pymysql.err.IntegrityError as e:
                    skipped += 1

            connection.commit()

        print(f"\nResults:")
        print(f"  Inserted/Updated: {inserted}")
        print(f"  Skipped (duplicate): {skipped}")
        if include_aliases:
            print(f"  Aliases added: {alias_count}")

    except Exception as e:
        print(f"Error during import: {e}")
        import traceback
        traceback.print_exc()
    finally:
        connection.close()


def show_stats():
    """Show current database statistics."""
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as count FROM companies")
            companies = cursor.fetchone()['count']

            cursor.execute("SELECT COUNT(*) as count FROM company_aliases")
            aliases = cursor.fetchone()['count']

            cursor.execute(
                "SELECT exchange, COUNT(*) as count FROM companies "
                "GROUP BY exchange ORDER BY count DESC"
            )
            by_exchange = cursor.fetchall()

            print(f"\nDatabase Statistics:")
            print(f"  Total companies: {companies}")
            print(f"  Total aliases: {aliases}")
            print(f"\n  By exchange:")
            for row in by_exchange:
                print(f"    {row['exchange'] or 'Unknown'}: {row['count']}")

    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description='Import stock tickers into the database'
    )
    parser.add_argument(
        '--download',
        action='store_true',
        help='Download and import all NASDAQ-traded tickers'
    )
    parser.add_argument(
        '--file',
        type=str,
        help='Import from a CSV file (ticker,name,exchange)'
    )
    parser.add_argument(
        '--seed',
        action='store_true',
        help='Seed from existing stock_ticker_data.py'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show current database statistics'
    )

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.seed:
        tickers = seed_from_hardcoded()
        bulk_insert(tickers, include_aliases=True)
        show_stats()
    elif args.download:
        tickers = download_nasdaq_tickers()
        bulk_insert(tickers, include_aliases=False)
        show_stats()
    elif args.file:
        tickers = import_from_csv(args.file)
        bulk_insert(tickers, include_aliases=False)
        show_stats()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
