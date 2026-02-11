#!/usr/bin/env python3
"""
News Impact Analysis Script

Analyzes how news articles affect stock prices and trading volume.
Fetches price data for article tickers and generates impact reports.

Usage:
    # Fetch prices and build snapshots for all articles with tickers
    python analyze_news_impact.py --fetch

    # Show impact report for recent articles
    python analyze_news_impact.py --report

    # Analyze a specific ticker
    python analyze_news_impact.py --ticker GOOGL

    # Fetch prices for a specific ticker (useful for testing)
    python analyze_news_impact.py --fetch-ticker GOOGL --days 30

    # Show volume analysis (compare news day volume vs average)
    python analyze_news_impact.py --volume
"""

import sys
import os
import argparse
from datetime import datetime, timedelta

import pymysql
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from services.stock_price_service import StockPriceService


def get_db_connection():
    load_dotenv()
    return pymysql.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'news_feed'),
        port=int(os.getenv('DB_PORT', 3306)),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def fetch_all_article_prices(days: int = 5):
    """Fetch stock prices for all articles that have tickers."""
    service = StockPriceService()

    print("=" * 80)
    print("FETCHING STOCK PRICES FOR ARTICLES")
    print("=" * 80)

    service.fetch_prices_for_articles(limit=200, days_around=days)

    print("\nDone.")
    print("=" * 80)


def fetch_single_ticker(ticker: str, date: str = None, days_around: int = 2):
    """Fetch and store prices for a single ticker around a date."""
    service = StockPriceService()

    if not date:
        date = datetime.now().strftime('%Y-%m-%d')

    print(f"Fetching prices for {ticker} around {date} (+/- {days_around} days)...")
    count = service.fetch_and_store_prices(ticker, date=date, days_around=days_around)
    print(f"Stored {count} price records for {ticker}")


def show_impact_report(limit: int = 30):
    """Show a report of news articles and their stock price impact."""
    connection = get_db_connection()

    print("=" * 80)
    print("NEWS IMPACT REPORT")
    print("=" * 80)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                       ri.id,
                       ri.title,
                       ri.published_at,
                       ass.ticker,
                       ass.price_at_publication,
                       ass.price_current AS price_next_day,
                       ass.price_change_since_article AS change_pct
                   FROM article_stock_snapshots ass
                   JOIN rss_items ri ON ass.article_id = ri.id
                   WHERE ass.price_at_publication IS NOT NULL
                     AND ass.price_current IS NOT NULL
                   ORDER BY ABS(ass.price_change_since_article) DESC
                   LIMIT %s""",
                (limit,)
            )
            rows = cursor.fetchall()

        if not rows:
            print("\nNo article-stock snapshots found.")
            print("Run: python analyze_news_impact.py --fetch")
            return

        print(f"\nTop {len(rows)} articles by price impact (sorted by |change %|):\n")
        print(f"{'Ticker':<8} {'Change %':>10} {'Pub Price':>12} {'Next Day':>12} {'Published':<12} Title")
        print("-" * 120)

        for row in rows:
            change = float(row['change_pct']) if row['change_pct'] else 0
            arrow = "▲" if change > 0 else "▼" if change < 0 else "─"
            title = row['title'][:55] if row['title'] else ''
            pub_date = row['published_at'].strftime('%Y-%m-%d') if row['published_at'] else 'N/A'

            print(f"{row['ticker']:<8} {arrow} {change:>+8.2f}% "
                  f"${float(row['price_at_publication']):>10.2f} "
                  f"${float(row['price_next_day']):>10.2f} "
                  f"{pub_date:<12} {title}")

        # Summary stats
        changes = [float(r['change_pct']) for r in rows if r['change_pct'] is not None]
        if changes:
            positive = sum(1 for c in changes if c > 0)
            negative = sum(1 for c in changes if c < 0)
            avg_change = sum(changes) / len(changes)
            max_gain = max(changes)
            max_loss = min(changes)

            print("\n" + "-" * 120)
            print(f"\nSummary ({len(changes)} article-ticker pairs):")
            print(f"  Positive moves: {positive} ({positive/len(changes)*100:.0f}%)")
            print(f"  Negative moves: {negative} ({negative/len(changes)*100:.0f}%)")
            print(f"  Avg change:     {avg_change:+.2f}%")
            print(f"  Max gain:       {max_gain:+.2f}%")
            print(f"  Max loss:       {max_loss:+.2f}%")

    finally:
        connection.close()

    print("=" * 80)


def show_ticker_analysis(ticker: str):
    """Show detailed analysis for a specific ticker."""
    connection = get_db_connection()

    print("=" * 80)
    print(f"TICKER ANALYSIS: {ticker}")
    print("=" * 80)

    try:
        with connection.cursor() as cursor:
            # Get all articles mentioning this ticker
            cursor.execute(
                """SELECT
                       ri.id, ri.title, ri.published_at,
                       ass.price_at_publication,
                       ass.price_current AS price_next_day,
                       ass.price_change_since_article AS change_pct
                   FROM article_stock_snapshots ass
                   JOIN rss_items ri ON ass.article_id = ri.id
                   WHERE ass.ticker = %s
                   ORDER BY ri.published_at DESC""",
                (ticker,)
            )
            articles = cursor.fetchall()

            # Get recent price history
            cursor.execute(
                """SELECT price_date, open_price, close_price, high_price,
                          low_price, volume, change_percent
                   FROM stock_prices
                   WHERE ticker = %s
                   ORDER BY price_date DESC
                   LIMIT 20""",
                (ticker,)
            )
            prices = cursor.fetchall()

        if not articles and not prices:
            print(f"\nNo data found for {ticker}.")
            print(f"Run: python analyze_news_impact.py --fetch-ticker {ticker}")
            return

        # Price history
        if prices:
            print(f"\nRecent Price History ({len(prices)} days):\n")
            print(f"{'Date':<12} {'Open':>10} {'Close':>10} {'High':>10} {'Low':>10} {'Volume':>14} {'Change':>10}")
            print("-" * 80)

            for p in reversed(prices):
                change = float(p['change_percent']) if p['change_percent'] else 0
                vol = int(p['volume']) if p['volume'] else 0
                print(f"{p['price_date']}  "
                      f"${float(p['open_price']):>9.2f} "
                      f"${float(p['close_price']):>9.2f} "
                      f"${float(p['high_price']):>9.2f} "
                      f"${float(p['low_price']):>9.2f} "
                      f"{vol:>14,} "
                      f"{change:>+9.2f}%")

        # Articles mentioning this ticker
        if articles:
            print(f"\nArticles Mentioning {ticker} ({len(articles)}):\n")
            for a in articles:
                change = float(a['change_pct']) if a['change_pct'] else 0
                arrow = "▲" if change > 0 else "▼" if change < 0 else "─"
                pub_date = a['published_at'].strftime('%Y-%m-%d %H:%M') if a['published_at'] else 'N/A'
                pub_price = f"${float(a['price_at_publication']):.2f}" if a['price_at_publication'] else 'N/A'
                next_price = f"${float(a['price_next_day']):.2f}" if a['price_next_day'] else 'N/A'

                print(f"  [{pub_date}] {a['title'][:70]}")
                print(f"    Price: {pub_price} → {next_price}  {arrow} {change:+.2f}%")
                print()

    finally:
        connection.close()

    print("=" * 80)


def show_volume_analysis(limit: int = 20):
    """
    Compare trading volume on news days vs. average volume.
    High volume on news day suggests the news had market impact.
    """
    connection = get_db_connection()

    print("=" * 80)
    print("VOLUME ANALYSIS: News Day vs Average")
    print("=" * 80)

    try:
        with connection.cursor() as cursor:
            # For each article-ticker pair, compare news day volume to 20-day average
            cursor.execute(
                """SELECT
                       ass.ticker,
                       ri.title,
                       ri.published_at,
                       sp_news.volume AS news_day_volume,
                       sp_news.price_date AS news_price_date,
                       sp_news.change_percent AS news_day_change,
                       (SELECT AVG(sp2.volume)
                        FROM stock_prices sp2
                        WHERE sp2.ticker = ass.ticker
                          AND sp2.price_date < sp_news.price_date
                          AND sp2.price_date >= DATE_SUB(sp_news.price_date, INTERVAL 30 DAY)
                       ) AS avg_volume_30d
                   FROM article_stock_snapshots ass
                   JOIN rss_items ri ON ass.article_id = ri.id
                   JOIN stock_prices sp_news ON sp_news.ticker = ass.ticker
                       AND sp_news.price_date = (
                           SELECT MIN(sp3.price_date)
                           FROM stock_prices sp3
                           WHERE sp3.ticker = ass.ticker
                             AND sp3.price_date >= DATE(ri.published_at)
                       )
                   WHERE sp_news.volume IS NOT NULL
                     AND sp_news.volume > 0
                   ORDER BY
                       CASE WHEN (SELECT AVG(sp2.volume)
                                  FROM stock_prices sp2
                                  WHERE sp2.ticker = ass.ticker
                                    AND sp2.price_date < sp_news.price_date
                                    AND sp2.price_date >= DATE_SUB(sp_news.price_date, INTERVAL 30 DAY)
                                 ) > 0
                            THEN sp_news.volume / (SELECT AVG(sp2.volume)
                                                   FROM stock_prices sp2
                                                   WHERE sp2.ticker = ass.ticker
                                                     AND sp2.price_date < sp_news.price_date
                                                     AND sp2.price_date >= DATE_SUB(sp_news.price_date, INTERVAL 30 DAY))
                            ELSE 0
                       END DESC
                   LIMIT %s""",
                (limit,)
            )
            rows = cursor.fetchall()

        if not rows:
            print("\nNo volume data available.")
            print("Run: python analyze_news_impact.py --fetch")
            return

        print(f"\n{'Ticker':<8} {'News Vol':>14} {'30d Avg Vol':>14} {'Vol Ratio':>10} {'Price Chg':>10} {'Date':<12} Title")
        print("-" * 130)

        for row in rows:
            news_vol = int(row['news_day_volume']) if row['news_day_volume'] else 0
            avg_vol = int(row['avg_volume_30d']) if row['avg_volume_30d'] else 0
            vol_ratio = (news_vol / avg_vol) if avg_vol > 0 else 0
            change = float(row['news_day_change']) if row['news_day_change'] else 0
            title = row['title'][:50] if row['title'] else ''
            date_str = str(row['news_price_date'])

            # Flag unusual volume
            flag = " !!!" if vol_ratio > 2.0 else " !" if vol_ratio > 1.5 else ""

            print(f"{row['ticker']:<8} "
                  f"{news_vol:>14,} "
                  f"{avg_vol:>14,} "
                  f"{vol_ratio:>9.1f}x "
                  f"{change:>+9.2f}% "
                  f"{date_str:<12} "
                  f"{title}{flag}")

        print("\n  !!! = Volume > 2x average (strong signal)")
        print("  !   = Volume > 1.5x average (moderate signal)")

    finally:
        connection.close()

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Analyze news impact on stock prices and volume'
    )

    parser.add_argument(
        '--fetch',
        action='store_true',
        help='Fetch stock prices for all articles with tickers and build snapshots'
    )
    parser.add_argument(
        '--fetch-ticker',
        type=str,
        help='Fetch prices for a specific ticker'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Center date for --fetch-ticker (YYYY-MM-DD, default: today)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=2,
        help='Days around each article/date to fetch (default: 2)'
    )
    parser.add_argument(
        '--report',
        action='store_true',
        help='Show news impact report (sorted by price change)'
    )
    parser.add_argument(
        '--ticker',
        type=str,
        help='Show detailed analysis for a specific ticker'
    )
    parser.add_argument(
        '--volume',
        action='store_true',
        help='Show volume analysis (news day vs average)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=30,
        help='Limit number of results (default: 30)'
    )

    args = parser.parse_args()

    if args.fetch:
        fetch_all_article_prices(days=args.days)
    elif args.fetch_ticker:
        fetch_single_ticker(args.fetch_ticker, date=args.date, days_around=args.days)
    elif args.report:
        show_impact_report(limit=args.limit)
    elif args.ticker:
        show_ticker_analysis(args.ticker)
    elif args.volume:
        show_volume_analysis(limit=args.limit)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
