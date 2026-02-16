# Stock Impact Analysis Backend API

Python 3.12 Lambda function providing REST API endpoints for the frontend dashboard.

## Debugging Guide

### Step 1: Check Database

First, verify your database has data and all tables exist:

```bash
cd aws-lambda-frontend
python check_database.py
```

This will show:
- ✓ Which tables exist and row counts
- ✓ Sample data from key tables
- ✗ Any missing tables or connection issues

### Step 2: Test Lambda Function Locally

Test the Lambda function without deploying:

```bash
python test_local.py
```

This will test all endpoints and show:
- Database connection status
- Query execution results
- Response data

### Step 3: Run Local Development Server

Start a local Flask server that simulates API Gateway:

```bash
# Install dependencies first
pip install -r requirements.txt

# Set your database password (if needed)
set DB_PASSWORD=your_password

# Start server
python local_server.py
```

Server will run at `http://localhost:3000`

Test endpoints:
- `http://localhost:3000/articles?start_date=2024-01-01&end_date=2024-12-31&min_score=0`
- `http://localhost:3000/processing-status`
- `http://localhost:3000/score-distribution`
- `http://localhost:3000/ticker-performance`
- `http://localhost:3000/health`

### Step 4: Update Frontend .env

Point your frontend to the local server:

```bash
# In news-feed/.env
VITE_API_URL=http://localhost:3000
```

Then restart your frontend:

```bash
npm run dev
```

## Common Issues

### No Data Displayed

**Cause 1: Empty database tables**
- Run migration: `migrations/009_add_multi_horizon_returns.sql`
- Check if `article_return_windows` table has data
- Run `check_database.py` to verify

**Cause 2: No articles with scores**
- Check if `alert_log` table has entries
- Verify articles have `score_total >= min_score`

**Cause 3: API Gateway not configured**
- If deployed to AWS, ensure API Gateway routes are set up
- Check CORS configuration
- Verify Lambda has database access (VPC/Security Groups)

**Cause 4: Frontend API URL misconfigured**
- Check `.env` file has correct `VITE_API_URL`
- For local: `http://localhost:3000`
- For AWS: Your API Gateway URL

### Database Connection Errors

Check environment variables:
```bash
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=news_feed
DB_PORT=3306
```

### CORS Errors

If testing with deployed Lambda:
- Ensure API Gateway has CORS enabled
- Check `OPTIONS` method is configured for all routes
- Verify `Access-Control-Allow-Origin: *` in responses

## API Endpoints

All endpoints return JSON with this structure:
```json
{
  "status": "success",
  "count": 10,
  "data": [...]
}
```

### GET /articles
Query params:
- `start_date` (YYYY-MM-DD, default: 30 days ago)
- `end_date` (YYYY-MM-DD, default: today)
- `min_score` (number, default: 5.0)
- `ticker` (string, optional)
- `limit` (number, default: 100)

### GET /alpha-candidates
Query params:
- `date` (YYYY-MM-DD, default: yesterday)
- `min_score` (number, default: 15.0)
- `min_abnormal_return` (number, default: 3.0)
- `limit` (number, default: 10)

### GET /backtest-results
Query params:
- `limit` (number, default: 10)

### GET /processing-status
No params required

### GET /score-distribution
Query params:
- `start_date` (YYYY-MM-DD, default: 30 days ago)
- `end_date` (YYYY-MM-DD, default: today)

### GET /ticker-performance
Query params:
- `start_date` (YYYY-MM-DD, default: 30 days ago)
- `end_date` (YYYY-MM-DD, default: today)
- `limit` (number, default: 20)

## Deployment

### AWS Lambda

1. Package dependencies:
```bash
pip install -r requirements.txt -t package/
cp lambda_function.py package/
cd package && zip -r ../lambda.zip . && cd ..
```

2. Upload to Lambda
3. Set environment variables in Lambda console
4. Configure API Gateway routes
5. Enable CORS on API Gateway

## Debug Logs

All endpoints include `[DEBUG]` logging:
- Database connection details
- Query parameters
- Row counts returned
- Sample data structure

Check CloudWatch Logs (AWS) or console output (local) for debug information.
