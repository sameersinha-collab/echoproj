# Audio Echo WebSocket Server & Client

A Python-based WebSocket application that streams live microphone audio and echoes it back with a 1-second delay. Uses standard ASR (Automatic Speech Recognition) audio chunking.

## Features

- **WebSocket Server**: Receives audio chunks and streams them back with a 1-second delay
- **WebSocket Client**: 
  - Captures live microphone audio
  - Sends audio in streaming fashion via WebSocket
  - Receives and plays delayed audio through speakers
  - Start/resume/stop microphone controls
  - Uses standard ASR chunking (16kHz, 16-bit PCM, mono, 4096 samples per chunk)

## Requirements

- Python 3.7+
- PyAudio (requires system audio libraries)
  - macOS: `brew install portaudio`
  - Linux: `sudo apt-get install portaudio19-dev` (Ubuntu/Debian)
  - Windows: Usually included with PyAudio wheel

## Installation

### 1. Create a Virtual Environment (Recommended)

It's recommended to create a separate Python environment to isolate project dependencies:

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
# venv\Scripts\activate
```

Once activated, you'll see `(venv)` in your terminal prompt. To deactivate later, simply run:
```bash
deactivate
```

### 2. Install System Dependencies

Install system audio libraries (if needed):
```bash
# macOS
brew install portaudio

# Linux (Ubuntu/Debian)
sudo apt-get install portaudio19-dev
```

### 3. Install Python Dependencies

With your virtual environment activated:
```bash
pip install -r requirements.txt
```

## Usage

### Start the Server

In one terminal:
```bash
python server.py
```

The server will start on `ws://localhost:8765`

### Start the Client

In another terminal:
```bash
python client.py
```

### Client Commands

Once connected, you can use these commands:
- `start` - Start/resume microphone recording
- `stop` - Stop microphone recording
- `resume` - Resume microphone recording (same as start)
- `quit` - Exit the client

## Audio Configuration

The system uses standard ASR audio settings:
- **Sample Rate**: 16000 Hz
- **Chunk Size**: 4096 samples
- **Channels**: 1 (mono)
- **Sample Width**: 2 bytes (16-bit PCM)
- **Delay**: 1 second

## Architecture

### Server (`server.py`)
- Maintains a buffer of audio chunks with timestamps
- Sends chunks back to clients after 1-second delay
- Handles multiple clients simultaneously
- Sends configuration to clients on connection

### Client (`client.py`)
- Uses PyAudio for microphone capture and speaker playback
- Separate threads for recording and playback
- Async WebSocket communication
- Queue-based audio playback for smooth streaming

## Troubleshooting

### No audio input/output devices found
- Check your system audio settings
- On macOS, grant microphone permissions to Terminal/Python
- Verify PyAudio installation: `python -c "import pyaudio; print(pyaudio.__version__)"`

### Connection errors
- Ensure the server is running before starting the client
- Check firewall settings if using remote connections
- Verify the server URL matches in both files

### Audio quality issues
- Ensure your microphone supports 16kHz sample rate
- Check system audio settings for input/output levels
- Try adjusting chunk size if experiencing latency issues

