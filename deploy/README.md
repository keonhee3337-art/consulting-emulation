# FinAgent AWS Lambda Deployment

Deploys the FinAgent FastAPI backend to AWS Lambda + API Gateway using AWS SAM.
Runtime: Python 3.11 + Mangum (ASGI adapter).

---

## Prerequisites

- AWS account
- AWS CLI: `pip install awscli` — then `aws configure` (Access Key ID, Secret, region)
- SAM CLI: `pip install aws-sam-cli`
- Python 3.11 (check with `python --version`)

---

## One-Time Setup

**1. Configure AWS credentials**

```bash
aws configure
```

Enter:
- AWS Access Key ID — from IAM console → Users → Security credentials
- AWS Secret Access Key — same place
- Default region: `ap-northeast-2` (Seoul) — or `us-east-1` if no preference
- Default output format: `json`

**2. Create an S3 bucket for SAM artifacts**

SAM needs an S3 bucket to upload your deployment package. Run once:

```bash
aws s3 mb s3://finagent-deploy-keonhee --region ap-northeast-2
```

SAM will ask for this bucket name during the first guided deploy.

---

## Deploy

```bash
cd deploy/

# First time — SAM will prompt for stack name, region, S3 bucket, env vars
./deploy.sh --guided

# Subsequent runs — uses saved config (samconfig.toml)
./deploy.sh
```

First-run prompts:
- Stack name: `finagent-prod`
- Region: `ap-northeast-2`
- S3 bucket: `finagent-deploy-keonhee` (the one you created above)
- OpenAIApiKey: paste from `.env`
- SupabaseUrl / SupabaseApiKey: paste from `.env` (or leave blank if not using checkpointing)
- Confirm changes: `Y`

---

## Environment Variables

These are passed as SAM parameters and set on the Lambda function automatically.

If you need to update them after deploy, go to:
Lambda console → FinAgent function → Configuration → Environment variables

| Variable | Value |
|---|---|
| `OPENAI_API_KEY` | From FinAgent `.env` |
| `SUPABASE_URL` | `https://bnsimxodkdnfxspwntro.supabase.co` |
| `SUPABASE_API_KEY` | From FinAgent `.env` |

---

## After Deploy

The deploy output will print an `ApiUrl`. Update the Streamlit app:

1. Go to Streamlit Cloud → App settings → Secrets
2. Set `API_URL = https://[your-api-id].execute-api.ap-northeast-2.amazonaws.com/`

Test endpoints:

```bash
# Health check
curl https://[api-id].execute-api.ap-northeast-2.amazonaws.com/health

# Full pipeline query
curl -X POST https://[api-id].execute-api.ap-northeast-2.amazonaws.com/analyze \
  -H "Content-Type: application/json" \
  -d '{"query": "Samsung revenue 2023"}'
```

---

## Cost Estimate

AWS Free Tier covers this easily for a portfolio project:

| Service | Free Tier | Est. Usage |
|---|---|---|
| Lambda | 1M requests/month, 400K GB-seconds/month | ~$0 |
| API Gateway (HTTP API) | 1M requests/month for 12 months | ~$0 |
| S3 (deployment artifacts) | 5GB, 20K GET, 2K PUT | ~$0 |

After free tier: Lambda at 1024MB, 30s avg = ~$0.0005 per request. 1,000 queries/month = ~$0.50.

---

## If Package Exceeds 250MB

Lambda's unzipped deployment package limit is 250MB. FinAgent's dependencies (numpy, pandas, LangGraph) may push close to this.

**Fix: Lambda Layers for heavy packages**

```bash
# Create a layer with the heavy packages
mkdir -p layer/python
pip install numpy pandas openai -t layer/python/ --quiet
zip -r numpy-layer.zip layer/
aws lambda publish-layer-version \
  --layer-name finagent-deps \
  --zip-file fileb://numpy-layer.zip \
  --compatible-runtimes python3.11 \
  --region ap-northeast-2
```

Then add to `template.yaml` under `FinAgentFunction`:

```yaml
Layers:
  - !Sub 'arn:aws:lambda:${AWS::Region}:${AWS::AccountId}:layer:finagent-deps:1'
```

And exclude those packages from the main package in `deploy.sh`:

```bash
pip install -r requirements.txt -t ./package/ \
  --upgrade --quiet \
  --no-deps numpy pandas openai  # already in layer
```

---

## File Reference

| File | Purpose |
|---|---|
| `lambda_handler.py` | Mangum wrapper — entry point for Lambda |
| `template.yaml` | AWS SAM infrastructure definition |
| `deploy.sh` | Deployment script — run this |
| `README.md` | This file |

---

## Teardown

To delete the stack and stop all charges:

```bash
sam delete --stack-name finagent-prod --region ap-northeast-2
aws s3 rb s3://finagent-deploy-keonhee --force
```
