#!/usr/bin/env python3
"""
Local Ticker Extraction Script

This script demonstrates company name and ticker extraction from RSS feed items.
Can be run locally to test the extraction or process existing database records.

Usage:
    # Test with sample titles
    python extract_tickers_local.py --test

    # Process database records
    python extract_tickers_local.py --process --limit 10

    # Extract from a specific title
    python extract_tickers_local.py --text "Apple and Microsoft announce partnership"

    # Update database with extracted tickers
    python extract_tickers_local.py --update --limit 100
"""

import sys
import os
import argparse
from typing import List, Dict
import pymysql
from dotenv import load_dotenv

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.company_extractor import CompanyExtractor


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


def test_extraction():
    """Test extraction with sample titles."""
    print("=" * 80)
    print("TESTING COMPANY AND TICKER EXTRACTION")
    print("=" * 80)

    sample_titles = [
        "Pfizer and BioNTech announce new vaccine partnership",
        "Moderna reports record revenue, stock surges",
        "AstraZeneca's new cancer drug approved by FDA",
        "Johnson & Johnson faces lawsuit over product safety",
        "Eli Lilly and Novo Nordisk compete in diabetes market",
        "Apple, Microsoft, and Google expand healthcare initiatives",
        "Palantir Technologies wins government contract",
        "Bristol Myers Squibb acquires biotech startup for $2B",
        "Regeneron and Roche collaborate on antibody therapy",
        "Amgen launches new drug to treat arthritis",
    ]

    extractor = CompanyExtractor()

    for i, title in enumerate(sample_titles, 1):
        print(f"\n{i}. Title: {title}")
        print("-" * 80)

        result = extractor.extract_companies_and_tickers(title)

        print(f"   Detected Companies: {', '.join(result['companies']) if result['companies'] else 'None'}")
        print(f"   Tickers Found: {', '.join(result['tickers']) if result['tickers'] else 'None'}")

        if result['matches']:
            print(f"   Matched Details:")
            for match in result['matches']:
                matched_via = match.get('matched_via', 'exact')
                confidence = match.get('confidence', 'high')
                print(f"      - {match['company']} → {match['ticker']} ({match['exchange']}) "
                      f"[{matched_via}, {confidence}]")

        if result['unmatched']:
            print(f"   Unmatched: {', '.join(result['unmatched'])}")

    print("\n" + "=" * 80)


def extract_from_text(text: str):
    """Extract companies and tickers from provided text."""
    print("=" * 80)
    print("EXTRACTING FROM TEXT")
    print("=" * 80)
    print(f"Input: {text}\n")

    extractor = CompanyExtractor()
    result = extractor.extract_companies_and_tickers(text)

    print(f"Companies Detected: {result['companies']}")
    print(f"Tickers: {result['tickers']}")
    print(f"\nMatches:")
    for match in result['matches']:
        print(f"  {match['company']} → {match['ticker']} ({match['full_name']})")

    if result['unmatched']:
        print(f"\nUnmatched Organizations: {result['unmatched']}")

    print("=" * 80)


def process_database_records(limit: int = 10, update: bool = False):
    """
    Process existing database records to extract tickers.

    Args:
        limit: Maximum number of records to process
        update: If True, update database with extracted values
    """
    print("=" * 80)
    print(f"PROCESSING DATABASE RECORDS (limit={limit}, update={update})")
    print("=" * 80)

    try:
        connection = get_db_connection()
        extractor = CompanyExtractor()

        with connection.cursor() as cursor:
            # Fetch records without tickers
            query = """
                SELECT id, title, summary, stock_tickers, company_names
                FROM rss_items
                WHERE (stock_tickers IS NULL OR stock_tickers = '')
                ORDER BY published_at DESC
                LIMIT %s
            """
            cursor.execute(query, (limit,))
            records = cursor.fetchall()

            print(f"\nFound {len(records)} records to process\n")

            processed = 0
            updated = 0

            for record in records:
                processed += 1
                print(f"\n{processed}. [{record['id']}] {record['title'][:80]}...")
                print("-" * 80)

                # Combine title and summary for better context
                text = record['title']
                if record.get('summary'):
                    text = f"{text}. {record['summary']}"

                result = extractor.extract_companies_and_tickers(text)

                if result['tickers']:
                    stock_tickers, company_names = extractor.format_for_database(result)

                    print(f"   Companies: {company_names}")
                    print(f"   Tickers: {stock_tickers}")

                    if update:
                        # Update the database
                        update_query = """
                            UPDATE rss_items
                            SET stock_tickers = %s, company_names = %s
                            WHERE id = %s
                        """
                        cursor.execute(update_query, (stock_tickers, company_names, record['id']))
                        updated += 1
                        print(f"   ✓ Database updated")
                else:
                    print(f"   No tickers found")

            if update:
                connection.commit()
                print(f"\n✓ Committed {updated} updates to database")

            print(f"\nProcessed: {processed} records")
            if update:
                print(f"Updated: {updated} records")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'connection' in locals():
            connection.close()

    print("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Extract company names and stock tickers from text using spaCy NER'
    )

    parser.add_argument(
        '--test',
        action='store_true',
        help='Run test with sample titles'
    )

    parser.add_argument(
        '--text',
        type=str,
        help='Extract from specific text'
    )

    parser.add_argument(
        '--process',
        action='store_true',
        help='Process database records'
    )

    parser.add_argument(
        '--update',
        action='store_true',
        help='Update database with extracted tickers (use with --process)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=10,
        help='Limit number of database records to process (default: 10)'
    )

    args = parser.parse_args()

    # Check if spaCy model is available
    try:
        import spacy
        spacy.load("en_core_web_sm")
    except OSError:
        print("ERROR: spaCy model 'en_core_web_sm' not found!")
        print("Install it with: python -m spacy download en_core_web_sm")
        sys.exit(1)

    if args.test:
        test_extraction()
    elif args.text:
        extract_from_text(args.text)
    elif args.process:
        process_database_records(limit=args.limit, update=args.update)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
