#!/usr/bin/env python3
"""
WebSocket Audio Echo Client
Captures microphone audio, sends it via WebSocket, and plays delayed audio back.
"""

import asyncio
import websockets
import json
import pyaudio
import numpy as np
import threading
import queue
import subprocess
import os
from typing import Optional

# Audio configuration matching ASR standards
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHUNK_SIZE = 4096  # Standard chunk size for ASR
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH = 2  # 16-bit = 2 bytes
DEFAULT_FORMAT = pyaudio.paInt16

class AudioEchoClient:
    """WebSocket client for audio streaming with echo playback."""
    
    def __init__(self, server_url: str = "wss://audio-echo-server-388996421538.asia-south1.run.app", api_key: str = "Oe3yxB9OatobNswqGpDizsiSuzESDgKt"):
        self.server_url = server_url
        self.api_key = api_key or os.getenv("API_KEY")  # API key for token authentication
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        
        # Audio configuration (will be updated from server)
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.chunk_size = DEFAULT_CHUNK_SIZE
        self.channels = DEFAULT_CHANNELS
        self.sample_width = DEFAULT_SAMPLE_WIDTH
        self.format = DEFAULT_FORMAT
        
        # PyAudio instance
        self.audio = pyaudio.PyAudio()
        
        # Audio streams
        self.input_stream: Optional[pyaudio.Stream] = None
        self.output_stream: Optional[pyaudio.Stream] = None
        
        # Control flags
        self.is_recording = False
        self.is_connected = False
        
        # Queues for audio data
        self.audio_output_queue = queue.Queue()
        
        # Threads
        self.recording_thread: Optional[threading.Thread] = None
        self.playback_thread: Optional[threading.Thread] = None
    
    def find_input_device(self):
        """Find default input device."""
        try:
            device_info = self.audio.get_default_input_device_info()
            return device_info['index']
        except:
            # Fallback: find any input device
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
            # Fallback: find any output device
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
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=input_device,
                frames_per_buffer=self.chunk_size
            )
            self.is_recording = True
            
            # Start recording thread if not already running
            if not self.recording_thread or not self.recording_thread.is_alive():
                self.recording_thread = threading.Thread(target=self.recording_worker, daemon=True)
                self.recording_thread.start()
            
            print("Recording started!")
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
        print("Recording stopped!")
    
    def resume_recording(self):
        """Resume recording (same as start)."""
        self.start_recording()
    
    def start_playback(self):
        """Start audio playback stream."""
        output_device = self.find_output_device()
        if output_device is None:
            print("No output device found!")
            return
        
        try:
            self.output_stream = self.audio.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                output=True,
                output_device_index=output_device,
                frames_per_buffer=self.chunk_size
            )
            print("Playback started!")
        except Exception as e:
            print(f"Error starting playback: {e}")
    
    def stop_playback(self):
        """Stop audio playback stream."""
        if self.output_stream:
            self.output_stream.stop_stream()
            self.output_stream.close()
            self.output_stream = None
        print("Playback stopped!")
    
    def recording_worker(self):
        """Worker thread that captures audio and sends it via WebSocket."""
        while self.is_connected and self.is_recording:
            try:
                if self.input_stream:
                    # Read audio chunk
                    audio_data = self.input_stream.read(self.chunk_size, exception_on_overflow=False)
                    
                    # Send via WebSocket if connected
                    if self.websocket:
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
                # Get audio chunk from queue (blocking with timeout)
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
    
    def get_identity_token(self) -> Optional[str]:
        """Get Google Cloud identity token for authenticated requests."""
        try:
            # Try to get identity token using gcloud
            result = subprocess.run(
                ['gcloud', 'auth', 'print-identity-token'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            pass
        return None
    
    async def connect(self):
        """Connect to WebSocket server."""
        try:
            print(f"Connecting to {self.server_url}...")
            
            # Priority: 1) API key, 2) gcloud identity token, 3) no auth
            headers = {}
            connection_url = self.server_url
            
            # Use API key if provided (simplest, works for everyone)
            if self.api_key:
                # Add token as query parameter (works better with WebSocket)
                separator = "&" if "?" in connection_url else "?"
                connection_url = f"{connection_url}{separator}token={self.api_key}"
                print("Using API key authentication...")
            else:
                # Fallback to gcloud identity token if available
                identity_token = self.get_identity_token()
                if identity_token:
                    headers['Authorization'] = f'Bearer {identity_token}'
                    print("Using Google Cloud identity token authentication...")
            
            # Connect with headers if available
            # websockets 12.0+ uses additional_headers as a list of (key, value) tuples
            connect_kwargs = {}
            if headers:
                connect_kwargs['additional_headers'] = list(headers.items())
            
            self.websocket = await websockets.connect(connection_url, **connect_kwargs)
            self.is_connected = True
            self.loop = asyncio.get_running_loop()
            print("Connected to server!")
            
            # Start playback thread
            self.playback_thread = threading.Thread(target=self.playback_worker, daemon=True)
            self.playback_thread.start()
            
            # Handle messages from server
            async for message in self.websocket:
                if isinstance(message, bytes):
                    # Audio data received - add to playback queue
                    self.audio_output_queue.put(message)
                elif isinstance(message, str):
                    # Control message
                    try:
                        data = json.loads(message)
                        if data.get("type") == "config":
                            # Update configuration from server
                            config = data.get("data", {})
                            self.sample_rate = config.get("sample_rate", self.sample_rate)
                            self.chunk_size = config.get("chunk_size", self.chunk_size)
                            self.channels = config.get("channels", self.channels)
                            self.sample_width = config.get("sample_width", self.sample_width)
                            print(f"Configuration received: {config}")
                        elif data.get("type") == "pong":
                            pass  # Heartbeat response
                    except json.JSONDecodeError:
                        pass
            
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed by server")
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.is_connected = False
            self.stop_recording()
            if self.websocket:
                await self.websocket.close()
    
    async def run(self):
        """Run the client (connect and handle messages)."""
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

def print_menu():
    """Print control menu."""
    print("\n" + "="*50)
    print("Audio Echo Client - Control Menu")
    print("="*50)
    print("Commands:")
    print("  start  - Start/resume microphone recording")
    print("  stop   - Stop microphone recording")
    print("  resume - Resume microphone recording (same as start)")
    print("  quit   - Exit the client")
    print("="*50 + "\n")

async def main():
    """Main entry point."""
    # Get API key from environment or use None (will try gcloud token as fallback)
    api_key = os.getenv("API_KEY")
    client = AudioEchoClient(
        server_url="wss://audio-echo-server-388996421538.asia-south1.run.app",
        api_key=api_key
    )
    
    # Start connection in background task
    connect_task = asyncio.create_task(client.run())
    
    # Wait a bit for connection
    await asyncio.sleep(1)
    
    if not client.is_connected:
        print("Failed to connect to server. Make sure server is running.")
        return
    
    print_menu()
    
    # Handle user input
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
                
                elif command == "quit":
                    print("Shutting down...")
                    client.cleanup()
                    loop.call_soon_threadsafe(connect_task.cancel)
                    break
                
                else:
                    print("Unknown command. Type 'start', 'stop', 'resume', or 'quit'")
            
            except EOFError:
                break
            except Exception as e:
                print(f"Error handling input: {e}")
    
    # Start input handler in separate thread
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

