"""
AWS Lambda handler for FinAgent FastAPI backend.
Uses Mangum to adapt ASGI (FastAPI) to Lambda event format.

Deploy:
  1. pip install mangum
  2. Package: zip -r deployment.zip . -x "*.pyc" "__pycache__/*"
  3. Lambda config: Handler = lambda_handler.handler, Runtime = python3.11
  4. Environment variables: OPENAI_API_KEY (SUPABASE_URL and SUPABASE_API_KEY if using checkpointing)

Notes:
  - SQLite DB and vector store are bundled in the package (read-only at Lambda runtime)
  - Lambda /tmp (512MB) is writable if you need to write at runtime
  - Heavy packages (numpy, pandas) may push you near the 250MB limit — see README for Lambda layers fix
"""

import sys
import os

# Ensure the package directory is on the path when running in Lambda
sys.path.insert(0, os.path.dirname(__file__))

from mangum import Mangum
from api import app  # FinAgent FastAPI app

handler = Mangum(app, lifespan="off")
