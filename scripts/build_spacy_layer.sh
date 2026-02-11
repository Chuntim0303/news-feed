#!/bin/bash
# =============================================================================
# Build spaCy Lambda Layer using AWS CloudShell
# =============================================================================
# 
# Instructions:
# 1. Open AWS CloudShell (https://console.aws.amazon.com/cloudshell)
# 2. Copy and paste this entire script into CloudShell
# 3. Wait for it to complete (~2-3 minutes)
# 4. Download the layer zip or it will be published directly to Lambda
#
# Target: Python 3.12, x86_64 (Amazon Linux 2023)
# =============================================================================

set -e

echo "============================================="
echo "Building spaCy Lambda Layer for Python 3.12"
echo "============================================="

# Clean up any previous build
rm -rf /tmp/spacy-layer
mkdir -p /tmp/spacy-layer/python

# Install spaCy and the small English model into the layer directory
# --platform ensures we get Linux x86_64 binaries
pip install \
    spacy==3.7.2 \
    --target /tmp/spacy-layer/python \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --no-cache-dir

echo ""
echo "Installing en_core_web_sm model..."

# Download and install the spaCy model
pip install \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl \
    --target /tmp/spacy-layer/python \
    --no-deps \
    --no-cache-dir

echo ""
echo "Cleaning up unnecessary files to reduce size..."

# Remove unnecessary files to shrink the layer
cd /tmp/spacy-layer/python
rm -rf __pycache__
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Show size
echo ""
LAYER_SIZE=$(du -sh /tmp/spacy-layer/python | cut -f1)
echo "Layer size: $LAYER_SIZE"

# Package the layer
echo ""
echo "Creating zip file..."
cd /tmp/spacy-layer
zip -r9 -q /tmp/spacy-lambda-layer.zip python/

ZIP_SIZE=$(du -sh /tmp/spacy-lambda-layer.zip | cut -f1)
echo "Zip size: $ZIP_SIZE"

# Publish the layer to AWS Lambda
echo ""
echo "Publishing Lambda Layer..."
LAYER_ARN=$(aws lambda publish-layer-version \
    --layer-name spacy-en-core-web-sm \
    --description "spaCy 3.7.2 + en_core_web_sm model for Python 3.12" \
    --zip-file fileb:///tmp/spacy-lambda-layer.zip \
    --compatible-runtimes python3.12 \
    --compatible-architectures x86_64 \
    --query 'LayerVersionArn' \
    --output text)

echo ""
echo "============================================="
echo "SUCCESS! Layer published."
echo "============================================="
echo ""
echo "Layer ARN: $LAYER_ARN"
echo ""
echo "To attach to your Lambda function, run:"
echo "  aws lambda update-function-configuration \\"
echo "    --function-name rss-feed-tracker \\"
echo "    --layers $LAYER_ARN"
echo ""
echo "============================================="

# Cleanup
rm -rf /tmp/spacy-layer
echo "Done. Temp files cleaned up."
