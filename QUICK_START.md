# Quick Start Guide for Team Members

## Prerequisites

1. Python 3.7+ installed
2. Microphone access permissions
3. API key from your team lead

## Setup Steps

### 1. Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 2. Set Your API Key

**Option A: Environment Variable (Recommended)**
```bash
export API_KEY=your-api-key-here
```

**Option B: Pass When Running**
```bash
API_KEY=your-api-key-here python client.py
```

**Option C: Set Server URL Too**
```bash
export API_KEY=your-api-key-here
export SERVER_URL=wss://audio-echo-server-XXXXX.asia-south1.run.app
```

### 3. Run the Client

```bash
python client.py
```

You should see:
```
Connecting to wss://...
Using API key authentication...
Connected to server!
```

### 4. Use the Client

Once connected, you can use these commands:
- `start` - Start/resume microphone recording
- `stop` - Stop microphone recording  
- `resume` - Resume microphone recording
- `quit` - Exit the client

## Common Issues

### "API_KEY environment variable not set"
**Solution**: Set the API key (see step 2 above)

### "Connection error: HTTP 403"
**Solution**: 
- Verify API key is correct (no extra spaces)
- Check that API key matches what's set on the server

### "Connection error: HTTP 404"
**Solution**: 
- Verify SERVER_URL is correct
- Check with your team lead for the correct server URL

### "No input device found"
**Solution**:
- Grant microphone permissions to Terminal/Python
- Check system audio settings

## Need Help?

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed troubleshooting steps.

