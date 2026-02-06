#!/bin/bash

# RSS Feed Tracker - AWS Lambda Deployment Script
# This script creates a deployment package and deploys to AWS Lambda

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
FUNCTION_NAME="${FUNCTION_NAME:-rss-feed-tracker}"
RUNTIME="${RUNTIME:-python3.9}"
HANDLER="lambda_function.lambda_handler"
TIMEOUT="${TIMEOUT:-300}"
MEMORY="${MEMORY:-512}"

echo -e "${GREEN}RSS Feed Tracker - Lambda Deployment${NC}"
echo "======================================="
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    echo "Please install AWS CLI: https://aws.amazon.com/cli/"
    exit 1
fi

# Check if required environment variables are set
if [ -z "$AWS_LAMBDA_ROLE_ARN" ]; then
    echo -e "${YELLOW}Warning: AWS_LAMBDA_ROLE_ARN not set${NC}"
    echo "Please set the Lambda execution role ARN:"
    echo "export AWS_LAMBDA_ROLE_ARN=arn:aws:iam::ACCOUNT_ID:role/lambda-execution-role"
    exit 1
fi

# Clean up previous package
echo -e "${YELLOW}Cleaning up previous deployment package...${NC}"
rm -rf lambda_package
rm -f lambda_deployment.zip

# Create package directory
echo -e "${YELLOW}Creating deployment package...${NC}"
mkdir -p lambda_package

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
python3 -m pip install -r requirements.txt -t lambda_package/ --upgrade

# Verify critical dependencies were installed
MISSING_DEPS=""
for dep in feedparser pymysql dateutil; do
    if [ ! -d "lambda_package/${dep}" ] && [ ! -d "lambda_package/${dep//-/_}" ]; then
        MISSING_DEPS="${MISSING_DEPS} ${dep}"
    fi
done

if [ -n "$MISSING_DEPS" ]; then
    echo -e "${RED}Error: Failed to install dependencies:${MISSING_DEPS}${NC}"
    echo "Please check your Python/pip installation and try again."
    exit 1
fi

# Copy application code
echo -e "${YELLOW}Copying application code...${NC}"
cp -r services lambda_package/
cp lambda_function.py lambda_package/

# Clean up __pycache__ directories to reduce package size
find lambda_package/ -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Create ZIP file
echo -e "${YELLOW}Creating ZIP archive...${NC}"
cd lambda_package
zip -r ../lambda_deployment.zip . -q
cd ..

echo -e "${GREEN}Deployment package created: lambda_deployment.zip${NC}"

# Check if function exists
echo -e "${YELLOW}Checking if Lambda function exists...${NC}"
if aws lambda get-function --function-name "$FUNCTION_NAME" &> /dev/null; then
    echo -e "${YELLOW}Updating existing Lambda function...${NC}"

    # Update function code
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://lambda_deployment.zip \
        --publish

    echo -e "${GREEN}Lambda function updated successfully!${NC}"
else
    echo -e "${YELLOW}Creating new Lambda function...${NC}"

    # Prompt for database configuration
    read -p "Enter DB_HOST: " DB_HOST
    read -p "Enter DB_USER: " DB_USER
    read -sp "Enter DB_PASSWORD: " DB_PASSWORD
    echo ""
    read -p "Enter DB_NAME [news_feed]: " DB_NAME
    DB_NAME=${DB_NAME:-news_feed}
    read -p "Enter DB_PORT [3306]: " DB_PORT
    DB_PORT=${DB_PORT:-3306}

    # Create function
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --handler "$HANDLER" \
        --role "$AWS_LAMBDA_ROLE_ARN" \
        --zip-file fileb://lambda_deployment.zip \
        --timeout "$TIMEOUT" \
        --memory-size "$MEMORY" \
        --environment "Variables={DB_HOST=$DB_HOST,DB_USER=$DB_USER,DB_PASSWORD=$DB_PASSWORD,DB_NAME=$DB_NAME,DB_PORT=$DB_PORT}" \
        --publish

    echo -e "${GREEN}Lambda function created successfully!${NC}"
fi

# Get function info
echo ""
echo -e "${GREEN}Function Information:${NC}"
aws lambda get-function --function-name "$FUNCTION_NAME" --query 'Configuration.[FunctionName,Runtime,MemorySize,Timeout,LastModified]' --output table

# Test the function
echo ""
read -p "Would you like to test the function? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Testing Lambda function...${NC}"
    aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --payload '{"action": "fetch_all"}' \
        response.json

    echo -e "${GREEN}Response:${NC}"
    cat response.json | python -m json.tool
    echo ""
fi

echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "To invoke the function:"
echo "  aws lambda invoke --function-name $FUNCTION_NAME --payload '{\"action\": \"fetch_all\"}' response.json"
echo ""
echo "To view logs:"
echo "  aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
