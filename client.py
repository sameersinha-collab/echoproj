#!/usr/bin/env python3
"""
WebSocket Voice AI Client
Captures microphone audio, sends it via WebSocket to Voice AI server,
and plays AI-generated audio responses through speakers.
"""

import asyncio
import websockets
import json
import pyaudio
import threading
import queue
import os
from typing import Optional

# Audio configuration - Input (microphone)
INPUT_SAMPLE_RATE = 16000
INPUT_CHUNK_SIZE = 512  # 32ms at 16kHz
INPUT_CHANNELS = 1
INPUT_FORMAT = pyaudio.paInt16

# Audio configuration - Output (speaker) - Gemini outputs 24kHz
OUTPUT_SAMPLE_RATE = 24000
OUTPUT_CHUNK_SIZE = 768  # 32ms at 24kHz
OUTPUT_CHANNELS = 1
OUTPUT_FORMAT = pyaudio.paInt16


class VoiceAIClient:
    """WebSocket client for Voice AI streaming."""
    
    def __init__(
        self,
        server_url: str = "ws://localhost:8765",
        agent_name: str = "default",
        voice_profile: str = "indian_female",
        trigger: str = ""
    ):
        self.base_url = server_url
        self.agent_name = agent_name
        self.voice_profile = voice_profile
        self.trigger = trigger
        
        # Build connection URL with parameters
        self.server_url = self._build_url()
        
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        
        # PyAudio instance
        self.audio = pyaudio.PyAudio()
        
        # Audio streams
        self.input_stream: Optional[pyaudio.Stream] = None
        self.output_stream: Optional[pyaudio.Stream] = None
        
        # Control flags
        self.is_recording = False
        self.is_connected = False
        self.is_ai_speaking = False  # Half-duplex: mute mic while AI speaks
        
        # Queues for audio data
        self.audio_output_queue = queue.Queue()
        
        # Threads
        self.recording_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None
        
        # Event loop reference
        self.loop = None
        
        # Transcript storage for evaluation
        self.transcripts = []
    
    def _build_url(self) -> str:
        """Build WebSocket URL with query parameters."""
        params = []
        if self.agent_name:
            params.append(f"agent_name={self.agent_name}")
        if self.voice_profile:
            params.append(f"voice_profile={self.voice_profile}")
        if self.trigger:
            params.append(f"trigger={self.trigger}")
        
        if params:
            separator = "&" if "?" in self.base_url else "?"
            return f"{self.base_url}{separator}{'&'.join(params)}"
        return self.base_url
    
    def find_input_device(self):
        """Find default input device."""
        try:
            device_info = self.audio.get_default_input_device_info()
            return device_info['index']
        except:
            for i in range(self.audio.get_device_count()):
                if self.audio.get_device_info_by_index(i)['maxInputChannels'] > 0:
                    return i
            return None
    
    def find_output_device(self):
        """Find default output device."""
        try:
            device_info = self.audio.get_default_output_device_info()
            return device_info['index']
        except:
            for i in range(self.audio.get_device_count()):
                if self.audio.get_device_info_by_index(i)['maxOutputChannels'] > 0:
                    return i
            return None
    
    def start_recording(self):
        """Start capturing audio from microphone."""
        if self.is_recording:
            print("Already recording!")
            return
        
        if not self.is_connected:
            print("Not connected to server!")
            return
        
        input_device = self.find_input_device()
        if input_device is None:
            print("No input device found!")
            return
        
        try:
            self.input_stream = self.audio.open(
                format=INPUT_FORMAT,
                channels=INPUT_CHANNELS,
                rate=INPUT_SAMPLE_RATE,
                input=True,
                input_device_index=input_device,
                frames_per_buffer=INPUT_CHUNK_SIZE
            )
            self.is_recording = True
            
            if not self.recording_thread or not self.recording_thread.is_alive():
                self.recording_thread = threading.Thread(target=self.recording_worker, daemon=True)
                self.recording_thread.start()
            
            print("🎤 Recording started - speak now!")
        except Exception as e:
            print(f"Error starting recording: {e}")
            self.is_recording = False
    
    def stop_recording(self):
        """Stop capturing audio from microphone."""
        if not self.is_recording:
            print("Not recording!")
            return
        
        self.is_recording = False
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
            self.input_stream = None
        print("🔇 Recording stopped")
    
    def resume_recording(self):
        """Resume recording (same as start)."""
        self.start_recording()
    
    def flush_input_buffer(self):
        """Flush the microphone input buffer to discard echo/feedback."""
        if self.input_stream:
            try:
                # Read and discard any buffered audio
                available = self.input_stream.get_read_available()
                if available > 0:
                    self.input_stream.read(available, exception_on_overflow=False)
            except Exception:
                pass
    
    def start_playback(self):
        """Start audio playback stream at 24kHz."""
        output_device = self.find_output_device()
        if output_device is None:
            print("No output device found!")
            return
        
        try:
            self.output_stream = self.audio.open(
                format=OUTPUT_FORMAT,
                channels=OUTPUT_CHANNELS,
                rate=OUTPUT_SAMPLE_RATE,  # 24kHz for Gemini output
                output=True,
                output_device_index=output_device,
                frames_per_buffer=OUTPUT_CHUNK_SIZE
            )
            print("🔊 Playback ready (24kHz)")
        except Exception as e:
            print(f"Error starting playback: {e}")
    
    def stop_playback(self):
        """Stop audio playback stream."""
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None
        print("Playback stopped")
    
    def recording_worker(self):
        """Worker thread that captures audio and sends it via WebSocket."""
        while self.is_connected and self.is_recording:
            try:
                if self.input_stream:
                    audio_data = self.input_stream.read(INPUT_CHUNK_SIZE, exception_on_overflow=False)
                    
                    # Half-duplex: only send audio when AI is not speaking
                    if self.websocket and self.loop and not self.is_ai_speaking:
                        asyncio.run_coroutine_threadsafe(
                            self.websocket.send(audio_data),
                            self.loop
                        )
            except Exception as e:
                if self.is_connected:
                    print(f"Error in recording worker: {e}")
                break
    
    def playback_worker(self):
        """Worker thread that plays audio from the queue."""
        self.start_playback()
        
        while self.is_connected:
            try:
                try:
                    audio_data = self.audio_output_queue.get(timeout=0.1)
                    if self.output_stream:
                        self.output_stream.write(audio_data)
                except queue.Empty:
                    continue
            except Exception as e:
                if self.is_connected:
                    print(f"Error in playback worker: {e}")
                break
        
        self.stop_playback()
    
    async def send_text(self, text: str):
        """Send text message to the AI."""
        if self.websocket and self.is_connected:
            await self.websocket.send(json.dumps({
                "type": "text",
                "text": text
            }))
            print(f"📝 You: {text}")
    
    async def connect(self):
        """Connect to WebSocket server."""
        try:
            if not (self.server_url.startswith("ws://") or self.server_url.startswith("wss://")):
                raise ValueError(f"Invalid WebSocket URL: {self.server_url}")
            
            print(f"Connecting to {self.server_url}...")
            print(f"  Agent: {self.agent_name}")
            print(f"  Voice: {self.voice_profile}")
            
            self.websocket = await websockets.connect(self.server_url)
            self.is_connected = True
            self.loop = asyncio.get_running_loop()
            print("✅ Connected to Voice AI server!")
            
            # Start playback thread
            self.playback_thread = threading.Thread(target=self.playback_worker, daemon=True)
            self.playback_thread.start()
            
            # Handle messages from server
            print("📡 Waiting for messages from server...")
            async for message in self.websocket:
                if isinstance(message, bytes):
                    # Audio data - add to playback queue
                    # Half-duplex: mute mic while AI speaks
                    if not self.is_ai_speaking:
                        self.is_ai_speaking = True
                        print("🔇 AI speaking (mic muted)...")
                    self.audio_output_queue.put(message)
                    
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type")
                        
                        if msg_type == "config":
                            config = data.get("data", {})
                            print(f"📋 Server config: {config}")
                            
                        elif msg_type == "transcript":
                            role = data.get("role", "")
                            text = data.get("text", "")
                            if role == "assistant":
                                print(f"🤖 AI: {text}")
                            self.transcripts.append({"role": role, "text": text})
                            
                        elif msg_type == "turn_complete":
                            # Half-duplex: unmute mic after AI finishes
                            # Wait for playback queue to drain
                            while not self.audio_output_queue.empty():
                                await asyncio.sleep(0.1)
                            # Extra delay for speaker audio to fade
                            await asyncio.sleep(0.8)
                            # Flush mic buffer to discard any echo
                            self.flush_input_buffer()
                            self.is_ai_speaking = False
                            print("🎤 Your turn (mic active)")
                            
                        elif msg_type == "pong":
                            pass
                            
                    except json.JSONDecodeError:
                        pass
            
            print("⚠️ Message loop ended - server stopped sending")
            
        except websockets.exceptions.ConnectionClosed as e:
            print(f"🔌 Connection closed: code={e.code}, reason={e.reason}")
        except websockets.exceptions.InvalidStatus as e:
            print(f"Connection rejected: HTTP {e.response.status_code}")
        except Exception as e:
            print(f"Connection error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.is_connected = False
            self.stop_recording()
            if self.websocket:
                await self.websocket.close()
    
    async def run(self):
        """Run the client."""
        await self.connect()
    
    def cleanup(self):
        """Clean up resources."""
        self.is_connected = False
        self.stop_recording()
        self.stop_playback()
        
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=1.0)
        
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=1.0)
        
        self.audio.terminate()
        
        # Save transcripts for evaluation
        if self.transcripts:
            print("\n📝 Session Transcript:")
            for entry in self.transcripts:
                role = "You" if entry["role"] == "user" else "AI"
                print(f"  [{role}]: {entry['text']}")


def print_menu():
    """Print control menu."""
    print("\n" + "="*60)
    print("Voice AI Client - Control Menu")
    print("="*60)
    print("Commands:")
    print("  start   - Start microphone recording")
    print("  stop    - Stop microphone recording")
    print("  resume  - Resume microphone recording")
    print("  text    - Send text message to AI")
    print("  quit    - Exit the client")
    print("="*60 + "\n")


async def main():
    """Main entry point."""
    # Configuration from environment or defaults
    server_url = os.getenv("SERVER_URL", "ws://localhost:8765")
    agent_name = os.getenv("AGENT_NAME", "default")
    voice_profile = os.getenv("VOICE_PROFILE", "indian_female")
    trigger = os.getenv("TRIGGER", "")
    
    print("\n🎙️  Voice AI Client")
    print("="*60)
    
    client = VoiceAIClient(
        server_url=server_url,
        agent_name=agent_name,
        voice_profile=voice_profile,
        trigger=trigger
    )
    
    # Start connection in background task
    connect_task = asyncio.create_task(client.run())
    
    # Wait for connection
    await asyncio.sleep(3)
    
    if not client.is_connected:
        print("❌ Failed to connect to server.")
        print("   Make sure the server is running and GEMINI_API_KEY is set.")
        # Don't return immediately - let the user see what happened
        await asyncio.sleep(1)
        return
    
    print_menu()
    
    loop = asyncio.get_event_loop()
    
    def handle_input():
        """Handle user input in a separate thread."""
        while client.is_connected:
            try:
                command = input("Enter command: ").strip().lower()
                
                if command == "start":
                    client.start_recording()
                
                elif command == "stop":
                    client.stop_recording()
                
                elif command == "resume":
                    client.resume_recording()
                
                elif command == "text":
                    text = input("Enter message: ").strip()
                    if text:
                        asyncio.run_coroutine_threadsafe(
                            client.send_text(text),
                            client.loop
                        )
                
                elif command == "quit":
                    print("Shutting down...")
                    client.cleanup()
                    loop.call_soon_threadsafe(connect_task.cancel)
                    break
                
                else:
                    print("Unknown command. Type 'start', 'stop', 'text', or 'quit'")
            
            except EOFError:
                break
            except Exception as e:
                print(f"Error: {e}")
    
    # Start input handler
    input_thread = threading.Thread(target=handle_input, daemon=True)
    input_thread.start()
    
    try:
        await connect_task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
