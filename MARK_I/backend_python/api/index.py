"""
Vercel serverless handler for PAM API - Ultra minimal version
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Parse the URL
        parsed_path = urlparse(self.path)
        
        # Set common headers
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
        
        # Route handling
        if parsed_path.path == '/':
            response = {
                "message": "PAM API is running on Vercel!", 
                "status": "healthy",
                "environment": "vercel"
            }
        elif parsed_path.path == '/health':
            response = {
                "status": "healthy", 
                "environment": "vercel",
                "service": "pam-api"
            }
        else:
            response = {
                "error": "Not found",
                "path": parsed_path.path
            }
        
        # Send response
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        # Handle POST requests
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
        
        response = {
            "message": "POST endpoint available",
            "status": "success"
        }
        
        self.wfile.write(json.dumps(response).encode())
    
    def do_OPTIONS(self):
        # Handle preflight requests
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()
