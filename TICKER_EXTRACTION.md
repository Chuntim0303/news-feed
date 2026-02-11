# Company Name and Ticker Extraction

This document describes the system for extracting company names from RSS feed titles and mapping them to stock ticker symbols.

## Overview

The ticker extraction system uses **spaCy's Named Entity Recognition (NER)** to identify company names in article titles and summaries, then maps them to stock ticker symbols using a curated company database.

## Database Schema

The `rss_items` table already includes fields for storing extracted ticker information (added in migration 002):

```sql
ALTER TABLE rss_items
ADD COLUMN stock_tickers VARCHAR(500) NULL COMMENT 'Comma-separated stock ticker symbols',
ADD COLUMN company_names VARCHAR(1000) NULL COMMENT 'Comma-separated company names detected';

CREATE INDEX idx_stock_tickers ON rss_items(stock_tickers);
```

### Fields

- **`stock_tickers`**: Comma-separated list of ticker symbols (e.g., "PFE,MRNA,AZN")
- **`company_names`**: Comma-separated list of detected company names (e.g., "Pfizer,Moderna,AstraZeneca")

## Components

### 1. Company Extractor (`services/company_extractor.py`)

The main extraction module that provides:

- **`CompanyExtractor`**: Main class for NER-based company extraction
  - Uses spaCy's `en_core_web_sm` model for entity recognition
  - Extracts organizations from text
  - Maps company names to tickers using fuzzy matching
  - Handles company name normalization (removes Inc., Corp., Ltd., etc.)

#### Key Methods

```python
# Initialize extractor
extractor = CompanyExtractor()

# Extract companies and tickers from text
result = extractor.extract_companies_and_tickers("Pfizer and Moderna announce partnership")
# Returns: {
#     'companies': ['Pfizer', 'Moderna'],
#     'tickers': ['MRNA', 'PFE'],
#     'matches': [detailed match info...],
#     'unmatched': []
# }

# Format for database storage
stock_tickers, company_names = extractor.format_for_database(result)
# Returns: ("MRNA,PFE", "Pfizer,Moderna")
```

### 2. Stock Ticker Database (`services/stock_ticker_data.py`)

Curated mappings of company names to ticker symbols:

- **35+ pharmaceutical and biotech companies**
- **Major tech companies** (Apple, Microsoft, Google)
- **Healthcare and medical device companies**
- **Financial companies**

Each entry includes:
- Ticker symbol
- Exchange (NYSE, NASDAQ, OTC, etc.)
- Full company name
- Aliases for matching variations

```python
"pfizer": {
    "ticker": "PFE",
    "exchange": "NYSE",
    "full_name": "Pfizer Inc.",
    "aliases": []
}
```

### 3. Local Extraction Script (`extract_tickers_local.py`)

Command-line tool for testing and processing:

```bash
# Test with sample titles
python extract_tickers_local.py --test

# Extract from specific text
python extract_tickers_local.py --text "Apple and Microsoft announce partnership"

# Process database records (dry run)
python extract_tickers_local.py --process --limit 10

# Process and UPDATE database
python extract_tickers_local.py --process --update --limit 100
```

## Installation

### 1. Install Dependencies

```bash
# Install Python packages
pip install -r requirements-local.txt

# Download spaCy language model
python -m spacy download en_core_web_sm
```

### 2. Configure Environment

Create a `.env` file with database credentials:

```bash
DB_HOST=localhost
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=news_feed
DB_PORT=3306
```

## Usage Examples

### Example 1: Test Extraction

```bash
python extract_tickers_local.py --test
```

Output:
```
1. Title: Pfizer and BioNTech announce new vaccine partnership
--------------------------------------------------------------------------------
   Detected Companies: Pfizer, BioNTech
   Tickers Found: BNTX, PFE
   Matched Details:
      - Pfizer → PFE (NYSE) [exact, high]
      - BioNTech → BNTX (NASDAQ) [exact, high]
```

### Example 2: Extract from Custom Text

```bash
python extract_tickers_local.py --text "Moderna and Regeneron collaborate on new therapy"
```

### Example 3: Process Database Records

```bash
# Preview what would be extracted (no database changes)
python extract_tickers_local.py --process --limit 10

# Actually update the database
python extract_tickers_local.py --process --update --limit 100
```

### Example 4: Use in Python Code

```python
from services.company_extractor import CompanyExtractor

# Initialize
extractor = CompanyExtractor()

# Extract from article
title = "Apple and Microsoft expand healthcare AI partnership"
result = extractor.extract_companies_and_tickers(title)

print(f"Companies: {result['companies']}")
print(f"Tickers: {result['tickers']}")

# Format for database
stock_tickers, company_names = extractor.format_for_database(result)

# Update database
cursor.execute(
    "UPDATE rss_items SET stock_tickers = %s, company_names = %s WHERE id = %s",
    (stock_tickers, company_names, item_id)
)
```

## Matching Strategy

The extractor uses a multi-level matching strategy:

1. **Exact Match**: Normalized company name matches database exactly
   - "pfizer" → "pfizer" ✓

2. **Alias Match**: Company name matches a known alias
   - "J&J" → "johnson & johnson" ✓
   - "GSK" → "glaxosmithkline" ✓

3. **Partial Match**: Fuzzy matching for variations
   - "Pfizer Inc" → "pfizer" ✓
   - "Novo Nordisk A/S" → "novo nordisk" ✓

4. **Normalization**: Removes common suffixes and variations
   - Inc., Corp., Ltd., LLC, PLC, AG, S.A., etc.

## Integration with Lambda

To integrate ticker extraction into the Lambda function:

### Option 1: Lightweight Extraction (Recommended for Lambda)

Use the existing `stock_ticker_data.py` with simple string matching (no spaCy):

```python
# In lambda_function.py
from services.stock_ticker_data import COMPANY_TICKER_MAP, ALIAS_TO_COMPANY

def simple_ticker_extraction(title):
    """Extract tickers using simple string matching."""
    title_lower = title.lower()
    found_tickers = []
    found_companies = []

    for company, data in COMPANY_TICKER_MAP.items():
        if company in title_lower:
            found_tickers.append(data['ticker'])
            found_companies.append(company)

    return ','.join(found_tickers), ','.join(found_companies)
```

### Option 2: Full NER Extraction (Large deployment package)

Include spaCy in Lambda deployment (adds ~100MB):

```python
# In lambda_function.py
from services.company_extractor import CompanyExtractor

extractor = CompanyExtractor()

def extract_with_ner(title, summary):
    text = f"{title}. {summary}" if summary else title
    result = extractor.extract_companies_and_tickers(text)
    return extractor.format_for_database(result)
```

**Note**: spaCy models are large (~40-100MB). For Lambda, consider:
- Using Lambda layers for spaCy
- Using EFS to store the model
- Running extraction in a separate step (recommended)

## Future Enhancements

### 1. Enhanced Ticker Database

Expand `stock_ticker_data.py` with:
- More companies (currently ~35, target 500+)
- Industry categorization
- Market cap information
- Subsidiary relationships

### 2. Stock Price Integration

Query real-time stock prices for extracted tickers:

```python
# Future: services/stock_price_fetcher.py
def fetch_stock_prices(tickers: List[str]) -> Dict[str, float]:
    """Fetch current prices for tickers using yfinance or Alpha Vantage."""
    # Implementation to follow
```

Add to schema:
```sql
CREATE TABLE stock_prices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    price DECIMAL(10, 2),
    change_percent DECIMAL(5, 2),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ticker (ticker),
    INDEX idx_fetched_at (fetched_at)
);
```

### 3. Automated Extraction Pipeline

Run extraction as a scheduled job:

```bash
# Cron job to extract tickers from new articles
0 */6 * * * cd /path/to/news-feed && python extract_tickers_local.py --process --update --limit 1000
```

### 4. Machine Learning Enhancements

- Fine-tune spaCy NER on financial news
- Add custom entity recognition for ticker symbols (e.g., "$AAPL")
- Train classifier to identify relevant companies vs. incidental mentions

## Troubleshooting

### spaCy Model Not Found

```bash
python -m spacy download en_core_web_sm
```

### Database Connection Error

Check `.env` file and database credentials:
```bash
mysql -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME -e "SELECT 1"
```

### No Companies Detected

The NER model may not recognize some company names. To improve:
- Add company to `stock_ticker_data.py` with common variations as aliases
- Use longer text (combine title + summary) for better context
- Check if company name is too generic (e.g., "General", "Global")

## Performance

- **NER Processing**: ~50-100ms per article title
- **Database Query**: ~5-10ms per record
- **Batch Processing**: ~100 records/minute

For large-scale processing (10,000+ records):
- Use batch updates (100-500 records per transaction)
- Run during off-peak hours
- Consider parallel processing

## License and Attribution

- **spaCy**: MIT License
- **Company ticker data**: Curated from public sources (Yahoo Finance, Google Finance)
- **Database schema**: Custom implementation for this project
