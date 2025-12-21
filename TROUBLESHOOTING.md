# Troubleshooting Connection Issues

If your team members are unable to connect to the server, check the following:

## 1. Verify API Key is Set on Cloud Run

The server must have the API_KEY environment variable set. Check with:

```bash
gcloud run services describe audio-echo-server \
  --region=YOUR_REGION \
  --format="value(spec.template.spec.containers[0].env)"
```

If API_KEY is not set, set it:

```bash
gcloud run services update audio-echo-server \
  --region=YOUR_REGION \
  --set-env-vars="API_KEY=your-api-key-here"
```

## 2. Verify Team Members Are Using the API Key

Team members must provide the API key in one of these ways:

### Option A: Environment Variable (Recommended)
```bash
export API_KEY=your-api-key-here
python client.py
```

### Option B: Pass as Command Line Argument
```bash
API_KEY=your-api-key-here python client.py
```

### Option C: Modify client.py
Change the default in `client.py`:
```python
def __init__(self, server_url: str = "wss://your-server-url", api_key: str = "your-api-key-here"):
```

## 3. Verify Server URL is Correct

The server URL should be:
- Format: `wss://audio-echo-server-XXXXX.asia-south1.run.app` (for HTTPS)
- Get the correct URL:
```bash
gcloud run services describe audio-echo-server \
  --region=asia-south1 \
  --format='value(status.url)'
```

Then convert `https://` to `wss://`:
- `https://audio-echo-server-XXXXX.asia-south1.run.app` → `wss://audio-echo-server-XXXXX.asia-south1.run.app`

## 4. Check Server Logs

View server logs to see connection attempts:

```bash
gcloud run services logs read audio-echo-server \
  --region=asia-south1 \
  --limit=50
```

Look for:
- "Authentication failed" - API key mismatch
- "Client connected" - Successful connection
- Connection errors

## 5. Common Error Messages and Solutions

### Error: "Authentication failed" or HTTP 403
**Cause**: API key mismatch or not provided
**Solution**: 
- Verify API_KEY is set on Cloud Run service
- Verify team members are passing the API key correctly
- Check that the API key matches exactly (no extra spaces)

### Error: "Connection refused" or HTTP 404
**Cause**: Wrong server URL or service not deployed
**Solution**:
- Verify the server URL is correct
- Check that the service is deployed and running
- Ensure you're using `wss://` not `ws://` for HTTPS URLs

### Error: "Invalid WebSocket URL format"
**Cause**: URL doesn't start with ws:// or wss://
**Solution**: Ensure URL starts with `wss://` for Cloud Run

## 6. Test Connection Manually

Test the WebSocket connection with curl:

```bash
# Get identity token (if using gcloud auth)
TOKEN=$(gcloud auth print-identity-token)

# Test WebSocket connection (replace with your URL and API key)
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: test" \
  "wss://your-server-url?token=your-api-key"
```

## 7. Quick Checklist for Team Members

- [ ] API key is set: `export API_KEY=your-key` or passed to script
- [ ] Server URL is correct and uses `wss://` protocol
- [ ] Python dependencies installed: `pip install -r requirements.txt`
- [ ] Microphone permissions granted (macOS/Linux)
- [ ] No firewall blocking WebSocket connections

## 8. Debug Mode

Enable verbose logging in client.py by adding:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

This will show detailed connection information.

