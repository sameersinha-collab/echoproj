#!/usr/bin/env python3
"""
WebSocket Voice AI Server
Receives audio from clients, processes through Gemini Live API, 
and streams AI-generated audio responses back.
"""

import asyncio
import websockets
import json
import os
import sys
import logging
from typing import Dict, Optional
from urllib.parse import parse_qs, urlparse

from google import genai
from google.genai import types

from agents import get_agent_config, get_voice_profile, DEFAULT_AGENT, DEFAULT_VOICE_PROFILE

# Configure logging for Cloud Run (writes to stderr which Cloud Logging captures)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Audio configuration
INPUT_SAMPLE_RATE = 16000   # Client sends 16kHz
OUTPUT_SAMPLE_RATE = 24000  # Gemini outputs 24kHz
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes

# Gemini model - latest native audio model
GEMINI_MODEL = "models/gemini-2.5-flash-native-audio-latest"


class VoiceAIServer:
    """WebSocket server that bridges clients to Gemini Live API."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_client = genai.Client(api_key=self.gemini_api_key)
    
    def parse_connection_params(self, path: str) -> dict:
        """Parse connection parameters from WebSocket path query string."""
        params = {
            "agent_name": DEFAULT_AGENT,
            "voice_profile": DEFAULT_VOICE_PROFILE,
            "trigger": ""
        }
        
        if path and "?" in path:
            query_string = path.split("?", 1)[1]
            parsed = parse_qs(query_string)
            
            if "agent_name" in parsed:
                params["agent_name"] = parsed["agent_name"][0]
            if "voice_profile" in parsed:
                params["voice_profile"] = parsed["voice_profile"][0]
            if "trigger" in parsed:
                params["trigger"] = parsed["trigger"][0]
        
        return params
    
    async def handle_client(self, websocket, path=None):
        """Handle a new client connection."""
        client_addr = websocket.remote_address
        logger.info(f"Client connected: {client_addr}")
        
        params = self.parse_connection_params(path or "")
        agent_config = get_agent_config(params["agent_name"])
        
        logger.info(f"Agent: {agent_config['name']}")
        logger.info(f"Trigger: {params['trigger']}")
        
        is_active = True
        
        try:
            # Send configuration to client
            await websocket.send(json.dumps({
                "type": "config",
                "data": {
                    "input_sample_rate": INPUT_SAMPLE_RATE,
                    "output_sample_rate": OUTPUT_SAMPLE_RATE,
                    "channels": CHANNELS,
                    "sample_width": SAMPLE_WIDTH,
                    "agent_name": params["agent_name"],
                    "voice_profile": params["voice_profile"]
                }
            }))
            
            # Build Gemini config
            gemini_config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=types.Content(
                    parts=[types.Part(text=agent_config["system_prompt"])]
                )
            )
            
            logger.info(f"Connecting to Gemini: {GEMINI_MODEL}...")
            logger.info(f"API Key (first 10 chars): {self.gemini_api_key[:10]}...")
            
            async with self.gemini_client.aio.live.connect(
                model=GEMINI_MODEL,
                config=gemini_config
            ) as gemini_session:
                logger.info("Gemini session ready - waiting for user to speak")
                
                async def receive_from_client():
                    """Receive audio from client and forward to Gemini."""
                    nonlocal is_active
                    try:
                        async for message in websocket:
                            if not is_active:
                                break
                            if isinstance(message, bytes):
                                # Audio data
                                await gemini_session.send_realtime_input(
                                    audio=types.Blob(
                                        data=message,
                                        mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}"
                                    )
                                )
                            elif isinstance(message, str):
                                data = json.loads(message)
                                if data.get("type") == "text":
                                    text = data.get("text", "")
                                    if text:
                                        await gemini_session.send_client_content(
                                            turns=types.Content(
                                                role="user",
                                                parts=[types.Part(text=text)]
                                            ),
                                            turn_complete=True
                                        )
                    except websockets.exceptions.ConnectionClosed:
                        pass
                    except Exception as e:
                        logger.error(f"Error from client: {e}")
                    finally:
                        is_active = False
                
                async def send_to_client():
                    """Receive responses from Gemini and forward to client."""
                    nonlocal is_active
                    try:
                        logger.info("Listening for Gemini responses...")
                        while is_active:
                            async for response in gemini_session.receive():
                                if not is_active:
                                    return
                                
                                if response.server_content:
                                    model_turn = response.server_content.model_turn
                                    if model_turn and model_turn.parts:
                                        for part in model_turn.parts:
                                            if hasattr(part, 'inline_data') and part.inline_data:
                                                if 'audio' in (part.inline_data.mime_type or ''):
                                                    await websocket.send(part.inline_data.data)
                                    
                                    if response.server_content.turn_complete:
                                        await websocket.send(json.dumps({"type": "turn_complete"}))
                                        logger.info("Turn complete - ready for next")
                            
                            # receive() ended, wait briefly and try again
                            await asyncio.sleep(0.05)
                                    
                    except websockets.exceptions.ConnectionClosed:
                        logger.info("Client WebSocket closed")
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"Gemini error: {e}")
                    finally:
                        is_active = False
                
                # Run both tasks
                logger.info("Starting streaming... (speak into mic after typing 'start')")
                receive_task = asyncio.create_task(receive_from_client())
                send_task = asyncio.create_task(send_to_client())
                
                # Wait until a task completes
                done, pending = await asyncio.wait(
                    [receive_task, send_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                is_active = False
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {client_addr}")
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
        finally:
            logger.info(f"Session ended: {client_addr}")
    
    async def start(self):
        """Start the WebSocket server."""
        logger.info(f"Starting Voice AI Server on ws://{self.host}:{self.port}")
        logger.info(f"Model: {GEMINI_MODEL}")
        
        async def handler(websocket, path=None):
            await self.handle_client(websocket, path)
        
        async with websockets.serve(handler, self.host, self.port):
            await asyncio.Future()


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8765"))
    
    try:
        server = VoiceAIServer(host=host, port=port)
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
