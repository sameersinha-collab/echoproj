#!/usr/bin/env python3
"""
WebSocket Audio Echo Server
Receives audio chunks from clients and streams them back with a 1 second delay.
"""

import asyncio
import websockets
import json
import time
from collections import deque
from typing import Dict, Deque, Tuple

# Audio configuration matching ASR standards
SAMPLE_RATE = 16000
CHUNK_SIZE = 4096  # Standard chunk size for ASR
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes
DELAY_SECONDS = 1.0

class AudioBuffer:
    """Manages audio chunks with timestamps for delayed playback."""
    
    def __init__(self, delay_seconds: float = 1.0):
        self.delay_seconds = delay_seconds
        self.chunks: Deque[Tuple[float, bytes]] = deque()  # (timestamp, audio_data)
    
    def add_chunk(self, audio_data: bytes):
        """Add a new audio chunk with current timestamp."""
        self.chunks.append((time.time(), audio_data))
    
    def get_ready_chunks(self) -> list[bytes]:
        """Get all chunks that are ready to be sent (older than delay)."""
        current_time = time.time()
        ready_chunks = []
        
        while self.chunks:
            timestamp, audio_data = self.chunks[0]
            if current_time - timestamp >= self.delay_seconds:
                ready_chunks.append(audio_data)
                self.chunks.popleft()
            else:
                break
        
        return ready_chunks

class AudioEchoServer:
    """WebSocket server that echoes audio with delay."""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Dict[websockets.WebSocketServerProtocol, AudioBuffer] = {}
    
    async def handle_client(self, websocket, path=None):
        """Handle a new client connection."""
        client_addr = websocket.remote_address
        print(f"Client connected: {client_addr}")
        
        # Create audio buffer for this client
        self.clients[websocket] = AudioBuffer(DELAY_SECONDS)
        
        try:
            # Send configuration to client
            config = {
                "sample_rate": SAMPLE_RATE,
                "chunk_size": CHUNK_SIZE,
                "channels": CHANNELS,
                "sample_width": SAMPLE_WIDTH
            }
            await websocket.send(json.dumps({"type": "config", "data": config}))
            
            # Start task to send delayed audio chunks
            send_task = asyncio.create_task(self.send_delayed_audio(websocket))
            
            # Receive audio chunks from client
            async for message in websocket:
                if isinstance(message, bytes):
                    # Audio data received
                    self.clients[websocket].add_chunk(message)
                elif isinstance(message, str):
                    # Control message
                    try:
                        data = json.loads(message)
                        if data.get("type") == "ping":
                            await websocket.send(json.dumps({"type": "pong"}))
                    except json.JSONDecodeError:
                        pass
            
        except websockets.exceptions.ConnectionClosed:
            print(f"Client disconnected: {client_addr}")
        except Exception as e:
            print(f"Error handling client {client_addr}: {e}")
        finally:
            # Cleanup
            if websocket in self.clients:
                del self.clients[websocket]
            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass
    
    async def send_delayed_audio(self, websocket):
        """Continuously send delayed audio chunks to client."""
        try:
            while websocket in self.clients:
                buffer = self.clients[websocket]
                ready_chunks = buffer.get_ready_chunks()
                
                for chunk in ready_chunks:
                    try:
                        await websocket.send(chunk)
                    except websockets.exceptions.ConnectionClosed:
                        return
                
                # Small sleep to avoid busy waiting
                await asyncio.sleep(0.01)  # 10ms
        except asyncio.CancelledError:
            pass
    
    async def start(self):
        """Start the WebSocket server."""
        print(f"Starting Audio Echo Server on ws://{self.host}:{self.port}")
        # Wrap handler to ensure correct signature for websockets library
        async def handler(websocket, path=None):
            await self.handle_client(websocket, path)
        async with websockets.serve(handler, self.host, self.port):
            await asyncio.Future()  # Run forever

def main():
    """Main entry point."""
    server = AudioEchoServer(host="localhost", port=8765)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\nServer shutting down...")

if __name__ == "__main__":
    main()

