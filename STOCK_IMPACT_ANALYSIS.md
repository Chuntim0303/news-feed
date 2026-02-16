# Stock Impact Analysis — Implementation Guide

This document describes the comprehensive improvements made to the stock impact analysis system, implementing proper event study methodology with multi-horizon returns, abnormal returns, and enhanced scoring.

## Table of Contents

- [Overview](#overview)
- [Key Improvements](#key-improvements)
- [Database Schema](#database-schema)
- [Service Architecture](#service-architecture)
- [Usage Examples](#usage-examples)
- [Deployment Guide](#deployment-guide)
- [Backtesting and Calibration](#backtesting-and-calibration)

---

## Overview

The enhanced stock impact analysis system replaces simple "next-day change" tracking with proper event study methodology used in academic finance research. This provides:

- **Causal evidence** through abnormal returns (controlling for market/sector moves)
- **Multi-horizon analysis** to capture delayed effects and mean reversion
- **Confidence metrics** to distinguish signal from noise
- **Decision-grade outputs** for actionable trading insights

---

## Key Improvements

### 1. Multi-Horizon Event Studies

**Problem:** Single next-day returns miss delayed effects and overreaction/reversion patterns.

**Solution:** Track returns at multiple horizons:
- Pre-event: -1D, -3D, -5D (leakage/anticipation detection)
- Post-event: +1D, +3D, +5D, +10D (full reaction window)

**Implementation:**
- `article_return_windows` table stores all horizons
- `EventStudyService` computes returns from price data
- Handles trading day alignment automatically

### 2. Abnormal Returns (Market-Adjusted)

**Problem:** Absolute returns conflate stock-specific news with market/sector moves.

**Solution:** Compute abnormal returns = stock return - benchmark return

**Benchmarks:**
- Market: SPY (S&P 500)
- Sector: XLV (Healthcare), XBI (Biotech), XLK (Technology), etc.

**Implementation:**
- `benchmark_returns` table stores daily benchmark data
- `ticker_sector_mapping` links tickers to appropriate benchmarks
- Abnormal returns computed for all horizons

### 3. Layer 4 Market Reaction Scoring

**Problem:** Current scoring ignores actual market reaction (volume, volatility).

**Solution:** Implement Layer 4 with three components:

| Signal | Score | Threshold |
|--------|-------|-----------|
| Volume spike | 0-2 | >2× or >3× baseline |
| Price gap | 0-2 | >3% or >5% |
| Trending mentions | 0-1 | >3× normal frequency |

**Implementation:**
- `MarketReactionService` computes scores from event study data
- Integrated into final `score_total` calculation
- Cached in `market_reaction_scores` table

### 4. Intraday Timestamp Precision

**Problem:** Daily bars blur effect timing for pre-market/after-hours news.

**Solution:** 
- Store precise publication timestamp
- Classify into market sessions (pre-market, regular, post-market)
- Use event-to-next-session alignment

**Implementation:**
- `publish_timestamp` and `publish_session` columns in `article_stock_snapshots`
- Future: Fetch intraday bars (5m/15m) around publication time

### 5. Ticker Relevance Weighting

**Problem:** Multi-company articles assign all movement equally, inflating false signals.

**Solution:** Compute per-ticker relevance weights:
- Mention frequency (0-0.3)
- Title presence (0-0.5)
- Proximity to trigger phrases (0-0.2)

**Implementation:**
- `TickerRelevanceService` computes weights using NLP
- `ticker_relevance_score` stored in `article_stock_snapshots`
- Only top-N relevant tickers scored per article

### 6. Context-Aware Keyword Matching

**Problem:** Regex matching misses negation and semantic context.

**Solution:** 
- Negation detection ("not approved", "no impact")
- Entity-role linking (which company got approved?)
- Confidence adjustment based on context

**Implementation:**
- `ContextAwareMatcher` service
- Reduces event scores for negated matches
- Tracks context snippets for review

### 7. Processing Status Tracking

**Problem:** Articles marked processed even when price data unavailable.

**Solution:** Explicit status enum with retry logic:
- `not_started`, `partial`, `complete`, `failed`
- Retry count and failure reason tracking
- Alert on stale partial rows

**Implementation:**
- `processing_status` column in `article_return_windows`
- Automatic retry for failed/partial within lookback window
- Status dashboard for monitoring

### 8. Model Calibration & Backtesting

**Problem:** No validation that `score_total` actually predicts returns.

**Solution:** Weekly backtesting job:
- Precision@K for top scored alerts
- Hit rate by score bucket
- Average abnormal return by score decile
- Layer contribution analysis

**Implementation:**
- `BacktestingService` with comprehensive metrics
- Results stored in `scoring_backtest_results`
- Auto-tuning recommendations

### 9. Confounder Detection

**Problem:** Same-day earnings/macro events confound attribution.

**Solution:** 
- Track known confounders (earnings, FDA dates, FOMC)
- Detect sector-wide moves
- Cluster duplicate articles
- Compute confidence score

**Implementation:**
- `confounder_events` table
- `ConfounderService` for detection
- Confidence score (0-1) based on confounders present

### 10. Enhanced Digest Outputs

**Problem:** Current digests are descriptive, not decision-grade.

**Solution:** Include:
- Abnormal returns vs benchmark
- Volume ratio percentiles
- Confidence scores
- "Alpha candidates" section (high score + high abnormal return + low confounding)

**Implementation:**
- `EnhancedDigestService` generates decision-grade reports
- Text and HTML formatting
- Telegram/email delivery

---

## Database Schema

### Core Tables

#### `article_return_windows`
Stores multi-horizon returns for each article-ticker pair.

```sql
CREATE TABLE article_return_windows (
    id INT AUTO_INCREMENT PRIMARY KEY,
    article_id INT NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    
    -- Pre-event baseline
    return_pre_1d DECIMAL(8, 4) NULL,
    return_pre_3d DECIMAL(8, 4) NULL,
    return_pre_5d DECIMAL(8, 4) NULL,
    
    -- Post-event windows
    return_1d DECIMAL(8, 4) NULL,
    return_3d DECIMAL(8, 4) NULL,
    return_5d DECIMAL(8, 4) NULL,
    return_10d DECIMAL(8, 4) NULL,
    
    -- Abnormal returns
    abnormal_return_1d DECIMAL(8, 4) NULL,
    abnormal_return_3d DECIMAL(8, 4) NULL,
    abnormal_return_5d DECIMAL(8, 4) NULL,
    abnormal_return_10d DECIMAL(8, 4) NULL,
    
    -- Volume/volatility metrics
    volume_baseline_20d BIGINT NULL,
    volume_ratio_1d DECIMAL(6, 2) NULL,
    volatility_baseline_20d DECIMAL(8, 4) NULL,
    gap_magnitude DECIMAL(8, 4) NULL,
    
    -- Processing status
    processing_status ENUM('not_started', 'partial', 'complete', 'failed'),
    retry_count TINYINT UNSIGNED DEFAULT 0,
    
    UNIQUE KEY unique_article_ticker (article_id, ticker)
);
```

#### `benchmark_returns`
Stores daily returns for market/sector benchmarks.

```sql
CREATE TABLE benchmark_returns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,  -- SPY, XBI, XLV, etc.
    return_date DATE NOT NULL,
    
    return_1d DECIMAL(8, 4) NULL,
    return_3d DECIMAL(8, 4) NULL,
    return_5d DECIMAL(8, 4) NULL,
    return_10d DECIMAL(8, 4) NULL,
    
    UNIQUE KEY unique_ticker_date (ticker, return_date)
);
```

#### `market_reaction_scores`
Caches Layer 4 market reaction scores.

```sql
CREATE TABLE market_reaction_scores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    article_id INT NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    
    volume_score DECIMAL(4, 2) DEFAULT 0,
    gap_score DECIMAL(4, 2) DEFAULT 0,
    trend_score DECIMAL(4, 2) DEFAULT 0,
    total_reaction_score DECIMAL(4, 2) DEFAULT 0,
    
    UNIQUE KEY unique_article_ticker (article_id, ticker)
);
```

### Supporting Tables

- `ticker_sector_mapping`: Maps tickers to sector benchmarks
- `confounder_events`: Known confounding events
- `article_clusters`: Duplicate article detection
- `scoring_backtest_results`: Backtesting metrics

See `migrations/009_add_multi_horizon_returns.sql` for complete schema.

---

## Service Architecture

### Core Services

#### `EventStudyService`
Computes multi-horizon event study returns.

```python
from services.event_study_service import EventStudyService

service = EventStudyService(db_config=db_config)
result = service.compute_event_windows(
    article_id=123,
    ticker='MRNA',
    published_at=datetime(2026, 2, 15)
)
# Returns: {'status': 'success', 'metrics': {...}}
```

**Key methods:**
- `compute_event_windows()`: Full event study for article-ticker pair
- `compute_returns()`: Multi-horizon returns from price data
- `compute_volume_metrics()`: Volume baseline, ratio, z-score
- `compute_volatility_metrics()`: Realized vol, intraday range, gap
- `process_pending_articles()`: Batch processing

#### `MarketReactionService`
Computes Layer 4 market reaction scores.

```python
from services.market_reaction_service import MarketReactionService

service = MarketReactionService(db_config=db_config)
scores = service.compute_reaction_score(article_id=123, ticker='MRNA')
# Returns: {'volume_score': 2.0, 'gap_score': 2.0, 'trend_score': 0.0, 'total_score': 4.0}
```

#### `TickerRelevanceService`
Computes relevance weights for multi-ticker articles.

```python
from services.ticker_relevance_service import TickerRelevanceService

service = TickerRelevanceService()
scores = service.compute_relevance_scores(
    title="Pfizer announces partnership with Moderna",
    summary="...",
    tickers=['PFE', 'MRNA'],
    company_names=['Pfizer', 'Moderna']
)
# Returns: {'PFE': 0.85, 'MRNA': 0.65}
```

#### `ContextAwareMatcher`
Context-aware keyword matching with negation detection.

```python
from services.context_aware_matcher import ContextAwareMatcher

matcher = ContextAwareMatcher()
matches = matcher.match_with_context(
    text="FDA did not approve Pfizer's drug",
    keywords=[{'keyword': 'fda', 'event_score': 6}, ...]
)
# Returns matches with is_negated, confidence, context_snippet
```

#### `ConfounderService`
Detects confounding events.

```python
from services.confounder_service import ConfounderService

service = ConfounderService(db_config=db_config)
confounders = service.detect_confounders(
    ticker='MRNA',
    event_date=datetime(2026, 2, 15)
)
confidence = service.compute_confounder_confidence(confounders)
# Returns: 0.85 (high confidence, few confounders)
```

#### `BacktestingService`
Backtests and calibrates scoring model.

```python
from services.backtesting_service import BacktestingService

service = BacktestingService(db_config=db_config)
results = service.run_backtest(
    start_date='2026-01-01',
    end_date='2026-02-01'
)
recommendations = service.generate_tuning_recommendations(results['results'])
```

#### `EnhancedDigestService`
Generates decision-grade digest reports.

```python
from services.enhanced_digest_service import EnhancedDigestService

service = EnhancedDigestService(db_config=db_config)
digest = service.generate_daily_digest(target_date='2026-02-15')
text_report = service.format_digest_text(digest['digest'])
html_report = service.format_digest_html(digest['digest'])
```

---

## Usage Examples

### Example 1: Process New Articles

```python
# 1. Compute event study windows
event_service = EventStudyService(db_config=db_config)
event_service.process_pending_articles(limit=50, retry_failed=True)

# 2. Compute market reaction scores
reaction_service = MarketReactionService(db_config=db_config)
reaction_service.process_pending_reactions(limit=50)

# 3. Update ticker relevance
relevance_service = TickerRelevanceService()
relevance_service.update_snapshot_relevance(db_config, article_id=123)
```

### Example 2: Generate Daily Digest

```python
digest_service = EnhancedDigestService(db_config=db_config)
digest = digest_service.generate_daily_digest()

# Format as text
text_report = digest_service.format_digest_text(digest['digest'])
print(text_report)

# Format as HTML for email
html_report = digest_service.format_digest_html(digest['digest'])
send_email(html_report)
```

### Example 3: Run Weekly Backtest

```python
backtest_service = BacktestingService(db_config=db_config)

# Run backtest
results = backtest_service.run_backtest(
    start_date='2026-01-01',
    end_date='2026-02-01',
    min_score=5.0
)

# Get recommendations
recommendations = backtest_service.generate_tuning_recommendations(results['results'])
for rec in recommendations:
    print(rec)
```

### Example 4: Check Article Confidence

```python
confounder_service = ConfounderService(db_config=db_config)

# Detect confounders
confounders = confounder_service.detect_confounders(
    ticker='MRNA',
    event_date=datetime(2026, 2, 15),
    window_days=1
)

# Compute confidence
confidence = confounder_service.compute_confounder_confidence(confounders)
print(f"Attribution confidence: {confidence:.0%}")

if confidence < 0.7:
    print("⚠️ Low confidence due to confounders:")
    for conf in confounders:
        print(f"  - {conf['type']}: {conf['description']}")
```

---

## Deployment Guide

### 1. Run Database Migration

```bash
# Connect to MySQL
mysql -u root -p news_feed

# Run migration
source migrations/009_add_multi_horizon_returns.sql
```

### 2. Seed Sector Mappings

The migration includes common sector mappings. Add more:

```sql
INSERT INTO ticker_sector_mapping (ticker, sector, sector_etf, market_benchmark) VALUES
('NVDA', 'Technology', 'XLK', 'SPY'),
('TSLA', 'Consumer Discretionary', 'XLY', 'SPY')
ON DUPLICATE KEY UPDATE sector = VALUES(sector);
```

### 3. Populate Benchmark Returns

Fetch historical benchmark data:

```python
from services.event_study_service import EventStudyService

service = EventStudyService(db_config=db_config)

# Fetch SPY, XBI, XLV data for last 90 days
benchmarks = ['SPY', 'XBI', 'XLV', 'XLK', 'XLY']
for ticker in benchmarks:
    prices = service.fetch_prices_around_date(
        ticker=ticker,
        center_date=datetime.now(),
        days_before=90,
        days_after=0
    )
    # Store in benchmark_returns table
```

### 4. Update Lambda Function

Add new services to Lambda deployment:

```bash
# Copy new service files
cp aws-lambda-daily/services/event_study_service.py lambda-package/services/
cp aws-lambda-daily/services/market_reaction_service.py lambda-package/services/
cp aws-lambda-daily/services/ticker_relevance_service.py lambda-package/services/
cp aws-lambda-daily/services/context_aware_matcher.py lambda-package/services/
cp aws-lambda-daily/services/confounder_service.py lambda-package/services/
cp aws-lambda-daily/services/backtesting_service.py lambda-package/services/
cp aws-lambda-daily/services/enhanced_digest_service.py lambda-package/services/

# Deploy Lambda
./deploy_lambda.sh
```

### 5. Update Daily Pipeline

Modify `lambda_function.py` to include new steps:

```python
def run_daily_pipeline(db_config, params=None):
    results = {}
    
    # Step 1: Fetch stock prices (existing)
    price_result = fetch_stock_prices(db_config, params)
    results['stock_prices'] = price_result
    
    # Step 2: Compute event study windows (NEW)
    event_service = EventStudyService(db_config=db_config)
    event_result = event_service.process_pending_articles(limit=50)
    results['event_study'] = event_result
    
    # Step 3: Compute market reaction scores (NEW)
    reaction_service = MarketReactionService(db_config=db_config)
    reaction_result = reaction_service.process_pending_reactions(limit=50)
    results['market_reaction'] = reaction_result
    
    # Step 4: Generate enhanced digest (NEW)
    digest_service = EnhancedDigestService(db_config=db_config)
    digest = digest_service.generate_daily_digest()
    results['digest'] = digest
    
    # Step 5: Send Telegram report (updated with enhanced digest)
    if digest['status'] == 'success':
        text_report = digest_service.format_digest_text(digest['digest'])
        send_telegram_message(text_report)
    
    return results
```

---

## Backtesting and Calibration

### Running Backtests

Run weekly to validate model performance:

```python
backtest_service = BacktestingService(db_config=db_config)

# Last 30 days
results = backtest_service.run_backtest(
    start_date=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
    end_date=datetime.now().strftime('%Y-%m-%d'),
    min_score=5.0
)

print(f"Precision@10: {results['results']['precision_at_k']['precision']:.0%}")
print(f"Hit rate (20-30 bucket): {results['results']['hit_rate_by_bucket']['20-30']['hit_rate']:.0%}")
```

### Key Metrics

1. **Precision@K**: % of top K scored articles with |abnormal_return| > 2%
   - Target: >50% for K=10

2. **Hit Rate by Bucket**: % with significant moves per score range
   - Target: Monotonically increasing with score

3. **Average Abnormal Return by Decile**: Mean return per score decile
   - Target: Positive correlation between score and return

4. **Layer Contribution**: Correlation of each layer with returns
   - Target: All layers show positive correlation

### Tuning Recommendations

Based on backtest results:

- **Low Precision@10**: Raise alert threshold or adjust layer weights
- **Negligible layer correlation**: Remove or re-weight that layer
- **Low hit rate in high buckets**: Scoring model needs recalibration

---

## Monitoring and Alerts

### Processing Status Dashboard

Query articles needing attention:

```sql
-- Articles with failed processing
SELECT article_id, ticker, failure_reason, retry_count
FROM article_return_windows
WHERE processing_status = 'failed'
  AND retry_count >= 3
ORDER BY last_processed_at DESC;

-- Stale partial rows (>24h old)
SELECT article_id, ticker, last_processed_at
FROM article_return_windows
WHERE processing_status = 'partial'
  AND last_processed_at < NOW() - INTERVAL 24 HOUR;
```

### Performance Metrics

```sql
-- Processing success rate
SELECT 
    processing_status,
    COUNT(*) as count,
    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
FROM article_return_windows
WHERE last_processed_at >= NOW() - INTERVAL 7 DAY
GROUP BY processing_status;

-- Average abnormal returns by score bucket
SELECT 
    CASE 
        WHEN score_total < 10 THEN '5-10'
        WHEN score_total < 15 THEN '10-15'
        WHEN score_total < 20 THEN '15-20'
        WHEN score_total < 30 THEN '20-30'
        ELSE '30+'
    END as score_bucket,
    COUNT(*) as count,
    AVG(abnormal_return_1d) as avg_abnormal_return,
    AVG(ABS(abnormal_return_1d)) as avg_abs_abnormal_return
FROM alert_log al
JOIN article_return_windows arw ON arw.article_id = al.rss_item_id
WHERE arw.processing_status = 'complete'
  AND arw.abnormal_return_1d IS NOT NULL
  AND al.created_at >= NOW() - INTERVAL 30 DAY
GROUP BY score_bucket
ORDER BY score_bucket;
```

---

## Next Steps

1. **Intraday Data**: Fetch 5m/15m bars around publication timestamp
2. **Beta-Adjusted Returns**: Compute expected returns using CAPM beta
3. **Transformer Sentiment**: Add FinBERT sentiment as parallel signal
4. **Auto-Tuning**: Implement gradient descent for optimal layer weights
5. **Real-Time Alerts**: WebSocket integration for sub-second latency
6. **Portfolio Backtester**: Simulate trading strategies based on signals

---

## References

- Event Study Methodology: MacKinlay (1997)
- Abnormal Returns: Fama-French Factor Models
- Market Microstructure: Hasbrouck (2007)
- News Impact: Tetlock (2007), Loughran-McDonald (2011)
