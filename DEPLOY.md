# Deploying to Google Cloud Run

This guide will help you deploy the WebSocket audio echo server to Google Cloud Run.

## Prerequisites

1. **Google Cloud Account**: Sign up at [cloud.google.com](https://cloud.google.com)
2. **Google Cloud SDK**: Install the [gcloud CLI](https://cloud.google.com/sdk/docs/install)
3. **Docker**: Install [Docker](https://www.docker.com/get-started) (for local testing)

## Setup Steps

### 1. Initialize Google Cloud Project

```bash
# Login to Google Cloud
gcloud auth login

# Set your project (replace with your actual project ID)
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable cloudbuild.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
```

**Note**: Update the Artifact Registry path in `cloudbuild.yaml` and `deploy.sh` with your actual registry path: `YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY`

### 2. Build and Deploy Using Cloud Build (Recommended)

This is the easiest method - it builds and deploys in one command:

```bash
# Submit build to Cloud Build
gcloud builds submit --config cloudbuild.yaml
```

This will:
- Build the Docker image
- Push it to Artifact Registry (configured in `cloudbuild.yaml`)
- Deploy it to Cloud Run in your specified region

### 3. Manual Deployment (Alternative)

If you prefer to deploy manually:

```bash
# Configure Docker to use gcloud as a credential helper
# Replace YOUR_REGION with your actual region (e.g., asia-south1, us-central1)
gcloud auth configure-docker YOUR_REGION-docker.pkg.dev

# Build the Docker image for linux/amd64 (required for Cloud Run)
# Note: If building on Apple Silicon (M1/M2), you MUST use --platform linux/amd64
# Replace with your actual registry path
docker build --platform linux/amd64 -t YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY/audio-echo-server .

# Push to Artifact Registry
docker push YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY/audio-echo-server

# Deploy to Cloud Run
gcloud run deploy audio-echo-server \
  --image YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY/audio-echo-server \
  --region YOUR_REGION \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 3600 \
  --max-instances 2

# Optionally set API key for token-based authentication
# gcloud run services update audio-echo-server \
#   --region=YOUR_REGION \
#   --set-env-vars="API_KEY=your-api-key-here"
```

## Get Your Server URL

After deployment, get your server URL:

```bash
# Replace YOUR_REGION with your actual region
gcloud run services describe audio-echo-server --region YOUR_REGION --format 'value(status.url)'
```

The URL will look like: `https://audio-echo-server-xxxxx-uc.a.run.app`

## Authentication Options

The server supports multiple authentication methods. Choose the one that works best for your setup:

### Option 1: API Key Authentication (Recommended - Works for Everyone)

This is the simplest method that works for all users, even without gcloud CLI:

1. **Generate an API key:**
   ```bash
   python generate_api_key.py
   ```

2. **Set the API key as an environment variable on Cloud Run:**
   ```bash
   # Replace YOUR_REGION with your actual region
   gcloud run services update audio-echo-server \
     --region=YOUR_REGION \
     --set-env-vars="API_KEY=your-generated-api-key-here"
   ```

3. **Use the API key in your client:**
   ```bash
   # Set as environment variable
   export API_KEY=your-generated-api-key-here
   python client.py
   
   # Or pass directly
   API_KEY=your-generated-api-key-here python client.py
   ```

The client will automatically use the API key if set, and it works for everyone without requiring gcloud.

### Option 2: Google Cloud Identity Token (Requires gcloud CLI)

If you have gcloud CLI installed and authenticated:

```bash
# Login to Google Cloud
gcloud auth login

# Set your project (replace with your actual project ID)
gcloud config set project YOUR_PROJECT_ID

# The client will automatically use identity token authentication
python client.py
```

### Option 3: Public Access (If Organization Policy Allows)

If your organization allows it, you can make the service publicly accessible:

```bash
# Replace YOUR_REGION with your actual region
gcloud run services add-iam-policy-binding audio-echo-server \
  --region=YOUR_REGION \
  --member=allUsers \
  --role=roles/run.invoker
```

**Note**: If you get an error about organization policies, use Option 1 (API key) or Option 2 (identity token).

## Update Client Configuration

Update your `client.py` to connect to the Cloud Run URL:

```python
# In client.py, change the server_url:
client = AudioEchoClient(server_url="wss://audio-echo-server-xxxxx-uc.a.run.app")
```

**Important**: Use `wss://` (secure WebSocket) for HTTPS URLs, not `ws://`

## Cloud Run Configuration

The deployment uses these settings:
- **Memory**: 512Mi (adjust if needed)
- **CPU**: 1 vCPU
- **Timeout**: 3600 seconds (1 hour) - important for WebSocket connections
- **Max Instances**: 10 (adjust based on your needs)
- **Port**: 8080 (Cloud Run standard)

## Customizing Deployment

### Change Region

The deployment region is configured in `cloudbuild.yaml` and `deploy.sh`. To change it, update:
- The `--region` parameter in the deploy step
- The Artifact Registry path if using a different region's registry
- The `REGION` variable in `deploy.sh`

### Adjust Resources

Modify memory/CPU in `cloudbuild.yaml`:

```yaml
- '--memory'
- '1Gi'  # Increase if needed
- '--cpu'
- '2'    # Increase if needed
```

## Monitoring

View logs:

```bash
# Replace YOUR_REGION with your actual region
gcloud run services logs read audio-echo-server --region YOUR_REGION
```

View service details:

```bash
gcloud run services describe audio-echo-server --region YOUR_REGION
```

## Cost Considerations

Cloud Run charges for:
- **CPU and Memory**: Only when handling requests
- **Requests**: Per million requests
- **Network**: Egress data

The free tier includes:
- 2 million requests per month
- 360,000 GB-seconds of memory
- 180,000 vCPU-seconds

## Troubleshooting

### WebSocket Connection Issues

Cloud Run supports WebSocket, but ensure:
1. You're using `wss://` (not `ws://`) for HTTPS URLs
2. The timeout is set high enough (3600 seconds)
3. The client properly handles reconnections

### Architecture Mismatch Error

If you see an error like:
```
Container manifest type 'application/vnd.oci.image.index.v1+json' must support amd64/linux
```

This means the Docker image was built for the wrong architecture (likely ARM64 on Apple Silicon). **Solution:**

```bash
# Rebuild with --platform linux/amd64 flag
# Replace placeholders with your actual values
docker build --platform linux/amd64 -t YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY/audio-echo-server .
docker push YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY/audio-echo-server
```

Cloud Build automatically handles this, but manual builds on Apple Silicon (M1/M2) require the `--platform linux/amd64` flag.

### Port Issues

The server automatically reads the `PORT` environment variable set by Cloud Run. No manual configuration needed.

### CORS Issues

If you encounter CORS issues, you may need to add CORS headers in the server (though WebSocket connections typically don't have CORS issues).

## Updating the Deployment

To update after making changes:

```bash
# Rebuild and redeploy
gcloud builds submit --config cloudbuild.yaml
```

Or manually:

```bash
# Build for linux/amd64 (required for Cloud Run, especially on Apple Silicon)
# Replace placeholders with your actual values
docker build --platform linux/amd64 -t YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY/audio-echo-server .
docker push YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY/audio-echo-server
gcloud run deploy audio-echo-server --image YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY/audio-echo-server --region YOUR_REGION
```

