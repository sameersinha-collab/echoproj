#!/usr/bin/env python3
"""
WebSocket Audio Echo Server
Receives audio chunks from clients and streams them back with a 1 second delay.
"""

import asyncio
import websockets
import json
import time
import os
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
    
    def __init__(self, host: str = "localhost", port: int = 8765, api_key: str = None):
        self.host = host
        self.port = port
        # API authentication disabled - allow all connections
        self.api_key = None  # Set to: api_key or os.getenv("API_KEY") to re-enable
        self.clients: Dict[websockets.WebSocketServerProtocol, AudioBuffer] = {}
    
    def validate_token(self, path: str, headers: dict) -> bool:
        """Validate API token from query parameter or header."""
        if not self.api_key:
            return True  # No API key required
        
        # Check query parameter (most common for WebSocket)
        if path and "?" in path:
            query_string = path.split("?")[1]
            params = {}
            for param in query_string.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value
            if params.get("token") == self.api_key or params.get("api_key") == self.api_key:
                return True
        
        # Check Authorization header
        auth_header = headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token == self.api_key:
                return True
        
        # Check X-API-Key header
        if headers.get("X-API-Key") == self.api_key:
            return True
        
        return False
    
    async def handle_client(self, websocket, path=None):
        """Handle a new client connection."""
        client_addr = websocket.remote_address
        
        # Validate token if API key is set
        if self.api_key:
            # Get headers from websocket request
            headers = {}
            if hasattr(websocket, 'request_headers'):
                headers = dict(websocket.request_headers)
            elif hasattr(websocket, 'headers'):
                headers = dict(websocket.headers)
            
            if not self.validate_token(path or "", headers):
                print(f"Authentication failed for {client_addr}")
                await websocket.close(code=4001, reason="Invalid API key")
                return
        
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
            
            # Start keep-alive task to prevent timeout (sends ping every 30 seconds)
            keep_alive_task = asyncio.create_task(self.keep_alive(websocket))
            
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
            keep_alive_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass
            try:
                await keep_alive_task
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
    
    async def keep_alive(self, websocket):
        """Send periodic ping to keep connection alive and prevent timeout."""
        try:
            while websocket in self.clients:
                await asyncio.sleep(30)  # Send ping every 30 seconds
                if websocket in self.clients:
                    try:
                        await websocket.ping()
                    except (websockets.exceptions.ConnectionClosed, Exception):
                        return
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
    # Read host and port from environment variables (for Cloud Run)
    # Default to localhost:8765 for local development
    host = os.getenv("HOST", "0.0.0.0")  # 0.0.0.0 for Cloud Run, localhost for local
    port = int(os.getenv("PORT", "8765"))  # Cloud Run sets PORT env var
    api_key = os.getenv("API_KEY")  # Optional API key for authentication
    
    if api_key:
        print("API key authentication enabled")
    else:
        print("No API key set - allowing unauthenticated access")
    
    server = AudioEchoServer(host=host, port=port, api_key=api_key)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\nServer shutting down...")

if __name__ == "__main__":
    main()

