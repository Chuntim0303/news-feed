# News Scoring Model

A composite scoring system that determines the **impact significance** of each news article before deciding whether to send an alert. Instead of alerting on every keyword match, articles are scored across multiple dimensions and only high-scoring articles trigger notifications.

## Table of Contents

- [Score Overview](#score-overview)
- [Layer 1: Keyword Event Score](#layer-1-keyword-event-score)
- [Layer 2: Market Cap Multiplier](#layer-2-market-cap-multiplier)
- [Layer 3: Surprise Score (Hidden Alpha)](#layer-3-surprise-score-hidden-alpha)
- [Layer 4: Market Reaction Score (Confirmation Layer)](#layer-4-market-reaction-score-confirmation-layer)
- [Final Score Calculation](#final-score-calculation)
- [Alert Thresholds](#alert-thresholds)
- [Examples](#examples)
- [Database Schema](#database-schema)
- [Implementation Status](#implementation-status)

---

## Score Overview

```
Final Score = (Sum of Keyword Event Scores) × Market Cap Multiplier + Surprise Score + Market Reaction Score
```

| Layer | Range | Source | Status |
|---|---|---|---|
| Keyword Event Score | 1–10 per keyword | User-assigned per keyword | ✅ Implemented |
| Market Cap Multiplier | ×1.0 – ×1.6 | Company market cap from DB | ✅ Implemented |
| Surprise Score | 0–5 | NLP phrase detection | ✅ Implemented |
| Market Reaction Score | 0–5 | Volume, gap, social signals | 📋 Planned |

---

## Layer 1: Keyword Event Score

Each keyword in `alert_keywords` has an `event_score` column (integer, 1–10) that represents how significant that keyword is to the user.

| Score | Meaning | Example Keywords |
|---|---|---|
| 1–2 | Low interest / background noise | `pharma`, `biotech` |
| 3–4 | Moderate interest | `clinical trial`, `pipeline` |
| 5–6 | Notable event | `FDA`, `approval`, `acquisition` |
| 7–8 | High-impact event | `breakthrough`, `phase 3 results` |
| 9–10 | Critical / urgent | `recall`, `fraud`, `CEO arrested` |

**Default:** New keywords are assigned `event_score = 5` unless specified.

**Telegram usage:**
```
/add pfizer 8        → adds "pfizer" with event_score = 8
/add ozempic          → adds "ozempic" with default event_score = 5
/score pfizer 9      → updates "pfizer" event_score to 9
```

When multiple keywords match a single article, their event scores are **summed**:
```
Article: "Pfizer receives FDA breakthrough designation for cancer drug"
Matched: pfizer (8) + FDA (6) + breakthrough (7)
Keyword Score = 8 + 6 + 7 = 21
```

---

## Layer 2: Market Cap Multiplier

Smaller companies have outsized price reactions to news. The market cap multiplier amplifies scores for small/mid-cap stocks.

| Market Cap | Multiplier | Rationale |
|---|---|---|
| < $1B (micro/small cap) | ×1.6 | News moves these stocks significantly |
| $1B – $5B (small cap) | ×1.3 | Moderate price sensitivity |
| $5B – $20B (mid cap) | ×1.1 | Some amplification |
| > $20B (large cap) | ×1.0 | No amplification (baseline) |
| Unknown | ×1.0 | Default when market cap unavailable |

**How it works:**
1. When tickers are extracted from an article, the system looks up `market_cap` from the `companies` table.
2. If multiple tickers are found, the **smallest market cap** is used (most price-sensitive company drives the multiplier).
3. The multiplier is applied to the keyword event score sum.

```
Keyword Score = 21
Smallest company market cap = $800M → multiplier = 1.6
Adjusted Score = 21 × 1.6 = 33.6
```

**Updating market cap:**
Market cap values are stored in the `companies` table (`market_cap_usd` column, BIGINT in dollars). They can be:
- Seeded manually via SQL or import script
- Updated periodically via API (future enhancement)

---

## Layer 3: Surprise Score (Hidden Alpha)

Detects language in the article that signals **unexpected** or **better/worse than expected** outcomes. These phrases indicate the news contains information the market hasn't priced in yet — the "hidden alpha."

### Positive Surprise Phrases (+1 to +3 each)

| Phrase | Score | Category |
|---|---|---|
| `unexpected` | +2 | Surprise |
| `better than expected` | +2 | Beat expectations |
| `exceeded expectations` | +2 | Beat expectations |
| `strong efficacy` | +2 | Clinical strength |
| `statistically significant improvement` | +3 | Clinical proof |
| `breakthrough` | +2 | Major advance |
| `first-in-class` | +2 | Novel mechanism |
| `accelerated approval` | +2 | Regulatory fast-track |
| `beat estimates` | +2 | Earnings surprise |
| `raised guidance` | +2 | Forward outlook |
| `blew past` | +2 | Strong beat |
| `outperformed` | +1 | Relative strength |
| `record revenue` | +2 | Financial milestone |
| `ahead of schedule` | +1 | Execution speed |
| `positive data` | +1 | Clinical signal |
| `exceeded primary endpoint` | +3 | Clinical proof |
| `superior to` | +2 | Head-to-head win |

### Negative Surprise Phrases (+1 to +3 each)

Negative surprises are equally important — they signal potential downside.

| Phrase | Score | Category |
|---|---|---|
| `worse than expected` | +2 | Miss expectations |
| `missed estimates` | +2 | Earnings miss |
| `failed to meet` | +2 | Clinical failure |
| `clinical hold` | +3 | Regulatory stop |
| `safety concern` | +2 | Risk signal |
| `adverse event` | +2 | Safety issue |
| `recall` | +2 | Product issue |
| `downgraded` | +1 | Analyst action |
| `lowered guidance` | +2 | Forward outlook |
| `disappointing` | +1 | Negative tone |
| `terminated` | +2 | Program end |
| `suspended` | +2 | Halt |
| `did not achieve` | +2 | Clinical failure |
| `complete response letter` | +3 | FDA rejection |
| `warning letter` | +2 | Regulatory action |

### Scoring Rules

- Surprise score is **additive** — multiple phrases in one article stack.
- Maximum surprise score is **capped at 5** to prevent runaway scores.
- Both positive and negative surprises increase the score (both are alpha signals).
- The surprise **direction** (positive/negative) is stored separately for display purposes.

```
Article: "Novo Nordisk's obesity drug shows unexpected strong efficacy,
          exceeded primary endpoint in Phase 3 trial"

Surprise phrases found:
  "unexpected"                    → +2
  "strong efficacy"               → +2
  "exceeded primary endpoint"     → +3

Raw surprise = 7, capped at 5
Surprise Score = 5 (direction: positive)
```

---

## Layer 4: Market Reaction Score (Confirmation Layer)

> **Status: 📋 PLANNED — Not yet implemented**

This layer confirms whether the market is actually reacting to the news. It avoids false positives where news *sounds* important but the market shrugs it off.

### Signals

| Signal | Score | Detection Method |
|---|---|---|
| Volume > 3× daily average | +2 | Compare current volume to 20-day avg via Twelve Data API |
| Pre-market gap > 5% | +2 | Compare pre-market price to previous close |
| Trending ticker mentions | +1 | Track ticker mention frequency across ingested articles |

### How It Will Work (Future)

1. After an article is scored (Layers 1–3), if the score exceeds a minimum threshold, the system will check market reaction signals.
2. Market data is fetched from the Twelve Data API (already integrated for price snapshots).
3. The reaction score is added to the final score.
4. This layer runs **asynchronously** — the initial alert fires based on Layers 1–3, and a follow-up message is sent if market reaction confirms the signal.

### Implementation Plan

```
Phase 1: Volume spike detection
  - Fetch 20-day average volume for the ticker
  - Compare to current day's volume
  - If volume > 3× average → +2

Phase 2: Pre-market gap detection
  - Fetch previous close and current pre-market price
  - If gap > 5% → +2

Phase 3: Trending ticker detection
  - Count how many articles mention the same ticker in the last 24h
  - If mentions > 3× normal frequency → +1
```

### Example (Future)

```
Article about MRNA scores 12.5 from Layers 1–3.
Market reaction check:
  Volume: 5.2× average → +2
  Pre-market gap: +7.3% → +2
  Trending mentions: 2× normal → +0

Market Reaction Score = 4
Final Score = 12.5 + 4 = 16.5
```

---

## Final Score Calculation

```
keyword_sum    = sum of event_score for all matched keywords
cap_multiplier = market_cap_multiplier(smallest_company_market_cap)
surprise       = min(sum of surprise phrase scores, 5)
market_rx      = market reaction score (0 when not implemented)

final_score = (keyword_sum × cap_multiplier) + surprise + market_rx
```

### Score Breakdown Example

```
Article: "Small biotech XYZ ($400M cap) reports unexpected Phase 3 success,
          exceeded primary endpoint for rare disease drug"

Layer 1 — Keyword Event Scores:
  "phase 3"     → event_score = 6
  "rare disease" → event_score = 7
  Keyword Sum = 13

Layer 2 — Market Cap Multiplier:
  XYZ market cap = $400M → ×1.6
  Adjusted = 13 × 1.6 = 20.8

Layer 3 — Surprise Score:
  "unexpected"              → +2
  "exceeded primary endpoint" → +3
  Raw = 5, cap = 5
  Surprise Score = 5

Layer 4 — Market Reaction (not yet implemented):
  Market Reaction Score = 0

Final Score = 20.8 + 5 + 0 = 25.8
```

---

## Alert Thresholds

The user's `alert_threshold` setting (stored in `bot_settings`) determines the minimum score to trigger a Telegram alert.

| Mode | Default Threshold | Behavior |
|---|---|---|
| `normal` | 5 | Most keyword matches trigger alerts |
| `quiet` | 10 | Only significant events trigger alerts |
| Custom | User-defined via `/threshold N` | Full control |

**Threshold logic:**
```python
if final_score >= user_threshold:
    send_alert(article, score_breakdown)
else:
    log_silently(article, score_breakdown)  # still stored in alert_log
```

All scored articles are logged to `alert_log` regardless of whether an alert is sent. This allows:
- Reviewing missed alerts via `/why`
- Tuning thresholds based on historical data
- Analyzing score distributions

---

## Examples

### Example 1: Low-score article (no alert in quiet mode)

```
Article: "Pfizer announces new partnership with university"

Keywords matched: pfizer (event_score=5)
Market cap: $150B → ×1.0
Surprise phrases: none
Final Score = (5 × 1.0) + 0 = 5.0

Threshold (quiet mode) = 10 → NO ALERT (logged silently)
Threshold (normal mode) = 5 → ALERT SENT
```

### Example 2: High-score article (always alerts)

```
Article: "Moderna vaccine shows unexpected statistically significant improvement
          over competitor in Phase 3 trial"

Keywords matched: moderna (8) + phase 3 (6) + vaccine (4)
Keyword sum = 18
Market cap: $45B → ×1.0
Surprise: "unexpected" (+2) + "statistically significant improvement" (+3) = 5 (capped)
Final Score = (18 × 1.0) + 5 = 23.0

Threshold (quiet mode) = 10 → ALERT SENT
```

### Example 3: Small-cap amplification

```
Article: "Ardelyx receives FDA approval for new kidney disease treatment"

Keywords matched: FDA (6) + approval (7)
Keyword sum = 13
Market cap: $1.2B → ×1.3
Surprise: none
Final Score = (13 × 1.3) + 0 = 16.9

Threshold (quiet mode) = 10 → ALERT SENT
```

---

## Database Schema

### Modified Tables

**alert_keywords** — added `event_score`:
```sql
ALTER TABLE alert_keywords
ADD COLUMN event_score TINYINT UNSIGNED NOT NULL DEFAULT 5
    COMMENT 'Impact score 1-10, used in news scoring model';
```

**companies** — added `market_cap_usd`:
```sql
ALTER TABLE companies
ADD COLUMN market_cap_usd BIGINT UNSIGNED DEFAULT NULL
    COMMENT 'Market capitalization in USD';
```

**alert_log** — added score breakdown columns:
```sql
ALTER TABLE alert_log
ADD COLUMN score_total     DECIMAL(6,2) DEFAULT NULL COMMENT 'Final composite score',
ADD COLUMN score_keyword   DECIMAL(6,2) DEFAULT NULL COMMENT 'Sum of keyword event scores',
ADD COLUMN score_cap_mult  DECIMAL(4,2) DEFAULT NULL COMMENT 'Market cap multiplier applied',
ADD COLUMN score_surprise  DECIMAL(4,2) DEFAULT NULL COMMENT 'Surprise phrase score (0-5)',
ADD COLUMN surprise_dir    ENUM('positive','negative','mixed','none') DEFAULT 'none',
ADD COLUMN alert_sent      TINYINT(1) NOT NULL DEFAULT 1 COMMENT '1=alert sent, 0=below threshold';
```

See `migrations/008_add_news_scoring.sql` for the full migration.

---

## Implementation Status

| Component | Status | File |
|---|---|---|
| Scoring model documentation | ✅ Done | `NEWS_SCORING_MODEL.md` |
| Migration (event_score, market_cap, score columns) | ✅ Done | `migrations/008_add_news_scoring.sql` |
| News scoring service | ✅ Done | `aws-lambda/services/news_scoring_service.py` |
| Company extractor (market cap) | ✅ Done | `aws-lambda/services/company_extractor.py` |
| Keyword alert service (score integration) | ✅ Done | `aws-lambda/services/keyword_alert_service.py` |
| Bot `/why` command (score breakdown) | ✅ Done | `aws-lambda-telegram-bot/bot_handlers.py` |
| Market Reaction Score (Layer 4) | 📋 Planned | — |
