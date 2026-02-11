# Create fpdf2 Lambda Layer using AWS CloudShell

This guide documents how to build and publish a Lambda Layer containing **fpdf2 2.8.1** for **Python 3.12 (x86_64)**. This layer is required for the `send_report` action (PDF generation + Telegram delivery).

## Prerequisites

- AWS account with Lambda and S3 permissions
- Access to [AWS CloudShell](https://console.aws.amazon.com/cloudshell) (region: `ap-southeast-1`)

## Steps

### 1. Reset to a valid folder

```bash
cd ~
pwd
```

### 2. Create the layer folder

```bash
rm -rf /tmp/fpdf2-layer
mkdir -p /tmp/fpdf2-layer/python
```

### 3. Install fpdf2

```bash
pip install fpdf2==2.8.1 \
  --target /tmp/fpdf2-layer/python \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --no-cache-dir
```

> **Note:** If the above fails because fpdf2 is pure Python (no binary wheels with platform tag), use this instead:
>
> ```bash
> pip install fpdf2==2.8.1 \
>   --target /tmp/fpdf2-layer/python \
>   --no-cache-dir
> ```

### 4. Zip the layer

```bash
cd /tmp/fpdf2-layer
zip -r9 /tmp/fpdf2-python312.zip python
ls -lh /tmp/fpdf2-python312.zip
```

> The zip should be around **1-2MB** (fpdf2 is lightweight).

### 5. Upload to S3 and publish the layer

Set the region and create an S3 bucket name:

```bash
export AWS_DEFAULT_REGION=ap-southeast-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="lambda-layers-$ACCOUNT_ID-ap-southeast-1"
```

> **Note:** If the S3 bucket doesn't exist yet, create it first:
> ```bash
> aws s3 mb s3://$BUCKET --region ap-southeast-1
> ```

Upload the zip to S3:

```bash
aws s3 cp /tmp/fpdf2-python312.zip \
  s3://$BUCKET/layers/fpdf2-python312.zip
```

Publish the Lambda Layer:

```bash
aws lambda publish-layer-version \
  --layer-name fpdf2-py312 \
  --description "fpdf2 2.8.1 PDF generation (Python 3.12)" \
  --content S3Bucket=$BUCKET,S3Key=layers/fpdf2-python312.zip \
  --compatible-runtimes python3.12 \
  --compatible-architectures x86_64
```

Save the **LayerVersionArn** from the output.

### 6. Attach the layer to your Lambda function

You can attach multiple layers. Include both the spaCy layer and the fpdf2 layer:

```bash
aws lambda update-function-configuration \
  --function-name rss-feed-tracker \
  --layers <SPACY_LAYER_ARN> <FPDF2_LAYER_ARN>
```

Replace `<SPACY_LAYER_ARN>` and `<FPDF2_LAYER_ARN>` with the ARNs from their respective `publish-layer-version` outputs.

> **Important:** The `--layers` flag replaces ALL layers, so always include every layer you need.

## Lambda Environment Variables

After attaching the layer, add these environment variables for the `send_report` action:

| Variable | Description | How to get it |
|----------|-------------|---------------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token | Message **@BotFather** on Telegram → `/newbot` |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | Message **@userinfobot** on Telegram |

## Verifying the Layer

Test the layer by invoking the Lambda with:

```json
{"action": "send_report"}
```

This will generate a PDF news impact report and send it to your Telegram chat.

## Troubleshooting

- **"No module named 'fpdf'"** — Layer not attached or wrong Python runtime (must be 3.12)
- **"TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set"** — Add the env vars to Lambda configuration
- **Telegram 401 error** — Bot token is invalid; regenerate via @BotFather
- **Telegram 400 "chat not found"** — Chat ID is wrong, or you haven't started a conversation with the bot yet (send `/start` to your bot first)
