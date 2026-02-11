# Create spaCy Lambda Layer using AWS CloudShell

This guide documents how to build and publish a Lambda Layer containing **spaCy 3.7.2** and the **en_core_web_sm 3.7.1** model for **Python 3.12 (x86_64)**.

## Prerequisites

- AWS account with Lambda and S3 permissions
- Access to [AWS CloudShell](https://console.aws.amazon.com/cloudshell) (region: `ap-southeast-1`)

## Steps

### 1. Reset to a valid folder

```bash
cd ~
pwd
```

### 2. Recreate the layer folder

```bash
rm -rf /tmp/spacy-layer
mkdir -p /tmp/spacy-layer/python
```

### 3. Install spaCy + model

Install spaCy (compiled for Lambda's Linux x86_64 environment):

```bash
pip install spacy==3.7.2 \
  --target /tmp/spacy-layer/python \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --no-cache-dir
```

Install the English language model:

```bash
pip install \
  https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl \
  --target /tmp/spacy-layer/python \
  --no-deps \
  --no-cache-dir
```

### 4. Zip the layer

```bash
cd /tmp/spacy-layer
zip -r9 /tmp/spacy-python312-spacy372-en_sm.zip python
ls -lh /tmp/spacy-python312-spacy372-en_sm.zip
```

> The zip should be around **50-80MB**.

### 5. Upload to S3 and publish the layer

Set the region and create an S3 bucket name:

```bash
export AWS_DEFAULT_REGION=ap-southeast-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="spacy-layer-$ACCOUNT_ID-ap-southeast-1"
```

> **Note:** If the S3 bucket doesn't exist yet, create it first:
> ```bash
> aws s3 mb s3://$BUCKET --region ap-southeast-1
> ```

Upload the zip to S3:

```bash
aws s3 cp /tmp/spacy-python312-spacy372-en_sm.zip \
  s3://$BUCKET/layers/spacy-python312-spacy372-en_sm.zip
```

Publish the Lambda Layer:

```bash
aws lambda publish-layer-version \
  --layer-name spacy-py312 \
  --description "spaCy 3.7.2 + en_core_web_sm 3.7.1 (Python 3.12 x86_64)" \
  --content S3Bucket=$BUCKET,S3Key=layers/spacy-python312-spacy372-en_sm.zip \
  --compatible-runtimes python3.12 \
  --compatible-architectures x86_64
```

Save the **LayerVersionArn** from the output.

### 6. Attach the layer to your Lambda function

```bash
aws lambda update-function-configuration \
  --function-name rss-feed-tracker \
  --layers <LAYER_VERSION_ARN>
```

Replace `<LAYER_VERSION_ARN>` with the ARN from step 5.

## Lambda Configuration Requirements

After attaching the layer, update your Lambda function settings:

| Setting | Value | Reason |
|---------|-------|--------|
| **Memory** | 512 MB+ | spaCy loads the model into RAM (~200MB) |
| **Timeout** | 300 seconds | Stock price fetching with rate limiting can take minutes |
| **Environment variable** | `TWELVE_DATA_API_KEY` | Required for stock price fetching |

## Verifying the Layer

Test the layer by invoking the Lambda with:

```json
{
  "action": "extract_tickers",
  "params": { "limit": 5 }
}
```

This will run spaCy NER on up to 5 unprocessed articles and extract stock tickers.

## Troubleshooting

- **"No module named 'spacy'"** — Layer not attached or wrong Python runtime (must be 3.12)
- **"Model 'en_core_web_sm' not found"** — Model wasn't included in the layer zip
- **Out of memory** — Increase Lambda memory to 512MB or higher
- **Timeout** — Increase Lambda timeout; spaCy model loading takes 2-5s on cold start
- **S3 upload fails** — Ensure the bucket exists and is in the same region (`ap-southeast-1`)
