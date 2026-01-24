#!/usr/bin/env python3
"""
Persistent Test Client for Wippi Voice AI
Demonstrates single connection with agent switching.
"""
import asyncio
import websockets
import json
import pyaudio
import sys
import threading
import queue
import time
from urllib.parse import urlencode

# Audio Constants
IN_RATE, OUT_RATE = 16000, 24000
CHANNELS, WIDTH = 1, 2
IN_CHUNK = 512   # 32ms at 16kHz
OUT_CHUNK = 768  # 32ms at 24kHz

class PersistentClient:
    def __init__(self, url, child_name="Kian"):
        self.url = url
        self.child_name = child_name
        self.audio = pyaudio.PyAudio()
        self.ws = None
        self.loop = None
        self.is_active = False
        self.is_ai_speaking = False
        self.out_queue = queue.Queue()
        self.streams = {"in": None, "out": None}

    def start_audio(self):
        try:
            self.streams["in"] = self.audio.open(format=pyaudio.paInt16, channels=CHANNELS, rate=IN_RATE, input=True, frames_per_buffer=IN_CHUNK)
            self.streams["out"] = self.audio.open(format=pyaudio.paInt16, channels=CHANNELS, rate=OUT_RATE, output=True, frames_per_buffer=OUT_CHUNK)
            threading.Thread(target=self._recording_worker, daemon=True).start()
            threading.Thread(target=self._playback_worker, daemon=True).start()
            print("🎙️ Audio hardware initialized")
        except Exception as e:
            print(f"❌ Audio error: {e}")

    def _recording_worker(self):
        while self.is_active:
            try:
                data = self.streams["in"].read(IN_CHUNK, exception_on_overflow=False)
                if self.ws and self.loop and not self.is_ai_speaking:
                    asyncio.run_coroutine_threadsafe(self.ws.send(data), self.loop)
            except Exception: pass

    def _playback_worker(self):
        while self.is_active:
            try:
                data = self.out_queue.get(timeout=0.1)
                if self.streams["out"]: self.streams["out"].write(data)
            except queue.Empty: pass

    async def send_command(self, cmd_data):
        if self.ws:
            # If switching to chat, assume AI will speak first and mute mic
            if cmd_data.get("command") == "switch_mode" and cmd_data.get("mode") == "chat":
                self.is_ai_speaking = True
                print("🔇 Switching to Chat (mic muted for greeting)...")
            
            await self.ws.send(json.dumps({"type": "command", **cmd_data}))
            print(f"➡️ Command sent: {cmd_data.get('command')} ({cmd_data.get('mode', cmd_data.get('trigger'))})")

    async def connect(self):
        self.is_active = True
        self.start_audio()
        
        # Initial connection (starts in idle)
        params = {"child_name": self.child_name, "mode": "idle"}
        conn_url = f"{self.url}?{urlencode(params)}"
        print(f"Connecting to {conn_url}...")
        
        try:
            async with websockets.connect(conn_url) as ws:
                self.ws = ws
                self.loop = asyncio.get_running_loop()
                print("✅ Connected!")

                # Background task to listen for user keyboard input to switch modes
                async def input_loop():
                    while self.is_active:
                        print("\nOptions: [1] Chat [2] Q&A (Cinderella Ch1) [3] Trigger (Morning Wake Up) [q] Quit")
                        choice = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                        choice = choice.strip()
                        if choice == '1':
                            await self.send_command({"command": "switch_mode", "mode": "chat"})
                        elif choice == '2':
                            await self.send_command({"command": "switch_mode", "mode": "qa", "story_id": "cinderella", "chapter_id": "1"})
                        elif choice == '3':
                            await self.send_command({"command": "trigger", "trigger": "Morning Wake Up"})
                        elif choice == 'q':
                            self.is_active = False
                            break

                input_task = asyncio.create_task(input_loop())

                async for msg in ws:
                    if isinstance(msg, bytes):
                        if not self.is_ai_speaking:
                            self.is_ai_speaking = True
                        self.out_queue.put(msg)
                    else:
                        data = json.loads(msg)
                        m_type = data.get("type")
                        if m_type == "config":
                            mode = data['data'].get('mode')
                            print(f"\n📋 Mode: {mode} (Config received)")
                            if mode == "idle":
                                self.is_ai_speaking = False
                                print("💤 System is IDLE. Choose an option to start.")
                        elif m_type == "transcript":
                            print(f"   💬 \"{data.get('text')}\"")
                        elif m_type == "turn_complete":
                            while not self.out_queue.empty(): await asyncio.sleep(0.1)
                            await asyncio.sleep(0.5)
                            self.is_ai_speaking = False
                            print("   --- Wippi finished ---")
                        elif m_type == "qa_complete":
                            print(f"\n🏆 Q&A Done! Score: {data.get('score')}")
                        elif m_type == "error":
                            print(f"❌ Server Error: {data.get('message')}")
                
                input_task.cancel()
        except Exception as e:
            print(f"❌ Connection error: {e}")
        finally:
            self.is_active = False
            self.audio.terminate()

if __name__ == "__main__":
    client = PersistentClient("wss://voice-ai-pers-388996421538.asia-south1.run.app")
    asyncio.run(client.connect())

