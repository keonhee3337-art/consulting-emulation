#!/bin/bash
# FinAgent AWS Lambda Deployment Script
# Prerequisites: AWS CLI configured (aws configure), SAM CLI installed, Python 3.11
#
# First-time run: ./deploy.sh --guided
# Subsequent runs: ./deploy.sh
#
# Run from the deploy/ directory.

set -e

FINAGENT_DIR="../../../FinAgent"
PACKAGE_DIR="./package"
STACK_NAME="finagent-prod"
REGION="ap-northeast-2"   # Seoul — change if needed

echo "=== FinAgent Lambda Deploy ==="
echo "Region: $REGION | Stack: $STACK_NAME"
echo ""

# ---- Step 1: Install Python dependencies into package/ ----
echo "Step 1: Installing dependencies into $PACKAGE_DIR ..."
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

# Install from FinAgent requirements.txt
pip install -r "$FINAGENT_DIR/requirements.txt" -t "$PACKAGE_DIR/" --upgrade --quiet

# Install Mangum (ASGI adapter for Lambda — not in FinAgent requirements)
pip install mangum -t "$PACKAGE_DIR/" --quiet

echo "  Done. Package size: $(du -sh $PACKAGE_DIR | cut -f1)"

# ---- Step 2: Copy application files into package/ ----
echo ""
echo "Step 2: Copying app files ..."

cp -r "$FINAGENT_DIR/agent" "$PACKAGE_DIR/"
cp "$FINAGENT_DIR/api.py" "$PACKAGE_DIR/"

# Copy data directory (SQLite DB + vector store JSON)
if [ -d "$FINAGENT_DIR/data" ]; then
  cp -r "$FINAGENT_DIR/data" "$PACKAGE_DIR/"
  echo "  Copied data/ (SQLite + vector store)"
else
  echo "  Warning: $FINAGENT_DIR/data not found — copy manually if needed"
fi

# Copy Lambda handler
cp lambda_handler.py "$PACKAGE_DIR/"

echo "  Done."

# ---- Step 3: Check package size ----
echo ""
echo "Step 3: Checking package size ..."
PACKAGE_SIZE_MB=$(du -sm "$PACKAGE_DIR" | cut -f1)
echo "  Package size: ${PACKAGE_SIZE_MB}MB"
if [ "$PACKAGE_SIZE_MB" -gt 200 ]; then
  echo "  WARNING: Package is ${PACKAGE_SIZE_MB}MB — Lambda limit is 250MB unzipped."
  echo "  If deploy fails, move heavy packages (numpy, pandas) to a Lambda Layer."
  echo "  See README.md section: 'If package exceeds 250MB'"
fi

# ---- Step 4: SAM build ----
echo ""
echo "Step 4: SAM build ..."
sam build --template template.yaml

# ---- Step 5: SAM deploy ----
echo ""
echo "Step 5: SAM deploy ..."
if [ "$1" == "--guided" ]; then
  echo "  Running guided deploy (first time setup) ..."
  sam deploy --guided --stack-name "$STACK_NAME" --region "$REGION"
else
  echo "  Running non-interactive deploy ..."
  sam deploy --stack-name "$STACK_NAME" --region "$REGION" --no-confirm-changeset
fi

echo ""
echo "=== Deploy complete. ==="
echo "Copy the ApiUrl from the output above and set it as API_URL in your Streamlit app."
echo "Test: curl https://[api-id].execute-api.$REGION.amazonaws.com/health"
