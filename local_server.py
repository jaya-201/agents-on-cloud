import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from lambda_handler import handler

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)  # This handles CORS headers so your frontend can communicate locally

# Dummy Lambda Context
class DummyContext:
    aws_request_id = "local-dev-request-123"

@app.route('/run-agent', methods=['POST'])
def run_agent():
    """
    This endpoint mimics AWS API Gateway by wrapping the Flask request 
    into a Lambda event and passing it to your lambda_handler.
    """
    # Create an event mimicking what API Gateway sends
    event = {
        "body": request.get_json()
    }
    
    # Call your lambda handler directly
    response = handler(event, DummyContext())
    
    # Lambda returns a stringified JSON body, so we need to load it back 
    # to send it as a proper JSON response via Flask
    status_code = response.get('statusCode', 500)
    body = response.get('body', '{}')
    
    try:
        parsed_body = json.loads(body)
    except json.JSONDecodeError:
        parsed_body = body
        
    return jsonify(parsed_body), status_code

if __name__ == '__main__':
    print("🚀 Starting local dev server on http://localhost:5000")
    if not os.environ.get('GEMINI_API_KEY'):
        print("⚠️  WARNING: GEMINI_API_KEY is not set! Please add it to your .env file.")
    app.run(host='0.0.0.0', port=5000, debug=True)
