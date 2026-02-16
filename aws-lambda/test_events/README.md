# AWS Lambda Test Events

Test event JSON files for invoking the Lambda function with different actions.

## Available Actions

### 1. Process Keywords (New!)

Process existing articles against keywords to populate `alert_log` table.

**Use Cases:**
- After seeding new keywords, score historical articles
- When no new RSS feeds are available but you want to populate the dashboard
- Re-score articles after updating keyword scores

#### Event: `process_keywords_all.json`
Process the 100 most recent unscored articles:
```json
{
  "action": "process_keywords",
  "params": {
    "limit": 100,
    "unscored_only": true
  }
}
```

#### Event: `process_keywords_date_range.json`
Process articles from a specific date range:
```json
{
  "action": "process_keywords",
  "params": {
    "limit": 500,
    "date_from": "2024-01-01",
    "date_to": "2024-12-31",
    "unscored_only": true
  }
}
```

#### Event: `process_keywords_rescore.json`
Re-score articles (including already scored ones):
```json
{
  "action": "process_keywords",
  "params": {
    "limit": 100,
    "date_from": "2024-01-01",
    "unscored_only": false
  }
}
```

**Parameters:**
- `limit` (int): Number of articles to process (default: 100)
- `date_from` (string): Start date YYYY-MM-DD (optional)
- `date_to` (string): End date YYYY-MM-DD (optional)
- `unscored_only` (boolean): Only process articles not in alert_log (default: true)

**Response:**
```json
{
  "status": "success",
  "message": "Processed 100 articles, 45 had keyword matches",
  "processed": 100,
  "matched": 45,
  "articles_checked": [123, 124, 125, ...]
}
```

### 2. Fetch All Feeds

Fetch all RSS feeds and extract tickers:
```json
{
  "action": "fetch_all"
}
```

### 3. Extract Tickers

Extract tickers from unprocessed articles:
```json
{
  "action": "extract_tickers",
  "params": {
    "limit": 50
  }
}
```

### 4. Search News

Search for specific articles:
```json
{
  "action": "search",
  "params": {
    "keyword": "FDA approval",
    "date_from": "2024-01-01",
    "limit": 20
  }
}
```

## How to Use in AWS Console

1. Go to AWS Lambda Console
2. Select your `aws-lambda` function
3. Go to the "Test" tab
4. Click "Create new event"
5. Copy one of the JSON files above
6. Click "Test" to invoke

## How to Use Locally

```bash
cd aws-lambda
python lambda_function.py
```

## Workflow for Populating Dashboard

**After seeding keywords:**

1. **Seed keywords** (in MySQL):
   ```sql
   SOURCE migrations/seed_alert_keywords.sql;
   ```

2. **Process existing articles** (in AWS Lambda):
   - Use `process_keywords_date_range.json`
   - Adjust date range to match your data
   - Set appropriate limit (start with 100, increase as needed)

3. **Check CloudWatch Logs** for debug output:
   - Keyword loading: "Loaded X active keywords"
   - Matching: "Article X matched Y keywords"
   - Scoring: "Article X score=Z.Z threshold=5 alert=YES/NO"
   - Database writes: "Successfully logged keyword 'X'"

4. **Verify alert_log** (in MySQL):
   ```sql
   SELECT COUNT(*) FROM alert_log;
   SELECT * FROM alert_log ORDER BY id DESC LIMIT 10;
   ```

5. **Refresh dashboard** - Data should now appear!

## Debug Logging

All actions include `[DEBUG]` logging. Check CloudWatch Logs to see:
- Keywords loaded from database
- Articles being processed
- Keyword matches found
- Scores calculated
- Database insertions
