# AWS Lambda — Telegram Bot Interface

A full-featured Telegram bot for the RSS news feed system. Manage keyword alerts, query articles, view price impact, and configure settings — all from Telegram.

## Commands

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
| `/latest <ticker\|source>` | Latest for a ticker or source | `/latest AAPL` |
| `/search <query>` | Search articles by keyword | `/search ozempic` |
| `/why` | Explain last alert with full score breakdown | `/why` |
| `/why <id>` | Explain a specific article alert | `/why 1234` |
| `/summary [Nd] [TICKER]` | Digest summary for a period/ticker | `/summary 1d NVO` |
| `/top [Nd]` | Top movers by price impact | `/top 7d` |

### Settings

| Command | Description | Example |
|---|---|---|
| `/settings` | Show current preferences | `/settings` |
| `/mode quiet\|normal` | Alert mode (quiet = score ≥ 10 only) | `/mode quiet` |
| `/threshold N` | Min news score to trigger alert | `/threshold 6` |
| `/sources <name> on\|off` | Enable/disable a feed source | `/sources bloomberg off` |
| `/digest <type> on\|off` | Toggle morning/eod/weekly digest | `/digest morning off` |

### News Scoring Model

Articles are scored using a composite model instead of alerting on every keyword match:

```
Final Score = (Sum of Keyword Event Scores) × Market Cap Multiplier + Surprise Score
```

- **Keyword Event Score** (1-10 per keyword): User-assigned importance
- **Market Cap Multiplier**: <$1B → ×1.6, $1B-5B → ×1.3, $5B-20B → ×1.1, >$20B → ×1.0
- **Surprise Score** (0-5): Detects phrases like "unexpected", "exceeded expectations", "clinical hold"

Alerts are only sent when the final score ≥ your threshold. All matches are logged regardless.

See `NEWS_SCORING_MODEL.md` for full documentation.

## Architecture

```
Telegram User
    │
    ▼
Telegram Bot API
    │
    ▼
API Gateway (POST /webhook)
    │
    ▼
aws-lambda-telegram-bot (this Lambda)
    │
    ▼
MySQL Database (alert_keywords table)
```

## Prerequisites

1. **Telegram Bot Token** — Create a bot via [@BotFather](https://t.me/BotFather)
2. **MySQL Database** — With migration `006_create_alert_keywords_table.sql` applied
3. **AWS Account** — With permissions to create Lambda, API Gateway, and IAM roles

## Setup Steps

### Step 1: Run the Database Migration

Apply the migration to create the `alert_keywords` and `alert_log` tables:

```sql
-- Connect to your MySQL database and run:
SOURCE migrations/006_create_alert_keywords_table.sql;
```

Or via command line:

```bash
mysql -u <DB_USER> -p <DB_NAME> < migrations/006_create_alert_keywords_table.sql
```

### Step 2: Create the Lambda Function

#### Option A: AWS Console

1. Go to **AWS Lambda** → **Create function**
2. Settings:
   - **Function name:** `news-feed-telegram-bot`
   - **Runtime:** Python 3.12
   - **Architecture:** x86_64
3. Upload the deployment package (see [Build & Package](#step-3-build--package) below)

#### Option B: AWS CLI

```bash
aws lambda create-function \
  --function-name news-feed-telegram-bot \
  --runtime python3.12 \
  --handler lambda_function.lambda_handler \
  --role arn:aws:iam::<ACCOUNT_ID>:role/<LAMBDA_ROLE> \
  --zip-file fileb://telegram-bot-package.zip \
  --timeout 10 \
  --memory-size 128
```

### Step 3: Build & Package

```bash
# Create a clean package directory
mkdir -p package
cd package

# Install dependencies
pip install pymysql -t .

# Copy the Lambda function
cp ../lambda_function.py .

# Create the zip
zip -r ../telegram-bot-package.zip .

cd ..
rm -rf package
```

### Step 4: Set Environment Variables

In the Lambda console → **Configuration** → **Environment variables**, add:

| Variable | Value | Required |
|---|---|---|
| `DB_HOST` | Your MySQL host | ✅ |
| `DB_USER` | Your MySQL user | ✅ |
| `DB_PASSWORD` | Your MySQL password | ✅ |
| `DB_NAME` | Your MySQL database name | ✅ |
| `DB_PORT` | MySQL port (default: 3306) | ✅ |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | ✅ |
| `TELEGRAM_CHAT_ID` | Your chat ID (restricts access) | Optional |

> **Security tip:** Use AWS Secrets Manager or SSM Parameter Store for sensitive values like `DB_PASSWORD` and `TELEGRAM_BOT_TOKEN` in production.

### Step 5: Create API Gateway

1. Go to **API Gateway** → **Create API** → **HTTP API**
2. Click **Add integration** → **Lambda** → select `news-feed-telegram-bot`
3. **API name:** `news-feed-telegram-bot-api`
4. Click **Next**
5. Configure route:
   - **Method:** POST
   - **Resource path:** `/webhook`
6. Click **Next** → **Next** → **Create**
7. Copy the **Invoke URL** (e.g., `https://abc123.execute-api.us-east-1.amazonaws.com`)

### Step 6: Register the Telegram Webhook

Tell Telegram to send bot messages to your API Gateway endpoint:

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://<API_GATEWAY_URL>/webhook"}'
```

Expected response:

```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

#### Verify the webhook is set:

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

### Step 7: Test It

1. Open your Telegram bot chat
2. Send `/help` — you should see the command list
3. Send `/add pfizer` — keyword is saved to the database
4. Send `/list` — confirms "pfizer" is active

## How to Find Your Chat ID

If you want to restrict the bot to your chat only (recommended), you need your `TELEGRAM_CHAT_ID`:

1. Send any message to your bot
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Look for `"chat": {"id": 123456789}` in the response
4. Set `TELEGRAM_CHAT_ID=123456789` in the Lambda environment variables

## Troubleshooting

### Bot doesn't respond

- Check CloudWatch Logs for the Lambda function
- Verify the webhook is set: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
- Ensure the API Gateway route is `POST /webhook`
- Check that the Lambda has network access to your MySQL database (VPC/security group settings)

### "Unauthorized" response

- The `TELEGRAM_CHAT_ID` environment variable is set and your chat ID doesn't match
- Remove `TELEGRAM_CHAT_ID` to allow any chat, or set it to your actual chat ID

### Database connection errors

- Ensure the Lambda is in the same VPC as your database (or the database is publicly accessible)
- Check security group inbound rules allow the Lambda's IP/subnet on port 3306
- Verify `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` are correct

### Webhook errors

To remove a webhook and switch back to polling (for debugging):

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/deleteWebhook"
```

## Database Migrations

Run these migrations **in order** before deploying:

```bash
# Keywords & alert log (required)
mysql -u <DB_USER> -p <DB_NAME> < migrations/006_create_alert_keywords_table.sql

# Bot settings & source preferences (required for /settings, /mode, /threshold, etc.)
mysql -u <DB_USER> -p <DB_NAME> < migrations/007_create_bot_settings_table.sql
```

## File Structure

```
aws-lambda-telegram-bot/
├── README.md              ← This file
├── lambda_function.py     ← Lambda handler, command routing, Telegram messaging
└── bot_handlers.py        ← All command handler logic (keywords, queries, settings)
```

## Related Components

| Component | Description |
|---|---|
| `aws-lambda/` | RSS feed ingestion — checks new articles against keywords |
| `aws-lambda-daily/` | Daily stock price fetch and analysis |
| `migrations/006_create_alert_keywords_table.sql` | Database migration for keyword tables |
| `aws-lambda/services/keyword_alert_service.py` | Service that matches articles to keywords and sends alerts |
