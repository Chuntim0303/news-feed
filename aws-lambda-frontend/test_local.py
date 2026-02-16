"""
Local test script for the Lambda function
Run this to test the API locally before deploying
"""

import os
import sys
from lambda_function import lambda_handler

# Set environment variables for local testing
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_USER'] = 'root'
os.environ['DB_PASSWORD'] = ''  # Set your password
os.environ['DB_NAME'] = 'news_feed'
os.environ['DB_PORT'] = '3306'

def test_endpoint(path, params=None):
    """Test an API endpoint locally."""
    event = {
        'httpMethod': 'GET',
        'path': path,
        'queryStringParameters': params or {}
    }
    
    print(f"\n{'='*60}")
    print(f"Testing: GET {path}")
    print(f"Params: {params}")
    print('='*60)
    
    try:
        response = lambda_handler(event, None)
        print(f"Status Code: {response['statusCode']}")
        print(f"Response Body: {response['body'][:500]}...")  # First 500 chars
        return response
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    print("Testing Lambda Function Locally")
    print("="*60)
    
    # Test 1: Articles endpoint
    print("\n1. Testing /articles endpoint")
    test_endpoint('/articles', {
        'start_date': '2024-01-01',
        'end_date': '2024-12-31',
        'min_score': '0',
        'limit': '10'
    })
    
    # Test 2: Processing status
    print("\n2. Testing /processing-status endpoint")
    test_endpoint('/processing-status')
    
    # Test 3: Score distribution
    print("\n3. Testing /score-distribution endpoint")
    test_endpoint('/score-distribution', {
        'start_date': '2024-01-01',
        'end_date': '2024-12-31'
    })
    
    # Test 4: Ticker performance
    print("\n4. Testing /ticker-performance endpoint")
    test_endpoint('/ticker-performance', {
        'start_date': '2024-01-01',
        'end_date': '2024-12-31',
        'limit': '10'
    })
    
    print("\n" + "="*60)
    print("Testing complete!")
