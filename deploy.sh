#!/bin/bash
# Quick deployment script for Voice AI Server to Google Cloud Run

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Deploying Voice AI Server to Google Cloud Run...${NC}"

# Set project and registry details
PROJECT_ID="${PROJECT_ID:-YOUR_PROJECT_ID}"
REGISTRY_PATH="${REGISTRY_PATH:-YOUR_REGION-docker.pkg.dev/YOUR_PROJECT_ID/YOUR_REPOSITORY}"
REGION="${REGION:-YOUR_REGION}"
IMAGE_NAME="voice-ai-server"
FULL_IMAGE_PATH="${REGISTRY_PATH}/${IMAGE_NAME}"

# Gemini API Key (required)
if [ -z "$GEMINI_API_KEY" ]; then
    echo -e "${RED}Error: GEMINI_API_KEY environment variable is required${NC}"
    echo "  Set it with: export GEMINI_API_KEY=your-api-key"
    exit 1
fi

echo -e "${GREEN}Using project: ${PROJECT_ID}${NC}"
echo -e "${GREEN}Registry: ${REGISTRY_PATH}${NC}"
echo -e "${GREEN}Region: ${REGION}${NC}"

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo -e "${RED}Error: gcloud CLI not found. Please install it:${NC}"
    echo "  https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if user is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo -e "${YELLOW}Not authenticated. Running gcloud auth login...${NC}"
    gcloud auth login
fi

# Enable required APIs
echo -e "${GREEN}Enabling required APIs...${NC}"
gcloud config set project ${PROJECT_ID}
gcloud services enable cloudbuild.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet
gcloud services enable artifactregistry.googleapis.com --quiet

# Configure Docker authentication for Artifact Registry
echo -e "${GREEN}Configuring Docker authentication...${NC}"
REGISTRY_HOST=$(echo "$REGISTRY_PATH" | cut -d'/' -f1)
gcloud auth configure-docker "$REGISTRY_HOST" --quiet

# Build Docker image
echo -e "${GREEN}Building Docker image...${NC}"
docker build --platform linux/amd64 -t ${FULL_IMAGE_PATH} .

# Push to Artifact Registry
echo -e "${GREEN}Pushing to Artifact Registry...${NC}"
docker push ${FULL_IMAGE_PATH}

# Deploy to Cloud Run
echo -e "${GREEN}Deploying to Cloud Run...${NC}"
gcloud run deploy ${IMAGE_NAME} \
    --image ${FULL_IMAGE_PATH} \
    --region ${REGION} \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 1Gi \
    --cpu 2 \
    --timeout 3600 \
    --max-instances 10 \
    --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY}"

# Get the service URL
echo -e "${GREEN}Getting service URL...${NC}"
SERVICE_URL=$(gcloud run services describe ${IMAGE_NAME} --region ${REGION} --format 'value(status.url)' 2>/dev/null || echo "")

if [ -n "$SERVICE_URL" ]; then
    echo -e "${GREEN}✓ Deployment successful!${NC}"
    echo -e "${GREEN}Service URL: ${SERVICE_URL}${NC}"
    echo ""
    echo -e "${YELLOW}Connect with client:${NC}"
    echo "  export SERVER_URL=\"wss://${SERVICE_URL#https://}\""
    echo "  python client.py"
else
    echo -e "${YELLOW}Deployment completed. Get URL with:${NC}"
    echo "  gcloud run services describe ${IMAGE_NAME} --region ${REGION} --format 'value(status.url)'"
fi
