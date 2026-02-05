# Stock Ticker Detection Feature

## Overview

The RSS tracking system now automatically detects and tracks stock ticker symbols mentioned in news articles. This feature helps you quickly find all news related to specific companies.

## How It Works

### Bloomberg Feed
- **Direct Extraction**: Bloomberg RSS feeds include stock ticker symbols in category tags
- Example: `<category domain="stock-symbol">NYS:PLTR</category>`
- Tickers are extracted automatically without any parsing needed
- Supports NYSE and NASDAQ exchanges

### Fierce Biotech Feed
- **Pattern Matching**: Uses a comprehensive company database to detect company names
- Matches company names in article titles and summaries
- Maps detected companies to their stock tickers
- Example: "Astellas" → "4503.T" (Tokyo Stock Exchange)

## Database Schema

Two new columns added to `rss_items` table:

| Column | Type | Description |
|--------|------|-------------|
| stock_tickers | VARCHAR(500) | Comma-separated ticker symbols (e.g., "PLTR,KKR") |
| company_names | VARCHAR(1000) | Comma-separated company names detected |

## Supported Companies

The system tracks 40+ pharmaceutical, biotech, and healthcare companies including:

**Pharmaceutical:**
- Astellas (4503.T), Pfizer (PFE), Novartis (NVS), Roche (RHHBY)
- Merck (MRK), J&J (JNJ), Bristol Myers Squibb (BMY)
- Eli Lilly (LLY), AbbVie (ABBV), GSK (GSK), Sanofi (SNY)
- AstraZeneca (AZN), Novo Nordisk (NVO), Bayer (BAYRY), Takeda (TAK)

**Biotech:**
- Moderna (MRNA), BioNTech (BNTX), Vertex (VRTX)
- Regeneron (REGN), Biogen (BIIB), Illumina (ILMN)
- Amgen (AMGN), Gilead (GILD)

**Medical Device:**
- Medtronic (MDT), Abbott (ABT), GE HealthCare (GEHC)

See `services/stock_ticker_data.py` for the complete list.

## Usage

### Search by Stock Ticker

Find all news articles mentioning a specific stock:

```json
{
  "action": "search",
  "params": {
    "ticker": "4503.T"
  }
}
```

Example response:
```json
{
  "status": "success",
  "count": 3,
  "items": [
    {
      "id": 123,
      "title": "Astellas tops expectations as Vyloy sales surge",
      "stock_tickers": "4503.T",
      "company_names": "Astellas Pharma Inc.",
      "link": "https://www.fiercebiotech.com/...",
      "published_at": "2026-02-05T10:31:00"
    }
  ]
}
```

### Search by Company Name

```json
{
  "action": "search",
  "params": {
    "company": "Astellas"
  }
}
```

### Combined Searches

You can combine ticker/company search with other filters:

```json
{
  "action": "search",
  "params": {
    "ticker": "PFE",
    "keyword": "FDA approval",
    "date_from": "2026-02-01",
    "limit": 20
  }
}
```

## Adding New Companies

To add new companies to the tracking system:

1. Edit `services/stock_ticker_data.py`
2. Add company to `COMPANY_TICKER_MAP`:

```python
"company name": {
    "ticker": "TICK",
    "exchange": "NYSE",  # or "NASDAQ"
    "full_name": "Full Company Name Inc.",
    "aliases": ["alternate name", "abbreviation"]
}
```

3. The system will automatically detect the new company in future feed fetches

## Migration

To add stock ticker fields to existing database:

```bash
mysql -u your_user -p news_feed < migrations/002_add_stock_ticker_fields.sql
```

To rollback:

```bash
mysql -u your_user -p news_feed < migrations/002_rollback_stock_ticker_fields.sql
```

## API Examples

### AWS Lambda Invocation

```bash
# Find all Pfizer news
aws lambda invoke \
  --function-name rss-feed-tracker \
  --payload '{"action": "search", "params": {"ticker": "PFE"}}' \
  response.json

# Find news about multiple companies
aws lambda invoke \
  --function-name rss-feed-tracker \
  --payload '{"action": "search", "params": {"company": "Novo Nordisk"}}' \
  response.json
```

### SQL Queries

Query the database directly:

```sql
-- Find all articles mentioning Astellas
SELECT title, stock_tickers, published_at
FROM rss_items
WHERE stock_tickers LIKE '%4503.T%'
ORDER BY published_at DESC;

-- Find articles about multiple pharma companies
SELECT title, company_names, stock_tickers, published_at
FROM rss_items
WHERE stock_tickers IN ('PFE', 'MRK', 'LLY')
ORDER BY published_at DESC;

-- Top mentioned companies
SELECT stock_tickers, company_names, COUNT(*) as mentions
FROM rss_items
WHERE stock_tickers IS NOT NULL
GROUP BY stock_tickers, company_names
ORDER BY mentions DESC
LIMIT 10;
```

## How Detection Works

### For Bloomberg Articles

1. RSS feed is fetched
2. Category tags are scanned for `stock-symbol` domain
3. Tickers are extracted directly (e.g., "NYS:PLTR" → "PLTR")
4. Only NYSE and NASDAQ tickers are stored

### For Fierce Biotech Articles

1. Article title and summary are analyzed
2. Text is scanned for company names using word-boundary matching
3. Detected names are mapped to stock tickers via the company database
4. Only NYSE and NASDAQ companies are stored

### Example Detection

**Article Title:** "Astellas tops expectations as Vyloy sales surge outshines trial setback"

**Detection Process:**
1. Scan title for known company names
2. Find match: "Astellas"
3. Lookup in database: `COMPANY_TICKER_MAP['astellas']`
4. Extract ticker: "4503.T"
5. Store: `stock_tickers="4503.T"`, `company_names="Astellas Pharma Inc."`

## Limitations

- Only tracks companies in the predefined database
- Focuses on NYSE and NASDAQ (other exchanges filtered out)
- Does not track drug/product names
- Pattern matching may miss misspellings or variations
- Requires manual updates to add new companies

## Future Enhancements

Possible improvements:
- Named Entity Recognition (NER) for automatic company detection
- External API integration (Alpha Vantage, Yahoo Finance)
- Real-time stock price tracking
- Sentiment analysis for stock-related news
- Alert system for specific ticker mentions
