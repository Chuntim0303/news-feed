"""
Local development server for testing the Lambda function
Simulates API Gateway locally
"""

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from lambda_function import lambda_handler
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Set environment variables for local testing
os.environ['DB_HOST'] = os.environ.get('DB_HOST', 'localhost')
os.environ['DB_USER'] = os.environ.get('DB_USER', 'root')
os.environ['DB_PASSWORD'] = os.environ.get('DB_PASSWORD', '')
os.environ['DB_NAME'] = os.environ.get('DB_NAME', 'news_feed')
os.environ['DB_PORT'] = os.environ.get('DB_PORT', '3306')

@app.route('/<path:path>', methods=['GET', 'POST', 'OPTIONS'])
def proxy(path):
    """Proxy all requests to the Lambda handler."""
    
    # Build Lambda event from Flask request
    event = {
        'httpMethod': request.method,
        'path': f'/{path}',
        'queryStringParameters': dict(request.args) if request.args else None,
        'headers': dict(request.headers),
        'body': request.get_data(as_text=True) if request.method == 'POST' else None
    }
    
    print(f"\n[REQUEST] {request.method} /{path}")
    print(f"[PARAMS] {dict(request.args)}")
    
    # Call Lambda handler
    try:
        response = lambda_handler(event, None)
        
        # Parse Lambda response
        status_code = response.get('statusCode', 200)
        headers = response.get('headers', {})
        body = response.get('body', '{}')
        
        print(f"[RESPONSE] Status: {status_code}, Body length: {len(body)} chars")
        
        # Return Flask response
        flask_response = app.response_class(
            response=body,
            status=status_code,
            mimetype='application/json'
        )
        
        # Add headers
        for key, value in headers.items():
            flask_response.headers[key] = value
        
        return flask_response
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'Stock Impact Analysis API',
        'database': {
            'host': os.environ.get('DB_HOST'),
            'database': os.environ.get('DB_NAME')
        }
    })

if __name__ == '__main__':
    print("="*60)
    print("Starting Local Development Server")
    print("="*60)
    print(f"Database: {os.environ.get('DB_HOST')}:{os.environ.get('DB_PORT')}/{os.environ.get('DB_NAME')}")
    print(f"Server: http://localhost:3000")
    print("="*60)
    print("\nAvailable endpoints:")
    print("  GET  /articles")
    print("  GET  /alpha-candidates")
    print("  GET  /backtest-results")
    print("  GET  /processing-status")
    print("  GET  /score-distribution")
    print("  GET  /ticker-performance")
    print("  GET  /health")
    print("\n" + "="*60 + "\n")
    
    app.run(host='0.0.0.0', port=3000, debug=True)
