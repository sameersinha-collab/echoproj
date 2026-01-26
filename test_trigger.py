#!/usr/bin/env python3
"""
Test script for Trigger-based Audio Events
"""
import asyncio
import websockets
import json
import pyaudio
import sys
from urllib.parse import urlencode

# Audio Constants
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
OUTPUT_CHUNK = 2400

async def test_trigger(trigger_name, child_name="Kian"):
    params = {
        "trigger": trigger_name,
        "child_name": child_name,
        "voice_profile": "indian_female"
    }
    url = f"wss://voice-ai-qa-388996421538.asia-south1.run.app?{urlencode(params)}"
    print(f"Connecting for trigger: {trigger_name}...")
    
    audio = pyaudio.PyAudio()
    stream = None
    
    try:
        async with websockets.connect(url) as websocket:
            async for message in websocket:
                if isinstance(message, bytes):
                    if not stream:
                        stream = audio.open(
                            format=pyaudio.paInt16,
                            channels=CHANNELS,
                            rate=OUTPUT_SAMPLE_RATE,
                            output=True,
                            frames_per_buffer=OUTPUT_CHUNK
                        )
                    stream.write(message)
                else:
                    data = json.loads(message)
                    print(f"Server message: {data}")
                    if data.get("type") == "turn_complete":
                        print("Audio finished.")
                        break
                    if data.get("type") == "error":
                        print(f"Error: {data.get('message')}")
                        break
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        if stream:
            stream.stop_stream()
            stream.close()
        audio.terminate()

if __name__ == "__main__":
    trigger = sys.argv[1] if len(sys.argv) > 1 else "Morning Wake Up"
    asyncio.run(test_trigger(trigger))

