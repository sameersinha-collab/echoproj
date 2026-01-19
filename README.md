# Voice AI WebSocket Server & Client

A Python-based real-time voice AI application powered by **Google Gemini 2.5 Flash**. Stream live microphone audio to an AI agent and receive natural voice responses instantly.

## Features

- **Real-time Voice AI**: Bidirectional audio streaming with Gemini Live API
- **Built-in VAD**: Gemini's internal Voice Activity Detection handles turn-taking
- **Multiple Agents**: Configurable AI personalities (sales, support, tutor, etc.)
- **Voice Profiles**: Choose from different TTS voices (default: Indian female)
- **Session Persistence**: Conversation context maintained throughout the session
- **Transcript Logging**: Full conversation transcripts for evaluation

## Architecture

```
┌─────────────┐     WebSocket      ┌─────────────┐     Gemini Live API     ┌─────────────┐
│   Client    │ ◄──────────────► │   Server    │ ◄────────────────────► │   Gemini    │
│  (16kHz)    │    Audio/Text     │  (Bridge)   │      Audio/Text        │  2.5 Flash  │
└─────────────┘                   └─────────────┘                        └─────────────┘
     │                                  │
     │ Mic Input (16kHz)               │ Forwards to Gemini
     │ Speaker Output (24kHz)          │ Streams responses back
     ▼                                  ▼
```

## Requirements

- Python 3.9+
- Google Cloud account with Gemini API access
- PyAudio (requires system audio libraries)
  - macOS: `brew install portaudio`
  - Linux: `sudo apt-get install portaudio19-dev`
  - Windows: Usually included with PyAudio wheel

## Installation

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install System Dependencies

```bash
# macOS
brew install portaudio

# Linux (Ubuntu/Debian)
sudo apt-get install portaudio19-dev
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Gemini API Key

```bash
export GEMINI_API_KEY=your-gemini-api-key
```

## Usage

### Start the Server

```bash
export GEMINI_API_KEY=your-api-key
python server.py
```

Server starts on `ws://localhost:8765`

### Start the Client

```bash
python client.py
```

### Client Commands

- `start` - Start microphone recording
- `stop` - Stop microphone recording  
- `resume` - Resume microphone recording
- `text` - Send text message to AI
- `quit` - Exit the client

### Configuration Options

Set via environment variables:

```bash
# Server URL (default: ws://localhost:8765)
export SERVER_URL=wss://your-cloud-run-url

# Agent personality (default, sales_assistant, support_agent, tutor, companion)
export AGENT_NAME=sales_assistant

# Voice profile (indian_female, indian_male, us_female, us_male, british_female, etc.)
export VOICE_PROFILE=indian_female

# Custom trigger (for your application logic)
export TRIGGER=my_trigger
```

### WebSocket Parameters

Parameters can also be passed via URL query string:

```
ws://localhost:8765?agent_name=tutor&voice_profile=indian_female&trigger=lesson_1
```

## Audio Configuration

| Parameter | Input (Mic) | Output (Speaker) |
|-----------|-------------|------------------|
| Sample Rate | 16,000 Hz | 24,000 Hz |
| Channels | 1 (mono) | 1 (mono) |
| Format | 16-bit PCM | 16-bit PCM |
| Chunk Size | 4096 samples | 6144 samples |

## Available Agents

| Agent Name | Description |
|------------|-------------|
| `default` | Friendly general assistant |
| `sales_assistant` | Professional sales helper |
| `support_agent` | Technical support specialist |
| `interviewer` | Professional interviewer |
| `tutor` | Patient educational tutor |
| `companion` | Casual conversational companion |

## Available Voice Profiles

| Profile | Voice | Language |
|---------|-------|----------|
| `indian_female` (default) | Kore | en-IN |
| `indian_male` | Puck | en-IN |
| `us_female` | Kore | en-US |
| `us_male` | Puck | en-US |
| `british_female` | Aoede | en-GB |
| `british_male` | Charon | en-GB |
| `deep_male` | Fenrir | en-US |

## Deployment to Google Cloud Run

### Quick Deploy

```bash
export GEMINI_API_KEY=your-api-key
export PROJECT_ID=your-project-id
export REGION=asia-south1
export REGISTRY_PATH=asia-south1-docker.pkg.dev/your-project/your-repo

./deploy.sh
```

### Manual Deploy

```bash
# Build image
docker build --platform linux/amd64 -t ${REGISTRY_PATH}/voice-ai-server .

# Push
docker push ${REGISTRY_PATH}/voice-ai-server

# Deploy
gcloud run deploy voice-ai-server \
  --image ${REGISTRY_PATH}/voice-ai-server \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=${GEMINI_API_KEY}" \
  --memory 1Gi \
  --cpu 2 \
  --timeout 3600
```

### Connect to Cloud Run

```bash
export SERVER_URL=wss://voice-ai-server-xxxxx.asia-south1.run.app
python client.py
```

## Troubleshooting

### No audio devices found
- Check system audio settings
- Grant microphone permissions to Terminal/Python
- Verify PyAudio: `python -c "import pyaudio; print(pyaudio.__version__)"`

### Connection errors
- Ensure server is running
- Check `GEMINI_API_KEY` is set on server
- Use `wss://` for Cloud Run URLs

### Audio quality issues
- Ensure microphone supports 16kHz
- Check system audio levels
- Reduce network latency (deploy server closer to users)

### Gemini API errors
- Verify API key is valid
- Check Gemini API quota
- Ensure model `gemini-2.5-flash-preview-native-audio-dialog` is available

## Files

| File | Description |
|------|-------------|
| `server.py` | WebSocket server bridging clients to Gemini |
| `client.py` | Audio client with mic/speaker handling |
| `agents.py` | Agent configurations and voice profiles |
| `requirements.txt` | Python dependencies |
| `requirements-server.txt` | Server-only dependencies (for Docker) |
| `Dockerfile` | Container image for Cloud Run |
| `deploy.sh` | Deployment script |
