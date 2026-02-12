# System Flowchart — Three-Lambda Architecture

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Triggers
        EV1["EventBridge<br/>Every 1-2 hours"]
        EV2["EventBridge<br/>Daily ~4:30 PM ET"]
        TG_IN["Telegram User<br/>/add /remove /list"]
    end

    EV1 --> L1
    EV2 --> L2
    TG_IN --> APIGW["API Gateway<br/>(POST /webhook)"]
    APIGW --> L3

    subgraph L1["aws-lambda — Feed Ingestion & Ticker Extraction"]
        direction TB
        H1["lambda_handler()"]
        H1 -->|"fetch_all<br/>(default)"| FETCH_ALL
        H1 -->|"fetch_bloomberg"| FETCH_BB
        H1 -->|"fetch_fiercebiotech"| FETCH_FB
        H1 -->|"extract_tickers"| EXTRACT
        H1 -->|"search"| SEARCH
    end

    subgraph L2["aws-lambda-daily — Stock Prices & Analysis"]
        direction TB
        H2["lambda_handler()"]
        H2 -->|"run_daily<br/>(default)"| DAILY
        H2 -->|"fetch_stock_prices"| PRICES
        H2 -->|"news_impact"| IMPACT
        H2 -->|"send_report"| REPORT
    end

    subgraph L3["aws-lambda-telegram-bot — Keyword Management"]
        direction TB
        H3["lambda_handler()"]
        H3 -->|"/add"| CMD_ADD["INSERT alert_keywords"]
        H3 -->|"/remove"| CMD_RM["UPDATE alert_keywords<br/>is_active = 0"]
        H3 -->|"/list"| CMD_LS["SELECT alert_keywords"]
    end

    subgraph FETCH_ALL["fetch_all_feeds()"]
        direction TB
        FA1["fetch_bloomberg_feed()"] --> FA2["fetch_fiercebiotech_feed()"]
        FA2 --> FA3["extract_tickers()"]
    end

    subgraph FETCH_BB["fetch_bloomberg_feed()"]
        BB1["BloombergService.fetch_and_save()"]
    end

    subgraph FETCH_FB["fetch_fiercebiotech_feed()"]
        FB1["FiercebiotechService.fetch_and_save()"]
    end

    subgraph EXTRACT["extract_tickers()"]
        direction TB
        EX1["Query rss_items<br/>WHERE ticker_processed = 0"]
        EX1 --> EX2["CompanyExtractor<br/>spaCy NER + alias scan"]
        EX2 --> EX3["UPDATE rss_items<br/>SET stock_tickers, ticker_processed = 1"]
    end

    subgraph SEARCH["search_news()"]
        SR1["Query rss_items<br/>by keyword / source / ticker / date"]
    end

    subgraph DAILY["run_daily_pipeline()"]
        direction TB
        D1["Step 1: fetch_stock_prices()"]
        D1 --> D2["Step 2: get_news_impact()"]
        D2 --> D3["Step 3: send_report()<br/>(if Telegram configured)"]
    end

    subgraph PRICES["fetch_stock_prices()"]
        direction TB
        SP1["StockPriceService<br/>.fetch_prices_for_articles()"]
        SP1 --> SP2["Twelve Data API<br/>/time_series (OHLCV)"]
        SP2 --> SP3["store_prices()<br/>→ stock_prices table"]
        SP3 --> SP4["build_article_snapshots()<br/>→ article_stock_snapshots"]
    end

    subgraph IMPACT["get_news_impact()"]
        IM1["JOIN article_stock_snapshots<br/>+ rss_items + stock_prices"]
    end

    subgraph REPORT["send_report()"]
        direction TB
        RP1["TelegramReportService"]
        RP1 --> RP2["Generate PDF (fpdf2)"]
        RP2 --> RP3["Send via Telegram Bot API"]
    end

    L1 -.->|"writes tickers to<br/>rss_items"| DB[(MySQL Database)]
    L1 -.->|"keyword match →<br/>Telegram alert"| TG_OUT["Telegram Bot API<br/>(send alert)"]
    L2 -.->|"reads tickers from<br/>rss_items"| DB
    L3 -.->|"manages keywords in"| DB
```

## RSS Feed Fetch & Save Flow

```mermaid
flowchart TD
    A["BaseRSSService.fetch_and_save()"] --> B["feedparser.parse(feed_url)"]
    B --> C{"feed.bozo?"}
    C -->|Yes| C1["Log warning + continue"]
    C -->|No| D
    C1 --> D["get_db_connection()"]
    D --> E["get_or_create_feed()<br/>→ rss_feeds table"]
    E --> F["update_feed_metadata()"]
    F --> G["Loop: feed.entries"]

    G --> H["Subclass.parse_item(entry)"]
    H --> I["save_item()"]
    I --> J{"IntegrityError?<br/>(duplicate guid)"}
    J -->|No| K["new_items += 1"]
    J -->|Yes| L["existing_items += 1"]
    K --> G
    L --> G

    subgraph Bloomberg ["BloombergService.parse_item()"]
        direction LR
        BL1["Extract: guid, link, title,<br/>author (dc:creator),<br/>summary, content,<br/>media_content → image_url,<br/>published (RFC 822)"]
    end

    subgraph Fierce ["FiercebiotechService.parse_item()"]
        direction LR
        FI1["Extract: guid, link,<br/>title (HTML → text),<br/>author (HTML → text),<br/>summary, content,<br/>custom date parser<br/>(e.g. 'Feb 5, 2026 4:54am')"]
    end

    H -.->|Bloomberg| Bloomberg
    H -.->|FierceBiotech| Fierce
```

## Ticker Extraction Flow

```mermaid
flowchart TD
    A["extract_tickers()"] --> B["CompanyExtractor.__init__()"]
    B --> B1["spacy.load('en_core_web_sm')"]
    B1 --> B2{"use_db?"}
    B2 -->|Yes| B3["_load_from_database()<br/>companies + company_aliases"]
    B2 -->|No / Fail| B4["_build_lookup_index()<br/>hardcoded COMPANY_TICKER_MAP"]
    B3 --> C
    B4 --> C

    C["Query: rss_items WHERE<br/>stock_tickers IS NULL<br/>LIMIT N"] --> D["Loop: articles"]

    D --> E["Combine title + summary"]
    E --> F["extract_companies_and_tickers(text)"]

    F --> G["extract_organizations(text)<br/>spaCy NER → ORG entities"]
    G --> H["_scan_text_for_known_companies(text)<br/>regex word-boundary scan<br/>against alias_map"]
    H --> I["De-duplicate orgs"]
    I --> J["Loop: find_ticker_info(org)"]

    J --> K{"Exact match<br/>in normalized_map?"}
    K -->|Yes| M["Return ticker info"]
    K -->|No| L{"Alias match<br/>in alias_map?"}
    L -->|Yes| M
    L -->|No| N{"Partial match<br/>(substring)?"}
    N -->|Yes| M
    N -->|No| O["Unmatched"]

    M --> P["format_for_database()<br/>→ comma-separated strings"]
    O --> P
    P --> Q{"tickers_str<br/>not empty?"}
    Q -->|Yes| R["UPDATE rss_items<br/>SET stock_tickers, company_names"]
    Q -->|No| S["Skip article"]
```

## Stock Price & Snapshot Flow

```mermaid
flowchart TD
    A["StockPriceService<br/>.fetch_prices_for_articles()"] --> B["Query articles with tickers<br/>but no snapshots yet"]
    B --> C["Group by ticker<br/>merge date ranges"]
    C --> D["Loop: unique tickers"]

    D --> E["_rate_limit()<br/>(8 calls/min)"]
    E --> F["Twelve Data API<br/>GET /time_series<br/>interval=1day"]
    F --> G["Parse OHLCV +<br/>calculate change %"]
    G --> H["store_prices()<br/>INSERT ... ON DUPLICATE KEY UPDATE<br/>→ stock_prices"]
    H --> D

    D -->|All done| I["build_article_snapshots()"]
    I --> J["Loop: article × ticker"]
    J --> K["Get close_price on/before pub_date"]
    J --> L["Get close_price after pub_date"]
    K --> M["Calculate % change"]
    L --> M
    M --> N["INSERT → article_stock_snapshots<br/>ON DUPLICATE KEY UPDATE"]
```

## Database Tables

```mermaid
erDiagram
    rss_feeds ||--o{ rss_items : "feed_id"
    rss_items ||--o{ article_stock_snapshots : "article_id"
    stock_prices ||--o{ article_stock_snapshots : "ticker"
    companies ||--o{ company_aliases : "company_id"

    rss_feeds {
        int id PK
        string url
        string title
        string site_url
        string description
        string language
        datetime last_fetch_at
        datetime next_fetch_at
        string etag
        string last_modified
        boolean is_active
    }

    rss_items {
        int id PK
        int feed_id FK
        string guid UK
        string link
        string title
        string author
        text summary
        text content
        string image_url
        datetime published_at
        datetime fetched_at
        string stock_tickers
        string company_names
        datetime created_at
    }

    companies {
        int id PK
        string name
        string ticker
        string exchange
        string full_name
        boolean is_active
    }

    company_aliases {
        int id PK
        int company_id FK
        string alias
    }

    stock_prices {
        int id PK
        string ticker
        decimal price
        decimal open_price
        decimal high_price
        decimal low_price
        decimal close_price
        bigint volume
        decimal change_amount
        decimal change_percent
        date price_date
    }

    article_stock_snapshots {
        int id PK
        int article_id FK
        string ticker
        decimal price_at_publication
        decimal price_current
        decimal price_change_since_article
    }
```

## Service Dependency Map

```
aws-lambda/ (Feed Ingestion — runs every 1-2 hours)
├── BloombergService        (→ BaseRSSService → feedparser, pymysql)
├── FiercebiotechService    (→ BaseRSSService → feedparser, pymysql)
├── CompanyExtractor        (→ spacy, pymysql, stock_ticker_data)
└── KeywordAlertService     (→ Telegram Bot API, pymysql)

aws-lambda-daily/ (Stock Prices & Analysis — runs once daily after market close)
├── StockPriceService       (→ Twelve Data API, pymysql)
└── TelegramReportService   (→ fpdf2, Telegram Bot API, pymysql)  [optional]

aws-lambda-telegram-bot/ (Keyword Management — API Gateway webhook)
└── lambda_function.py      (→ Telegram Bot API, pymysql)
```

## Recommended Schedules

| Lambda | Trigger | Rationale |
|---|---|---|
| `aws-lambda` | `rate(1 hour)` or `cron(0 */2 * * ? *)` | Frequent feed ingestion to catch new articles |
| `aws-lambda-daily` | `cron(30 21 ? * MON-FRI *)` (4:30 PM ET) | After US market close so all daily prices are final |
| `aws-lambda-telegram-bot` | API Gateway POST `/webhook` | Receives Telegram bot commands in real time |

## Environment Variables

### aws-lambda (Feed Ingestion)

| Variable | Description |
|---|---|
| `DB_HOST` | MySQL host |
| `DB_USER` | MySQL user |
| `DB_PASSWORD` | MySQL password |
| `DB_NAME` | MySQL database name |
| `DB_PORT` | MySQL port (default: 3306) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (for keyword alerts) |
| `TELEGRAM_CHAT_ID` | Telegram chat ID (for keyword alerts) |

### aws-lambda-daily (Stock Prices & Analysis)

| Variable | Description |
|---|---|
| `DB_HOST` | MySQL host |
| `DB_USER` | MySQL user |
| `DB_PASSWORD` | MySQL password |
| `DB_NAME` | MySQL database name |
| `DB_PORT` | MySQL port (default: 3306) |
| `TWELVE_DATA_API_KEY` | Twelve Data API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (optional, for reports) |
| `TELEGRAM_CHAT_ID` | Telegram chat ID (optional, for reports) |

### aws-lambda-telegram-bot (Keyword Management)

| Variable | Description |
|---|---|
| `DB_HOST` | MySQL host |
| `DB_USER` | MySQL user |
| `DB_PASSWORD` | MySQL password |
| `DB_NAME` | MySQL database name |
| `DB_PORT` | MySQL port (default: 3306) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Restrict commands to this chat (optional) |
