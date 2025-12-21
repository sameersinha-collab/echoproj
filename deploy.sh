#!/bin/bash
# Quick deployment script for Google Cloud Run

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Deploying Audio Echo Server to Google Cloud Run...${NC}"

# Set project and registry details
PROJECT_ID="handy-compass-481307-i8"
REGISTRY_PATH="asia-south1-docker.pkg.dev/handy-compass-481307-i8/zippy"
REGION="asia-south1"
IMAGE_NAME="audio-echo-server"
FULL_IMAGE_PATH="${REGISTRY_PATH}/${IMAGE_NAME}"

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
gcloud auth configure-docker asia-south1-docker.pkg.dev --quiet

# Submit build
echo -e "${GREEN}Building and deploying...${NC}"
gcloud builds submit --config cloudbuild.yaml

# Note: Service uses authenticated access by default
# If you need public access, run manually:
# gcloud run services add-iam-policy-binding ${IMAGE_NAME} \
#   --region=${REGION} \
#   --member=allUsers \
#   --role=roles/run.invoker

# Get the service URL
echo -e "${GREEN}Getting service URL...${NC}"
SERVICE_URL=$(gcloud run services describe ${IMAGE_NAME} --region ${REGION} --format 'value(status.url)' 2>/dev/null || echo "")

if [ -n "$SERVICE_URL" ]; then
    echo -e "${GREEN}✓ Deployment successful!${NC}"
    echo -e "${GREEN}Service URL: ${SERVICE_URL}${NC}"
    echo ""
    echo -e "${YELLOW}Update your client.py to use:${NC}"
    echo "  client = AudioEchoClient(server_url=\"wss://${SERVICE_URL#https://}\")"
else
    echo -e "${YELLOW}Deployment completed. Get URL with:${NC}"
    echo "  gcloud run services describe ${IMAGE_NAME} --region ${REGION} --format 'value(status.url)'"
fi

