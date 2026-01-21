#!/usr/bin/env python3
"""
Q&A Test Client for Wippi Voice AI (Pre-Optimization Version)
Connects to the server in Q&A mode and interacts with the story agent.
"""

import asyncio
import websockets
import json
import pyaudio
import sys
import argparse
from urllib.parse import urlencode

# Audio Constants
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2
INPUT_CHUNK = 1600
OUTPUT_CHUNK = 2400

class QATestClient:
    def __init__(self, server_url, story_id, chapter_id, child_name):
        self.server_url = server_url
        self.story_id = story_id
        self.chapter_id = chapter_id
        self.child_name = child_name
        self.audio = pyaudio.PyAudio()
        self.is_ai_speaking = False

    def build_url(self):
        params = {
            "mode": "qa",
            "story_id": self.story_id,
            "chapter_id": self.chapter_id,
            "child_name": self.child_name,
            "device_id": "test_device_python"
        }
        return f"{self.server_url}?{urlencode(params)}"

    async def connect(self):
        url = self.build_url()
        print(f"Connecting to {url}...")
        
        try:
            async with websockets.connect(url) as websocket:
                print("✅ Connected to server!")
                
                # Initialize audio streams
                input_stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=INPUT_SAMPLE_RATE,
                    input=True,
                    frames_per_buffer=INPUT_CHUNK
                )
                
                output_stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=OUTPUT_SAMPLE_RATE,
                    output=True,
                    frames_per_buffer=OUTPUT_CHUNK
                )

                async def receive_loop():
                    nonlocal input_stream
                    try:
                        async for message in websocket:
                            if isinstance(message, bytes):
                                if not self.is_ai_speaking:
                                    print("🤖 Wippi is speaking...")
                                    self.is_ai_speaking = True
                                output_stream.write(message)
                            else:
                                data = json.loads(message)
                                m_type = data.get("type")
                                
                                if m_type == "config":
                                    print(f"📖 Story Chapter: {data['data'].get('chapter_name')}")
                                    print(f"❓ Total Questions: {data['data'].get('total_questions')}")
                                elif m_type == "transcript":
                                    print(f"   💬 AI said: \"{data.get('text')}\"")
                                elif m_type == "turn_complete":
                                    print("   --- AI finished speaking ---")
                                    # Brief delay to allow audio buffer to drain
                                    await asyncio.sleep(0.5)
                                    self.is_ai_speaking = False
                                    print("\n🎤 Your turn! Answer now.")
                                    # Clear input buffer
                                    input_stream.read(input_stream.get_read_available(), exception_on_overflow=False)
                                elif m_type == "qa_complete":
                                    print(f"\n🏆 Q&A Complete! Your Score: {data.get('score')}")
                                    break
                    except Exception as e:
                        print(f"Receive loop error: {e}")

                async def recording_loop():
                    try:
                        while True:
                            if not self.is_ai_speaking:
                                # Read audio from mic in a non-blocking way
                                loop = asyncio.get_event_loop()
                                data = await loop.run_in_executor(
                                    None, 
                                    input_stream.read, 
                                    INPUT_CHUNK, 
                                    False # exception_on_overflow
                                )
                                await websocket.send(data)
                            else:
                                await asyncio.sleep(0.1)
                    except Exception as e:
                        print(f"Recording loop error: {e}")

                await asyncio.gather(receive_loop(), recording_loop())

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.audio.terminate()

def main():
    parser = argparse.ArgumentParser(description="Wippi Q&A Test Client")
    parser.add_argument("--url", default="ws://localhost:8765", help="Server URL")
    parser.add_argument("--story", default="cinderella", help="Story ID")
    parser.add_argument("--chapter", default="1", help="Chapter ID")
    parser.add_argument("--child", default="Kian", help="Child Name")
    
    args = parser.parse_args()
    
    client = QATestClient(args.url, args.story, args.chapter, args.child)
    asyncio.run(client.connect())

if __name__ == "__main__":
    main()
