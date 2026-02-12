"""
Telegram Bot Command Handlers

All command logic for the Telegram bot interface.
Separated from lambda_function.py for clarity.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import pymysql

logger = logging.getLogger(__name__)


def get_connection(db_config: Dict[str, str]):
    return pymysql.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password'],
        database=db_config['database'],
        port=int(db_config.get('port', 3306)),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


# ===========================================================================
# Keyword Management
# ===========================================================================

def handle_add(db_config: Dict, keyword: str, user_name: str) -> str:
    """
    /add pfizer       → adds with default event_score=5
    /add pfizer 8     → adds with event_score=8
    """
    parts = keyword.strip().split()
    if not parts:
        return (
            "⚠️ Usage: <code>/add keyword [score]</code>\n\n"
            "Examples:\n"
            "<code>/add pfizer</code> — default score 5\n"
            "<code>/add pfizer 8</code> — score 8 (1-10)"
        )

    # Check if last part is a number (event_score)
    event_score = 5
    if len(parts) >= 2 and parts[-1].isdigit():
        event_score = max(1, min(10, int(parts[-1])))
        kw = ' '.join(parts[:-1]).lower()
    else:
        kw = ' '.join(parts).lower()

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    "INSERT INTO alert_keywords (keyword, created_by, event_score) VALUES (%s, %s, %s)",
                    (kw, user_name, event_score)
                )
                connection.commit()
                return f"✅ Keyword <b>{kw}</b> added (score={event_score})"
            except pymysql.err.IntegrityError:
                cursor.execute(
                    "UPDATE alert_keywords SET is_active = 1, event_score = %s WHERE keyword = %s AND is_active = 0",
                    (event_score, kw)
                )
                connection.commit()
                if cursor.rowcount > 0:
                    return f"✅ Keyword <b>{kw}</b> reactivated (score={event_score})"
                return f"ℹ️ Keyword <b>{kw}</b> already exists"
    finally:
        connection.close()


def handle_remove(db_config: Dict, keyword: str) -> str:
    keyword = keyword.strip().lower()
    if not keyword:
        return "⚠️ Usage: <code>/remove keyword</code>\n\nExample: <code>/remove pfizer</code>"

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE alert_keywords SET is_active = 0 WHERE keyword = %s AND is_active = 1",
                (keyword,)
            )
            connection.commit()
            if cursor.rowcount > 0:
                return f"✅ Keyword <b>{keyword}</b> removed"
            return f"⚠️ Keyword <b>{keyword}</b> not found"
    finally:
        connection.close()


def handle_score(db_config: Dict, args: str) -> str:
    """/score pfizer 9 → update event_score for keyword"""
    parts = args.strip().split()
    if len(parts) < 2 or not parts[-1].isdigit():
        return (
            "⚠️ Usage: <code>/score keyword N</code> (N = 1-10)\n\n"
            "Example: <code>/score pfizer 9</code>"
        )

    score = max(1, min(10, int(parts[-1])))
    kw = ' '.join(parts[:-1]).lower()

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE alert_keywords SET event_score = %s WHERE keyword = %s AND is_active = 1",
                (score, kw)
            )
            connection.commit()
            if cursor.rowcount > 0:
                return f"✅ Keyword <b>{kw}</b> score updated to <b>{score}</b>"
            return f"⚠️ Keyword <b>{kw}</b> not found"
    finally:
        connection.close()


def handle_list(db_config: Dict) -> str:
    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT keyword, event_score, created_at, created_by "
                "FROM alert_keywords WHERE is_active = 1 ORDER BY event_score DESC, keyword"
            )
            rows = cursor.fetchall()

        if not rows:
            return "📋 No active keywords.\n\nUse <code>/add keyword [score]</code> to add one."

        lines = ["📋 <b>Active Keywords</b>\n"]
        for row in rows:
            score = row.get('event_score', 5)
            bar = '█' * score + '░' * (10 - score)
            by = f" (by {row['created_by']})" if row.get('created_by') else ''
            lines.append(f"• <code>{row['keyword']}</code> — score {score} {bar}{by}")

        lines.append(f"\nTotal: {len(rows)} keywords")
        lines.append("\nUse <code>/score keyword N</code> to change a score.")
        return '\n'.join(lines)
    finally:
        connection.close()


# ===========================================================================
# Query Commands
# ===========================================================================

def handle_latest(db_config: Dict, args: str) -> str:
    """
    /latest           → latest 10 headlines
    /latest AAPL      → latest 10 for ticker AAPL
    /latest bloomberg → latest 10 from bloomberg
    """
    args = args.strip()
    limit = 10

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            if not args:
                cursor.execute(
                    """SELECT ri.title, ri.published_at, ri.stock_tickers, ri.link,
                              f.title AS feed_title
                       FROM rss_items ri
                       JOIN rss_feeds f ON ri.feed_id = f.id
                       ORDER BY ri.published_at DESC
                       LIMIT %s""",
                    (limit,)
                )
            else:
                # Try as ticker first, then as source
                cursor.execute(
                    """SELECT ri.title, ri.published_at, ri.stock_tickers, ri.link,
                              f.title AS feed_title
                       FROM rss_items ri
                       JOIN rss_feeds f ON ri.feed_id = f.id
                       WHERE FIND_IN_SET(%s, ri.stock_tickers) > 0
                          OR f.title LIKE %s
                       ORDER BY ri.published_at DESC
                       LIMIT %s""",
                    (args.upper(), f"%{args}%", limit)
                )

            rows = cursor.fetchall()

        if not rows:
            return f"📰 No articles found" + (f" for <b>{args}</b>" if args else "") + "."

        header = "📰 <b>Latest Headlines</b>"
        if args:
            header += f" — {args}"
        header += "\n"

        lines = [header]
        for row in rows:
            pub = row['published_at'].strftime('%m/%d %H:%M') if row.get('published_at') else '?'
            tickers = f" [{row['stock_tickers']}]" if row.get('stock_tickers') else ''
            title = (row['title'] or '(no title)')[:80]
            source = row.get('feed_title', '')[:15]
            link = row.get('link', '')

            line = f"• <b>{pub}</b> {title}{tickers}"
            if source:
                line += f"\n  <i>{source}</i>"
            if link:
                line += f" — <a href=\"{link}\">link</a>"
            lines.append(line)

        return '\n'.join(lines)
    finally:
        connection.close()


def handle_search(db_config: Dict, query: str) -> str:
    """
    /search ozempic → search articles by keyword in title/summary
    """
    query = query.strip()
    if not query:
        return "⚠️ Usage: <code>/search keyword</code>\n\nExample: <code>/search ozempic</code>"

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            like_query = f"%{query}%"
            cursor.execute(
                """SELECT ri.title, ri.published_at, ri.stock_tickers, ri.link,
                          f.title AS feed_title
                   FROM rss_items ri
                   JOIN rss_feeds f ON ri.feed_id = f.id
                   WHERE ri.title LIKE %s OR ri.summary LIKE %s
                   ORDER BY ri.published_at DESC
                   LIMIT 10""",
                (like_query, like_query)
            )
            rows = cursor.fetchall()

        if not rows:
            return f"🔍 No results for <b>{query}</b>"

        lines = [f"🔍 <b>Search: {query}</b> ({len(rows)} results)\n"]
        for row in rows:
            pub = row['published_at'].strftime('%m/%d %H:%M') if row.get('published_at') else '?'
            tickers = f" [{row['stock_tickers']}]" if row.get('stock_tickers') else ''
            title = (row['title'] or '(no title)')[:80]
            link = row.get('link', '')

            line = f"• <b>{pub}</b> {title}{tickers}"
            if link:
                line += f"\n  <a href=\"{link}\">link</a>"
            lines.append(line)

        return '\n'.join(lines)
    finally:
        connection.close()


def handle_why(db_config: Dict, args: str) -> str:
    """
    /why        → explain the last alert (with score breakdown)
    /why <id>   → explain a specific article alert
    """
    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            if args.strip().isdigit():
                article_id = int(args.strip())
                cursor.execute(
                    """SELECT al.keyword, al.sent_at, al.score_total, al.score_keyword,
                              al.score_cap_mult, al.score_surprise, al.surprise_dir,
                              al.alert_sent, ak.event_score, ak.created_by
                       FROM alert_log al
                       JOIN alert_keywords ak ON al.keyword_id = ak.id
                       WHERE al.rss_item_id = %s
                       ORDER BY al.sent_at DESC""",
                    (article_id,)
                )
            else:
                # Get the most recent alert
                cursor.execute(
                    """SELECT al.rss_item_id, al.keyword, al.sent_at,
                              al.score_total, al.score_keyword, al.score_cap_mult,
                              al.score_surprise, al.surprise_dir, al.alert_sent,
                              ak.event_score, ak.created_by
                       FROM alert_log al
                       JOIN alert_keywords ak ON al.keyword_id = ak.id
                       ORDER BY al.sent_at DESC
                       LIMIT 5"""
                )

            alert_rows = cursor.fetchall()

            if not alert_rows:
                return "ℹ️ No alerts found."

            # Get the article details
            if args.strip().isdigit():
                target_id = int(args.strip())
            else:
                target_id = alert_rows[0]['rss_item_id']

            cursor.execute(
                """SELECT ri.id, ri.title, ri.published_at, ri.stock_tickers,
                          ri.company_names, ri.link, f.title AS feed_title
                   FROM rss_items ri
                   JOIN rss_feeds f ON ri.feed_id = f.id
                   WHERE ri.id = %s""",
                (target_id,)
            )
            article = cursor.fetchone()

            # Get price impact if available
            cursor.execute(
                """SELECT ass.ticker, ass.price_at_publication, ass.price_current,
                          ass.price_change_since_article
                   FROM article_stock_snapshots ass
                   WHERE ass.article_id = %s""",
                (target_id,)
            )
            snapshots = cursor.fetchall()

        if not article:
            return "ℹ️ Article not found."

        lines = [f"🔎 <b>Alert Explanation</b>\n"]
        lines.append(f"<b>{article['title']}</b>")
        if article.get('published_at'):
            lines.append(f"Published: {article['published_at'].strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Source: {article.get('feed_title', '?')}")
        if article.get('link'):
            lines.append(f"<a href=\"{article['link']}\">Read article</a>")

        # Matched keywords with scores
        relevant_rows = [r for r in alert_rows if r.get('rss_item_id', target_id) == target_id]
        if not relevant_rows:
            relevant_rows = alert_rows

        kw_parts = []
        for r in relevant_rows:
            es = r.get('event_score', 5)
            kw_parts.append(f"<b>{r['keyword']}</b> ({es})")
        lines.append(f"\n<b>Matched keywords:</b> {', '.join(kw_parts)}")

        # Score breakdown (from the first alert row for this article)
        row0 = relevant_rows[0]
        score_total = row0.get('score_total')
        if score_total is not None:
            was_sent = row0.get('alert_sent', 1)
            sent_icon = "✅" if was_sent else "🔇"
            lines.append(f"\n<b>Score Breakdown:</b> {sent_icon}")
            lines.append(f"  Keyword sum: {row0.get('score_keyword', '?')}")
            cap_mult = row0.get('score_cap_mult', 1.0)
            if cap_mult and float(cap_mult) != 1.0:
                lines.append(f"  Market cap multiplier: ×{float(cap_mult):.1f}")
            surprise = row0.get('score_surprise', 0)
            if surprise and float(surprise) > 0:
                s_dir = row0.get('surprise_dir', 'none')
                dir_icon = "📈" if s_dir == 'positive' else "📉" if s_dir == 'negative' else "⚡" if s_dir == 'mixed' else ""
                lines.append(f"  Surprise score: +{float(surprise):.0f} {dir_icon} ({s_dir})")
            lines.append(f"  <b>Total: {float(score_total):.1f}</b>")
            if not was_sent:
                lines.append(f"  (Below threshold — alert was silenced)")

        # Tickers
        if article.get('stock_tickers'):
            lines.append(f"\n<b>Tickers:</b> {article['stock_tickers']}")
        if article.get('company_names'):
            lines.append(f"<b>Companies:</b> {article['company_names']}")

        # Price impact
        if snapshots:
            lines.append(f"\n<b>Price Impact:</b>")
            for snap in snapshots:
                change = float(snap['price_change_since_article'] or 0)
                arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                pub_price = float(snap['price_at_publication'] or 0)
                cur_price = float(snap['price_current'] or 0)
                lines.append(
                    f"  {arrow} <b>{snap['ticker']}</b>: "
                    f"${pub_price:.2f} → ${cur_price:.2f} ({change:+.2f}%)"
                )

        return '\n'.join(lines)
    finally:
        connection.close()


def handle_summary(db_config: Dict, args: str) -> str:
    """
    /summary 1d NVO  → daily digest for ticker NVO
    /summary 7d AAPL → weekly digest for AAPL
    /summary         → 1-day summary of all tickers
    """
    parts = args.strip().split()
    days = 1
    ticker_filter = None

    for part in parts:
        if part.lower().endswith('d') and part[:-1].isdigit():
            days = int(part[:-1])
        elif part.upper() == part and len(part) <= 6 and part.isalpha():
            ticker_filter = part.upper()

    since = datetime.now() - timedelta(days=days)

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            # Article count and tickers
            query = """
                SELECT ri.stock_tickers, COUNT(*) AS cnt
                FROM rss_items ri
                WHERE ri.published_at >= %s
                  AND ri.stock_tickers IS NOT NULL AND ri.stock_tickers != ''
            """
            params = [since]
            if ticker_filter:
                query += " AND FIND_IN_SET(%s, ri.stock_tickers) > 0"
                params.append(ticker_filter)
            query += " GROUP BY ri.stock_tickers ORDER BY cnt DESC LIMIT 10"

            cursor.execute(query, params)
            ticker_counts = cursor.fetchall()

            # Price movers
            query = """
                SELECT ass.ticker,
                       ass.price_at_publication, ass.price_current,
                       ass.price_change_since_article AS change_pct,
                       ri.title, ri.published_at
                FROM article_stock_snapshots ass
                JOIN rss_items ri ON ass.article_id = ri.id
                WHERE ri.published_at >= %s
                  AND ass.price_change_since_article IS NOT NULL
            """
            params = [since]
            if ticker_filter:
                query += " AND ass.ticker = %s"
                params.append(ticker_filter)
            query += " ORDER BY ABS(ass.price_change_since_article) DESC LIMIT 5"

            cursor.execute(query, params)
            movers = cursor.fetchall()

            # Total articles
            query = "SELECT COUNT(*) AS total FROM rss_items WHERE published_at >= %s"
            params = [since]
            if ticker_filter:
                query += " AND FIND_IN_SET(%s, stock_tickers) > 0"
                params.append(ticker_filter)
            cursor.execute(query, params)
            total = cursor.fetchone()['total']

        period = f"{days}d"
        header = f"📊 <b>Summary ({period})</b>"
        if ticker_filter:
            header += f" — {ticker_filter}"
        header += f"\nArticles: {total} | Since: {since.strftime('%m/%d %H:%M')}\n"

        lines = [header]

        if movers:
            lines.append("<b>Top Movers:</b>")
            for m in movers:
                change = float(m['change_pct'] or 0)
                arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                title = (m['title'] or '')[:50]
                lines.append(f"  {arrow} <b>{m['ticker']}</b> {change:+.2f}% — {title}")

        if ticker_counts and not ticker_filter:
            lines.append("\n<b>Most Mentioned:</b>")
            for tc in ticker_counts[:5]:
                lines.append(f"  • {tc['stock_tickers']} ({tc['cnt']} articles)")

        if not movers and not ticker_counts:
            lines.append("No data available for this period.")

        return '\n'.join(lines)
    finally:
        connection.close()


def handle_top(db_config: Dict, args: str) -> str:
    """
    /top        → top 5 highest-impact news items today
    /top 7d     → top movers in last 7 days
    """
    days = 1
    if args.strip().endswith('d') and args.strip()[:-1].isdigit():
        days = int(args.strip()[:-1])

    since = datetime.now() - timedelta(days=days)

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                       ass.ticker,
                       ass.price_at_publication,
                       ass.price_current,
                       ass.price_change_since_article AS change_pct,
                       ri.title, ri.published_at, ri.link,
                       sp.volume
                   FROM article_stock_snapshots ass
                   JOIN rss_items ri ON ass.article_id = ri.id
                   LEFT JOIN stock_prices sp ON sp.ticker = ass.ticker
                       AND sp.price_date = (
                           SELECT MIN(sp2.price_date) FROM stock_prices sp2
                           WHERE sp2.ticker = ass.ticker
                             AND sp2.price_date >= DATE(ri.published_at)
                       )
                   WHERE ri.published_at >= %s
                     AND ass.price_change_since_article IS NOT NULL
                   ORDER BY ABS(ass.price_change_since_article) DESC
                   LIMIT 10""",
                (since,)
            )
            rows = cursor.fetchall()

        if not rows:
            return f"📊 No price impact data for the last {days} day(s)."

        period = f"{days}d"
        lines = [f"🏆 <b>Top Movers ({period})</b>\n"]

        for i, row in enumerate(rows, 1):
            change = float(row['change_pct'] or 0)
            arrow = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            pub_price = float(row['price_at_publication'] or 0)
            cur_price = float(row['price_current'] or 0)
            title = (row['title'] or '')[:55]
            vol = f" | Vol: {int(row['volume']):,}" if row.get('volume') else ''
            link = row.get('link', '')

            lines.append(
                f"{i}. {arrow} <b>{row['ticker']}</b> {change:+.2f}% "
                f"(${pub_price:.2f}→${cur_price:.2f}{vol})\n"
                f"   {title}"
            )
            if link:
                lines.append(f"   <a href=\"{link}\">link</a>")

        return '\n'.join(lines)
    finally:
        connection.close()


# ===========================================================================
# Settings Commands
# ===========================================================================

def _get_or_create_settings(cursor, chat_id: str) -> Dict:
    """Get settings for a chat, creating defaults if needed."""
    cursor.execute("SELECT * FROM bot_settings WHERE chat_id = %s", (chat_id,))
    row = cursor.fetchone()
    if row:
        return row
    cursor.execute("INSERT INTO bot_settings (chat_id) VALUES (%s)", (chat_id,))
    cursor.execute("SELECT * FROM bot_settings WHERE chat_id = %s", (chat_id,))
    return cursor.fetchone()


def handle_settings(db_config: Dict, chat_id: str) -> str:
    """/settings → show current preferences"""
    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            settings = _get_or_create_settings(cursor, chat_id)
            connection.commit()

            # Get source settings
            cursor.execute(
                "SELECT source_name, is_enabled FROM bot_source_settings WHERE chat_id = %s ORDER BY source_name",
                (chat_id,)
            )
            sources = cursor.fetchall()

        mode_emoji = "🔔" if settings['alert_mode'] == 'normal' else "🔕"
        morning = "✅" if settings['morning_brief'] else "❌"
        eod = "✅" if settings['eod_recap'] else "❌"
        weekly = "✅" if settings['weekly_report'] else "❌"

        lines = [
            "⚙️ <b>Settings</b>\n",
            f"<b>Alert mode:</b> {mode_emoji} {settings['alert_mode']}",
            f"<b>Alert threshold:</b> {settings['alert_threshold']} (min score to alert)",
            f"\n<b>Digests:</b>",
            f"  {morning} Morning brief (9:00 AM)",
            f"  {eod} End-of-day recap",
            f"  {weekly} Weekly report",
        ]

        if sources:
            lines.append(f"\n<b>Sources:</b>")
            for s in sources:
                icon = "✅" if s['is_enabled'] else "❌"
                lines.append(f"  {icon} {s['source_name']}")
        else:
            lines.append(f"\n<b>Sources:</b> all enabled (default)")

        lines.append(
            "\n<b>Commands:</b>\n"
            "<code>/mode quiet</code> or <code>/mode normal</code>\n"
            "<code>/threshold 3</code>\n"
            "<code>/sources bloomberg off</code>\n"
            "<code>/digest morning off</code>"
        )

        return '\n'.join(lines)
    finally:
        connection.close()


def handle_mode(db_config: Dict, chat_id: str, args: str) -> str:
    """/mode quiet or /mode normal"""
    mode = args.strip().lower()
    if mode not in ('quiet', 'normal'):
        return "⚠️ Usage: <code>/mode quiet</code> or <code>/mode normal</code>"

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            _get_or_create_settings(cursor, chat_id)
            cursor.execute(
                "UPDATE bot_settings SET alert_mode = %s WHERE chat_id = %s",
                (mode, chat_id)
            )
            connection.commit()

        emoji = "🔔" if mode == 'normal' else "🔕"
        desc = "all alerts" if mode == 'normal' else "urgent alerts only"
        return f"{emoji} Alert mode set to <b>{mode}</b> ({desc})"
    finally:
        connection.close()


def handle_threshold(db_config: Dict, chat_id: str, args: str) -> str:
    """/threshold 6 → set minimum score to trigger alert"""
    args = args.strip()
    if not args.isdigit() or int(args) < 1:
        return (
            "⚠️ Usage: <code>/threshold N</code> (N ≥ 1)\n\n"
            "Sets the minimum news score to trigger an alert.\n"
            "Example: <code>/threshold 6</code>"
        )

    threshold = int(args)
    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            _get_or_create_settings(cursor, chat_id)
            cursor.execute(
                "UPDATE bot_settings SET alert_threshold = %s WHERE chat_id = %s",
                (threshold, chat_id)
            )
            connection.commit()

        return f"✅ Alert threshold set to <b>{threshold}</b> (min score to alert)"
    finally:
        connection.close()


def handle_sources(db_config: Dict, chat_id: str, args: str) -> str:
    """/sources bloomberg off  or  /sources fiercebiotech on"""
    parts = args.strip().lower().split()
    if len(parts) < 2 or parts[-1] not in ('on', 'off'):
        return (
            "⚠️ Usage: <code>/sources name on|off</code>\n\n"
            "Examples:\n"
            "<code>/sources bloomberg off</code>\n"
            "<code>/sources fiercebiotech on</code>"
        )

    source_name = ' '.join(parts[:-1])
    is_enabled = 1 if parts[-1] == 'on' else 0

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    """INSERT INTO bot_source_settings (chat_id, source_name, is_enabled)
                       VALUES (%s, %s, %s)""",
                    (chat_id, source_name, is_enabled)
                )
            except pymysql.err.IntegrityError:
                cursor.execute(
                    """UPDATE bot_source_settings SET is_enabled = %s
                       WHERE chat_id = %s AND source_name = %s""",
                    (is_enabled, chat_id, source_name)
                )
            connection.commit()

        icon = "✅" if is_enabled else "❌"
        state = "enabled" if is_enabled else "disabled"
        return f"{icon} Source <b>{source_name}</b> {state}"
    finally:
        connection.close()


def handle_digest(db_config: Dict, chat_id: str, args: str) -> str:
    """/digest morning off  or  /digest eod on  or  /digest weekly off"""
    parts = args.strip().lower().split()
    if len(parts) < 2 or parts[-1] not in ('on', 'off'):
        return (
            "⚠️ Usage: <code>/digest type on|off</code>\n\n"
            "Types: <code>morning</code>, <code>eod</code>, <code>weekly</code>\n"
            "Example: <code>/digest morning off</code>"
        )

    digest_type = parts[0]
    enabled = 1 if parts[-1] == 'on' else 0

    column_map = {
        'morning': 'morning_brief',
        'eod': 'eod_recap',
        'weekly': 'weekly_report',
    }

    if digest_type not in column_map:
        return f"⚠️ Unknown digest type: <b>{digest_type}</b>. Use: morning, eod, weekly"

    column = column_map[digest_type]

    connection = get_connection(db_config)
    try:
        with connection.cursor() as cursor:
            _get_or_create_settings(cursor, chat_id)
            cursor.execute(
                f"UPDATE bot_settings SET {column} = %s WHERE chat_id = %s",
                (enabled, chat_id)
            )
            connection.commit()

        icon = "✅" if enabled else "❌"
        state = "enabled" if enabled else "disabled"
        return f"{icon} <b>{digest_type}</b> digest {state}"
    finally:
        connection.close()


# ===========================================================================
# Help
# ===========================================================================

def handle_help() -> str:
    return (
        "🤖 <b>News Feed Bot</b>\n\n"

        "📌 <b>Keyword Alerts</b>\n"
        "<code>/add keyword [score]</code> — Add keyword (score 1-10)\n"
        "<code>/remove keyword</code> — Remove a keyword\n"
        "<code>/score keyword N</code> — Update event score\n"
        "<code>/list</code> — List keywords with scores\n\n"

        "📰 <b>Query</b>\n"
        "<code>/latest</code> — Latest 10 headlines\n"
        "<code>/latest AAPL</code> — Latest for a ticker\n"
        "<code>/search ozempic</code> — Search articles\n"
        "<code>/why</code> — Explain last alert + score\n"
        "<code>/summary 1d NVO</code> — Ticker digest\n"
        "<code>/top</code> — Top movers today\n"
        "<code>/top 7d</code> — Top movers this week\n\n"

        "⚙️ <b>Settings</b>\n"
        "<code>/settings</code> — Show preferences\n"
        "<code>/mode quiet|normal</code> — Alert mode\n"
        "<code>/threshold N</code> — Min score to alert\n"
        "<code>/sources name on|off</code> — Toggle source\n"
        "<code>/digest morning|eod|weekly on|off</code>"
    )
