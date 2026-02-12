# News Feed Tracker — System Documentation

A serverless RSS news feed tracking system built on AWS Lambda. It ingests pharma/biotech news, extracts stock tickers, fetches price data, performs news impact analysis, and provides a full Telegram bot interface for alerts, queries, and reporting.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Lambda Functions](#lambda-functions)
- [Database Schema](#database-schema)
- [Telegram Bot Commands](#telegram-bot-commands)
- [Scheduled Digests](#scheduled-digests)
- [Services](#services)
- [Environment Variables](#environment-variables)
- [Migrations](#migrations)
- [Deployment](#deployment)
- [Local Development](#local-development)
- [Project Structure](#project-structure)

---

## Architecture Overview

The system consists of three AWS Lambda functions, a MySQL database, and external APIs:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EventBridge Schedules                        │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────────┐ │
│  │ Every 1-2 hr │  │ Daily after close│  │ Morning / EOD / Weekly│ │
│  └──────┬───────┘  └────────┬─────────┘  └───────────┬───────────┘ │
└─────────┼──────────────────┼─────────────────────────┼─────────────┘
          ▼                  ▼                         ▼
   ┌──────────────┐  ┌───────────────┐  ┌───────────────────────┐
   │  aws-lambda  │  │aws-lambda-daily│  │aws-lambda-telegram-bot│
   │  Feed Ingest │  │ Prices & Anal. │  │   Bot Commands        │
   │  + Tickers   │  │ + Digests      │  │   (via API Gateway)   │
   └──────┬───────┘  └───────┬────────┘  └───────────┬───────────┘
          │                  │                        │
          ▼                  ▼                        ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                      MySQL Database                         │
   │  rss_feeds │ rss_items │ stock_prices │ article_stock_snap. │
   │  companies │ company_aliases │ alert_keywords │ alert_log   │
   │  bot_settings │ bot_source_settings                         │
   └─────────────────────────────────────────────────────────────┘
          │                  │                        │
          ▼                  ▼                        ▼
   ┌──────────────┐  ┌───────────────┐  ┌───────────────────────┐
   │ RSS Feeds    │  │ Twelve Data   │  │ Telegram Bot API      │
   │ (Bloomberg,  │  │ API (OHLCV)   │  │ (alerts, digests,     │
   │  FierceBio)  │  │               │  │  bot commands)        │
   └──────────────┘  └───────────────┘  └───────────────────────┘
```

### Data Flow

1. **aws-lambda** runs every 1-2 hours:
   - Fetches RSS feeds (Bloomberg, Fierce Biotech)
   - Saves new articles to `rss_items`
   - Checks new articles against keyword alerts → sends Telegram notification
   - Extracts company names and stock tickers (spaCy NER + alias matching)
   - Sets `ticker_processed = 1` on every article it processes

2. **aws-lambda-daily** runs once daily after market close:
   - Fetches stock prices from Twelve Data API for articles with tickers
   - Builds `article_stock_snapshots` (price at publication vs next trading day)
   - Sets `price_processed = 1` on every article it processes
   - Retries articles with incomplete snapshots (NULL prices) within 48h
   - Sends scheduled digests (morning brief, EOD recap, weekly report)

3. **aws-lambda-telegram-bot** runs on demand via API Gateway webhook:
   - Receives Telegram messages, parses commands
   - Manages keywords, queries articles, adjusts settings

---

## Lambda Functions

### aws-lambda — Feed Ingestion & Ticker Extraction

| Action | Description | Default |
|---|---|---|
| `fetch_all` | Fetch all feeds + auto-extract tickers | ✅ (default) |
| `fetch_bloomberg` | Fetch Bloomberg RSS feed only | |
| `fetch_fiercebiotech` | Fetch Fierce Biotech RSS feed only | |
| `extract_tickers` | Extract tickers from unprocessed articles | |
| `search` | Search news items by keyword/source/ticker/date | |

**Invocation:**
```json
{"action": "fetch_all"}
{"action": "extract_tickers", "params": {"limit": 100}}
{"action": "search", "params": {"keyword": "ozempic", "limit": 20}}
```

### aws-lambda-daily — Stock Prices, Analysis & Digests

| Action | Description | Default |
|---|---|---|
| `run_daily` | Full pipeline: prices → snapshots → report | ✅ (default) |
| `fetch_stock_prices` | Fetch stock prices only | |
| `news_impact` | Query news impact data | |
| `send_report` | Generate PDF report and send via Telegram | |
| `morning_brief` | Send morning digest to subscribed chats | |
| `eod_recap` | Send end-of-day recap to subscribed chats | |
| `weekly_report` | Send weekly keyword-impact report | |

**Invocation:**
```json
{"action": "run_daily"}
{"action": "fetch_stock_prices", "params": {"limit": 200, "lookback_hours": 48}}
{"action": "morning_brief"}
{"action": "eod_recap"}
{"action": "weekly_report"}
```

### aws-lambda-telegram-bot — Bot Command Handler

Triggered by API Gateway POST `/webhook`. Receives Telegram updates and routes commands. See [Telegram Bot Commands](#telegram-bot-commands) below.

---

## Database Schema

### Core Tables

| Table | Purpose | Created by |
|---|---|---|
| `rss_feeds` | Feed metadata (URL, title, fetch schedule) | Migration 001 |
| `rss_items` | Individual articles (title, summary, tickers, processing flags) | Migration 001 |
| `companies` | Known companies with ticker symbols | Migration 004 |
| `company_aliases` | Alternative names for companies | Migration 004 |

### Stock Analysis Tables

| Table | Purpose | Created by |
|---|---|---|
| `stock_prices` | OHLCV price data from Twelve Data API | Migration 003 |
| `article_stock_snapshots` | Links articles to price changes | Migration 003 |

### Alert & Bot Tables

| Table | Purpose | Created by |
|---|---|---|
| `alert_keywords` | User-defined keywords with `event_score` (1-10) | Migration 006 + 008 |
| `alert_log` | Log of all matches with full score breakdown | Migration 006 + 008 |
| `bot_settings` | Per-chat preferences (mode, threshold, digests) | Migration 007 |
| `bot_source_settings` | Per-chat source enable/disable | Migration 007 |

### Processing Flags (rss_items)

| Column | Default | Set to 1 when |
|---|---|---|
| `ticker_processed` | 0 | Ticker extraction ran (whether tickers found or not) |
| `price_processed` | 0 | Price fetch + snapshot ran for this article |

**Tracing failures:**
```sql
-- Ticker extraction ran but found nothing
SELECT id, title FROM rss_items
WHERE ticker_processed = 1 AND (stock_tickers IS NULL OR stock_tickers = '');

-- Price processing ran but snapshot has NULL prices
SELECT ri.id, ri.title, ass.ticker
FROM rss_items ri
JOIN article_stock_snapshots ass ON ass.article_id = ri.id
WHERE ri.price_processed = 1
  AND (ass.price_at_publication IS NULL OR ass.price_current IS NULL);

-- Not yet processed at all
SELECT id, title FROM rss_items WHERE ticker_processed = 0;
```

---

## Telegram Bot Commands

### Keyword Alerts

| Command | Description | Example |
|---|---|---|
| `/add <keyword> [score]` | Add keyword with event score (1-10, default 5) | `/add pfizer 8` |
| `/remove <keyword>` | Remove a keyword alert | `/remove pfizer` |
| `/score <keyword> N` | Update event score for a keyword | `/score pfizer 9` |
| `/list` | List all active keywords with scores | `/list` |

### Query

| Command | Description | Example |
|---|---|---|
| `/latest` | Latest 10 headlines | `/latest` |
| `/latest <ticker\|source>` | Filter by ticker or source | `/latest AAPL` |
| `/search <query>` | Search articles by keyword | `/search ozempic` |
| `/why` | Explain last alert with full score breakdown | `/why` |
| `/why <id>` | Explain a specific article's alert | `/why 1234` |
| `/summary [Nd] [TICKER]` | Digest summary for period/ticker | `/summary 1d NVO` |
| `/top [Nd]` | Top movers by price impact | `/top 7d` |

### Settings

| Command | Description | Example |
|---|---|---|
| `/settings` | Show current preferences | `/settings` |
| `/mode quiet\|normal` | Alert mode (quiet = score ≥ 10 only) | `/mode quiet` |
| `/threshold N` | Min news score to trigger alert | `/threshold 6` |
| `/sources <name> on\|off` | Enable/disable a feed source | `/sources bloomberg off` |
| `/digest <type> on\|off` | Toggle digest (morning/eod/weekly) | `/digest morning off` |
| `/help` | Show all available commands | `/help` |

### News Scoring Model

Articles are scored using a composite model instead of alerting on every keyword match:

```
Final Score = (Sum of Keyword Event Scores) × Market Cap Multiplier + Surprise Score
```

- **Keyword Event Score** (1-10 per keyword): User-assigned importance
- **Market Cap Multiplier**: <$1B → ×1.6, $1B-5B → ×1.3, $5B-20B → ×1.1, >$20B → ×1.0
- **Surprise Score** (0-5): NLP detection of "unexpected", "exceeded expectations", "clinical hold", etc.

Alerts are only sent when the final score ≥ your threshold. All matches are logged regardless.
Use `/why` to see the full score breakdown for any alert.

See `NEWS_SCORING_MODEL.md` for the complete model documentation.

### How Keyword Alerts Work

```
1. User sends /add pfizer 8 via Telegram
2. Bot Lambda inserts "pfizer" with event_score=8 into alert_keywords
3. Feed Lambda runs hourly, fetches new RSS articles
4. Each new article is checked against all active keywords
5. If matched, the article is scored:
   a. Sum keyword event scores (e.g. pfizer=8 + FDA=6 = 14)
   b. Apply market cap multiplier (e.g. ×1.3 for $2B company)
   c. Detect surprise phrases (e.g. "unexpected" → +2)
   d. Final score = (14 × 1.3) + 2 = 20.2
6. If score ≥ threshold → Telegram alert sent with score breakdown
7. All matches logged to alert_log (even if below threshold)
```

---

## Scheduled Digests

Digests are actions on the **aws-lambda-daily** Lambda, triggered by separate EventBridge schedules.

| Digest | Action | Schedule | Content |
|---|---|---|---|
| Morning Brief | `morning_brief` | 9:00 AM local (weekdays) | Top 5 headlines + watchlist matches |
| EOD Recap | `eod_recap` | After market close (weekdays) | Top movers + alerts triggered + links |
| Weekly Report | `weekly_report` | Sunday evening | Keyword-spike correlations, most volatile tickers |

**EventBridge cron expressions (UTC+8 examples):**

```
Morning brief:  cron(0 1 ? * MON-FRI *)    → 9:00 AM UTC+8
EOD recap:      cron(30 8 ? * MON-FRI *)    → 4:30 PM UTC+8
Weekly report:  cron(0 14 ? * SUN *)        → 10:00 PM UTC+8 Sunday
```

**EventBridge event payloads:**
```json
{"action": "morning_brief"}
{"action": "eod_recap"}
{"action": "weekly_report"}
```

Users can toggle digests via Telegram:
- `/digest morning off` — disable morning brief
- `/digest eod on` — enable EOD recap
- `/settings` — view current digest preferences

---

## Services

### aws-lambda/services/

| Service | Purpose |
|---|---|
| `base_rss_service.py` | Abstract base class for RSS feed parsing and saving |
| `bloomberg_service.py` | Bloomberg RSS feed parser |
| `fiercebiotech_service.py` | Fierce Biotech RSS feed parser |
| `company_extractor.py` | spaCy NER + alias matching for ticker extraction |
| `keyword_alert_service.py` | Matches articles against keywords, sends Telegram alerts |
| `stock_ticker_data.py` | Hardcoded company/ticker data (fallback) |

### aws-lambda-daily/services/

| Service | Purpose |
|---|---|
| `stock_price_service.py` | Twelve Data API integration, price storage, snapshot building |
| `telegram_report_service.py` | PDF report generation (fpdf2) and Telegram delivery |

### aws-lambda-telegram-bot/

| File | Purpose |
|---|---|
| `lambda_function.py` | Webhook handler, command routing, Telegram messaging |
| `bot_handlers.py` | All command handler logic (keywords, queries, settings) |

---

## Environment Variables

### aws-lambda (Feed Ingestion)

| Variable | Required | Description |
|---|---|---|
| `DB_HOST` | ✅ | MySQL host |
| `DB_USER` | ✅ | MySQL user |
| `DB_PASSWORD` | ✅ | MySQL password |
| `DB_NAME` | ✅ | MySQL database name |
| `DB_PORT` | | MySQL port (default: 3306) |
| `TELEGRAM_BOT_TOKEN` | | For keyword alerts |
| `TELEGRAM_CHAT_ID` | | For keyword alerts |

### aws-lambda-daily (Prices & Analysis)

| Variable | Required | Description |
|---|---|---|
| `DB_HOST` | ✅ | MySQL host |
| `DB_USER` | ✅ | MySQL user |
| `DB_PASSWORD` | ✅ | MySQL password |
| `DB_NAME` | ✅ | MySQL database name |
| `DB_PORT` | | MySQL port (default: 3306) |
| `TWELVE_DATA_API_KEY` | ✅ | Twelve Data API key |
| `TELEGRAM_BOT_TOKEN` | | For reports and digests |
| `TELEGRAM_CHAT_ID` | | For reports and digests |

### aws-lambda-telegram-bot (Bot Interface)

| Variable | Required | Description |
|---|---|---|
| `DB_HOST` | ✅ | MySQL host |
| `DB_USER` | ✅ | MySQL user |
| `DB_PASSWORD` | ✅ | MySQL password |
| `DB_NAME` | ✅ | MySQL database name |
| `DB_PORT` | | MySQL port (default: 3306) |
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | | Restrict bot to this chat only |

---

## Migrations

Run migrations in order. Each has a corresponding rollback file.

| # | File | Purpose |
|---|---|---|
| 001 | `001_create_rss_tables.sql` | `rss_feeds` and `rss_items` tables |
| 002 | `002_add_stock_ticker_fields.sql` | Add `stock_tickers`, `company_names` to `rss_items` |
| 003 | `003_create_stock_prices_table.sql` | `stock_prices` and `article_stock_snapshots` tables |
| 004 | `004_create_companies_table.sql` | `companies` and `company_aliases` tables |
| 004 | `004_seed_companies.sql` | Seed initial company data |
| 005 | `005_add_processing_flags.sql` | Add `ticker_processed`, `price_processed` to `rss_items` |
| 006 | `006_create_alert_keywords_table.sql` | `alert_keywords` and `alert_log` tables |
| 007 | `007_create_bot_settings_table.sql` | `bot_settings` and `bot_source_settings` tables |
| 008 | `008_add_news_scoring.sql` | Add `event_score`, `market_cap_usd`, score breakdown columns |

```bash
# Run all migrations
mysql -u <USER> -p <DB_NAME> < migrations/001_create_rss_tables.sql
mysql -u <USER> -p <DB_NAME> < migrations/002_add_stock_ticker_fields.sql
mysql -u <USER> -p <DB_NAME> < migrations/003_create_stock_prices_table.sql
mysql -u <USER> -p <DB_NAME> < migrations/004_create_companies_table.sql
mysql -u <USER> -p <DB_NAME> < migrations/004_seed_companies.sql
mysql -u <USER> -p <DB_NAME> < migrations/005_add_processing_flags.sql
mysql -u <USER> -p <DB_NAME> < migrations/006_create_alert_keywords_table.sql
mysql -u <USER> -p <DB_NAME> < migrations/007_create_bot_settings_table.sql
mysql -u <USER> -p <DB_NAME> < migrations/008_add_news_scoring.sql
```

---

## Deployment

### Lambda Layers Required

| Layer | Used by | Guide |
|---|---|---|
| spaCy + en_core_web_sm | aws-lambda | `docs/create-spacy-lambda-layer.md` |
| fpdf2 | aws-lambda-daily | `docs/create-fpdf2-lambda-layer.md` |
| PyMySQL + feedparser | aws-lambda, aws-lambda-daily | Bundle with deployment package |

### Build & Deploy (aws-lambda)

```bash
mkdir -p package && cd package
pip install -r ../requirements.txt -t .
cp ../aws-lambda/lambda_function.py .
cp -r ../aws-lambda/services .
zip -r ../aws-lambda-package.zip .
cd .. && rm -rf package

aws lambda update-function-code \
  --function-name news-feed-rss-tracker \
  --zip-file fileb://aws-lambda-package.zip
```

### Build & Deploy (aws-lambda-daily)

```bash
mkdir -p package && cd package
pip install pymysql -t .
cp ../aws-lambda-daily/lambda_function.py .
cp -r ../aws-lambda-daily/services .
zip -r ../aws-lambda-daily-package.zip .
cd .. && rm -rf package

aws lambda update-function-code \
  --function-name news-feed-daily \
  --zip-file fileb://aws-lambda-daily-package.zip
```

### Build & Deploy (aws-lambda-telegram-bot)

```bash
mkdir -p package && cd package
pip install pymysql -t .
cp ../aws-lambda-telegram-bot/lambda_function.py .
cp ../aws-lambda-telegram-bot/bot_handlers.py .
zip -r ../telegram-bot-package.zip .
cd .. && rm -rf package

aws lambda update-function-code \
  --function-name news-feed-telegram-bot \
  --zip-file fileb://telegram-bot-package.zip
```

### Telegram Bot Webhook Setup

```bash
# Set webhook
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://<API_GATEWAY_URL>/webhook"}'

# Verify
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

### EventBridge Schedules

| Lambda | Schedule | Event |
|---|---|---|
| aws-lambda | `rate(1 hour)` | `{"action": "fetch_all"}` |
| aws-lambda-daily | `cron(30 8 ? * MON-FRI *)` | `{"action": "run_daily"}` |
| aws-lambda-daily | `cron(0 1 ? * MON-FRI *)` | `{"action": "morning_brief"}` |
| aws-lambda-daily | `cron(30 8 ? * MON-FRI *)` | `{"action": "eod_recap"}` |
| aws-lambda-daily | `cron(0 14 ? * SUN *)` | `{"action": "weekly_report"}` |

---

## Local Development

### Prerequisites

- Python 3.12+
- MySQL 8.0+
- spaCy with `en_core_web_sm` model

### Setup

```bash
# Install dependencies
pip install -r requirements-local.txt
python -m spacy download en_core_web_sm

# Copy and configure environment
cp .env.example .env
# Edit .env with your database and API credentials

# Run migrations
mysql -u root -p news_feed < migrations/001_create_rss_tables.sql
# ... (run all migrations in order)
```

### Local Testing

```bash
# Test feed ingestion
cd aws-lambda
python lambda_function.py fetch

# Test ticker extraction
python lambda_function.py tickers

# Test search
python lambda_function.py search
```

### Utility Scripts

| Script | Purpose |
|---|---|
| `import_tickers.py` | Import company/ticker data into the database |
| `extract_tickers_local.py` | Run ticker extraction locally (outside Lambda) |
| `analyze_news_impact.py` | Local news impact analysis script |

---

## Project Structure

```
news-feed/
├── aws-lambda/                     # Lambda 1: Feed ingestion + ticker extraction
│   ├── lambda_function.py          #   Handler (fetch_all, extract_tickers, search)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── base_rss_service.py     #   Abstract RSS feed parser
│   │   ├── bloomberg_service.py    #   Bloomberg feed parser
│   │   ├── fiercebiotech_service.py#   Fierce Biotech feed parser
│   │   ├── company_extractor.py    #   spaCy NER + alias matching
│   │   ├── keyword_alert_service.py#   Keyword matching + Telegram alerts
│   │   ├── stock_ticker_data.py    #   Hardcoded company data (fallback)
│   │   ├── stock_price_service.py  #   (kept for reference, used by daily Lambda)
│   │   └── telegram_report_service.py # (kept for reference, used by daily Lambda)
│   └── SYSTEM_FLOWCHART.md        #   Mermaid architecture diagrams
│
├── aws-lambda-daily/               # Lambda 2: Daily prices + analysis + digests
│   ├── lambda_function.py          #   Handler (run_daily, morning_brief, eod_recap, etc.)
│   └── services/
│       ├── __init__.py
│       ├── stock_price_service.py  #   Twelve Data API + snapshot building
│       └── telegram_report_service.py # PDF report generation
│
├── aws-lambda-telegram-bot/        # Lambda 3: Telegram bot interface
│   ├── lambda_function.py          #   Webhook handler + command routing
│   ├── bot_handlers.py             #   All command logic
│   └── README.md                   #   Bot-specific setup guide
│
├── migrations/                     # Database migrations (001-007)
│   ├── 001_create_rss_tables.sql
│   ├── 002_add_stock_ticker_fields.sql
│   ├── 003_create_stock_prices_table.sql
│   ├── 004_create_companies_table.sql
│   ├── 005_add_processing_flags.sql
│   ├── 006_create_alert_keywords_table.sql
│   ├── 007_create_bot_settings_table.sql
│   └── *_rollback_*.sql            #   Rollback scripts for each migration
│
├── docs/
│   ├── create-spacy-lambda-layer.md
│   └── create-fpdf2-lambda-layer.md
│
├── .env.example                    # Environment variable template
├── requirements.txt                # Lambda dependencies
├── requirements-local.txt          # Local development dependencies
├── deploy.sh                       # Deployment script
├── DOCUMENTATION.md                # This file
└── TICKER_EXTRACTION.md            # Ticker extraction details
```
