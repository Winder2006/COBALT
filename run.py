#!/usr/bin/env python3
"""
Startup script with error handling for Railway deployment.
"""
import sys
import os
import traceback

print("=" * 50)
print("COBALT AI Due Diligence - Starting")
print("=" * 50)
print(f"Python: {sys.version}")
print(f"Working dir: {os.getcwd()}")
print(f"PORT env: {os.environ.get('PORT', 'not set')}")
print("=" * 50)

try:
    print("Importing Flask...")
    from flask import Flask
    print("Flask OK")
    
    print("Importing other dependencies...")
    from dotenv import load_dotenv
    print("dotenv OK")
    
    from openai import OpenAI
    print("openai OK")
    
    print("Loading main app...")
    from main import app
    print("Main app loaded!")
    
    # Get port
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting on port {port}...")
    
    # Start Flask
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
    
except Exception as e:
    print("=" * 50)
    print("STARTUP ERROR!")
    print("=" * 50)
    print(f"Error type: {type(e).__name__}")
    print(f"Error message: {e}")
    print("Full traceback:")
    traceback.print_exc()
    print("=" * 50)
    sys.exit(1)
