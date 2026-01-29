#!/usr/bin/env python3
"""
WebSocket Voice AI Server
Supports single persistent connection with internal agent switching and session management.
"""

import asyncio
import websockets
import json
import os
import sys
import logging
import time
import random
import csv
import hashlib
from typing import Dict, Optional, Any, List
from urllib.parse import parse_qs, urlparse

from google import genai
from google.genai import types

from agents import get_agent_config, DEFAULT_AGENT, DEFAULT_VOICE_PROFILE
from story_data import get_story, QASession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Audio configuration
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2

# Gemini model
GEMINI_MODEL = "models/gemini-2.5-flash-native-audio-latest"

# Configuration
GREETINGS_FILE = "Questions - Greetings.csv"
GREETINGS_CACHE_DIR = "audio_cache"
SESSION_TIMEOUT_SECONDS = 120  # 3 minutes

class VoiceAIServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
        self.greetings = self._load_greetings()
        if not os.path.exists(GREETINGS_CACHE_DIR):
            os.makedirs(GREETINGS_CACHE_DIR)

    def _load_greetings(self) -> Dict[str, List[str]]:
        greetings = {}
        try:
            if os.path.exists(GREETINGS_FILE):
                with open(GREETINGS_FILE, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        event = row['Event'].strip()
                        if event not in greetings:
                            greetings[event] = []
                        greetings[event].append(row['Message'].strip())
            else:
                logger.warning(f"Greetings file {GREETINGS_FILE} not found.")
        except Exception as e:
            logger.error(f"Error loading greetings CSV: {e}")
        return greetings

    async def _get_cached_audio(self, message: str, voice_profile: str) -> Optional[bytes]:
        msg_hash = hashlib.md5(f"{message}_{voice_profile}".encode()).hexdigest()
        cache_path = os.path.join(GREETINGS_CACHE_DIR, f"{msg_hash}.pcm")
        
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                return f.read()
        
        logger.info(f"Generating audio for message: {message}")
        agent = get_agent_config("default")
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=agent["system_prompt"])])
        )
        
        audio_data = bytearray()
        try:
            async with self.gemini_client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text=f"Please say exactly this and nothing else: {message}")]),
                    turn_complete=True
                )
                async for response in session.receive():
                    if response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if hasattr(part, 'inline_data') and part.inline_data:
                                audio_data.extend(part.inline_data.data)
                    if response.server_content and response.server_content.turn_complete:
                        break
            
            if audio_data:
                with open(cache_path, 'wb') as f:
                    f.write(audio_data)
                return bytes(audio_data)
        except Exception as e:
            logger.error(f"Error generating cached audio: {e}")
        return None

    def parse_params(self, path: str) -> dict:
        params = {
            "agent_name": DEFAULT_AGENT,
            "voice_profile": DEFAULT_VOICE_PROFILE,
            "mode": "idle",
            "child_name": "friend",
            "story_id": "cinderella",
            "chapter_id": "1",
            "trigger": ""
        }
        if path and "?" in path:
            parsed = parse_qs(urlparse(path).query)
            for k in params:
                if k in parsed:
                    params[k] = parsed[k][0]
        return params

    async def handle_client(self, websocket, path=None):
        if path is None and hasattr(websocket, 'request'):
            actual_path = websocket.request.path
        else:
            actual_path = path or "/"
            
        params = self.parse_params(actual_path)
        logger.info(f"Persistent connection established from {websocket.remote_address}")

        # Session state
        state = {
            "mode": params["mode"],
            "params": params,
            "audio_queue": asyncio.Queue(),
            "control_queue": asyncio.Queue(),
            "active_tasks": [],
            "last_activity_time": time.time(),
            "is_active": True
        }

        async def session_manager():
            while state["is_active"]:
                mode = state["mode"]
                logger.info(f"Starting session mode: {mode}")
                
                # Cancel previous tasks if any
                for task in state["active_tasks"]:
                    task.cancel()
                state["active_tasks"] = []

                if mode == "chat":
                    task = asyncio.create_task(self.run_chat_session(websocket, state))
                    state["active_tasks"].append(task)
                elif mode == "qa":
                    task = asyncio.create_task(self.run_qa_session(websocket, state))
                    state["active_tasks"].append(task)
                elif mode == "trigger":
                    task = asyncio.create_task(self.run_trigger_session(websocket, state))
                    state["active_tasks"].append(task)
                elif mode == "idle":
                    await websocket.send(json.dumps({"type": "config", "data": {"mode": "idle"}}))
                    logger.info("Server is now IDLE, waiting for command")
                
                # Wait for mode switch or error
                new_mode_requested = await state["control_queue"].get()
                if new_mode_requested == "exit":
                    state["is_active"] = False
                    break
                state["mode"] = new_mode_requested

        async def message_receiver():
            try:
                async for message in websocket:
                    if isinstance(message, bytes):
                        await state["audio_queue"].put(message)
                    elif isinstance(message, str):
                        try:
                            data = json.loads(message)
                            if data.get("type") == "command":
                                cmd = data.get("command")
                                if cmd == "switch_mode":
                                    new_mode = data.get("mode", "chat")
                                    # Update params
                                    for k in state["params"]:
                                        if k in data:
                                            state["params"][k] = data[k]
                                    await state["control_queue"].put(new_mode)
                                elif cmd == "trigger":
                                    state["params"]["trigger"] = data.get("trigger", "")
                                    await state["control_queue"].put("trigger")
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON received: {message}")
            except websockets.exceptions.ConnectionClosed:
                logger.info("Client disconnected")
            finally:
                state["is_active"] = False
                await state["control_queue"].put("exit")

        # Start with initial trigger if present, otherwise initial mode
        if params["trigger"]:
            state["mode"] = "trigger"

        await asyncio.gather(session_manager(), message_receiver())

    async def run_chat_session(self, websocket, state):
        params = state["params"]
        agent = get_agent_config(params["agent_name"])
        
        # Reset activity timer
        state["last_activity_time"] = time.time()
        
        await websocket.send(json.dumps({
            "type": "config",
            "data": {
                "mode": "chat",
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE,
                "channels": CHANNELS,
                "sample_width": SAMPLE_WIDTH
            }
        }))

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=agent["system_prompt"])])
        )

        try:
            async with self.gemini_client.aio.live.connect(model=GEMINI_MODEL, config=config) as gemini_session:
                logger.info("✅ Gemini chat session established")

                async def forward_audio():
                    while True:
                        audio_data = await state["audio_queue"].get()
                        # We removed last_activity_time reset here so silence doesn't keep session alive
                        await gemini_session.send_realtime_input(
                            audio=types.Blob(data=audio_data, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                        )

                async def receive_gemini():
                    # Send an initial hidden prompt to trigger a greeting
                    await gemini_session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(text=f"Hi Wippi! I am {params['child_name']}. Please give me a very brief, friendly greeting to start our chat!")]),
                        turn_complete=True
                    )
                    while True:
                        async for response in gemini_session.receive():
                            if response.server_content:
                                turn = response.server_content.model_turn
                                if turn and turn.parts:
                                    # Reset timer only when Gemini speaks or sends text
                                    state["last_activity_time"] = time.time()
                                    for part in turn.parts:
                                        if hasattr(part, 'inline_data') and part.inline_data:
                                            await websocket.send(part.inline_data.data)
                                        if hasattr(part, 'text') and part.text:
                                            await websocket.send(json.dumps({
                                                "type": "transcript",
                                                "role": "assistant",
                                                "text": part.text
                                            }))
                                if response.server_content.turn_complete:
                                    await websocket.send(json.dumps({"type": "turn_complete"}))
                        await asyncio.sleep(0.01)

                async def check_timeout():
                    while True:
                        await asyncio.sleep(2) # Check every 2 seconds
                        elapsed = time.time() - state["last_activity_time"]
                        if elapsed > SESSION_TIMEOUT_SECONDS:
                            logger.info(f"Chat session inactivity timeout ({elapsed:.1f}s). Returning to IDLE...")
                            await state["control_queue"].put("idle")
                            return

                # Use wait instead of gather so we exit as soon as check_timeout returns
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(forward_audio()), 
                        asyncio.create_task(receive_gemini()), 
                        asyncio.create_task(check_timeout())
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
        except asyncio.CancelledError:
            logger.info("Chat session task cancelled")
        except Exception as e:
            logger.error(f"Chat session error: {e}")

    async def run_qa_session(self, websocket, state):
        params = state["params"]
        story = get_story(params["story_id"])
        chapter = story.get_chapter(params["chapter_id"]) if story else None
        
        if not story or not chapter:
            await websocket.send(json.dumps({"type": "error", "message": "Story/Chapter not found"}))
            return

        # Configuration
        QA_TIMEOUT_SECONDS = 35

        qa_state = {"questions_asked": 0, "waiting_for_answer": False, "is_closing": False, "last_activity": time.time()}

        await websocket.send(json.dumps({
            "type": "config",
            "data": {
                "mode": "qa",
                "chapter_name": chapter.chapter_name,
                "total_questions": 4,
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE
            }
        }))

        agent = get_agent_config("story_qa")
        story_summary = story.story_summary if hasattr(story, 'story_summary') else ""
        chapter_summary = chapter.summary if hasattr(chapter, 'summary') else ""
        
        # Override character and voice based on story
        character_name = getattr(story, 'character_name', "the story character")
        voice_profile_key = getattr(story, 'voice_profile', params['voice_profile'])
        
        # Get voice profile details
        from agents import get_voice_profile
        v_profile = get_voice_profile(voice_profile_key)
        voice_description = v_profile.get("description", voice_profile_key)
        tone_instruction = v_profile.get("tone_instruction", "")
        
        # Get past chapters summaries for context
        past_summaries = []
        try:
            chapter_ids = list(story.chapters.keys())
            current_idx = chapter_ids.index(params["chapter_id"])
            for i in range(current_idx):
                past_ch = story.chapters[chapter_ids[i]]
                if past_ch.summary:
                    past_summaries.append(f"Chapter {past_ch.chapter_id} ({past_ch.chapter_name}): {past_ch.summary}")
        except Exception as e:
            logger.warning(f"Error getting past summaries: {e}")
            
        combined_chapter_context = ""
        if past_summaries:
            combined_chapter_context += "PAST CHAPTERS:\n" + "\n".join(past_summaries) + "\n\n"
        combined_chapter_context += f"CURRENT CHAPTER ({chapter.chapter_name}):\n{chapter_summary}"

        system_instruction = agent['system_prompt']
        system_instruction = system_instruction.replace("the story's main character", character_name)
        system_instruction = system_instruction.replace("[Overall Story Summary]", story_summary)
        system_instruction = system_instruction.replace("[Current Chapter Summary]", combined_chapter_context)
        system_instruction = system_instruction.replace("[Voice Profile]", f"{voice_description}\nTONE INSTRUCTION: {tone_instruction}")
        system_instruction = system_instruction.replace("[Kid Name]", params['child_name'])
        
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=system_instruction)])
        )

        try:
            async with self.gemini_client.aio.live.connect(model=GEMINI_MODEL, config=config) as gemini_session:
                logger.info("✅ Gemini Q&A session established")

                async def forward_audio():
                    while True:
                        try:
                            audio_data = await state["audio_queue"].get()
                            # Only forward audio if not already in closing phase
                            if qa_state["is_closing"]:
                                return
                            await gemini_session.send_realtime_input(
                                audio=types.Blob(data=audio_data, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                            )
                        except Exception as e:
                            logger.error(f"Error forwarding audio: {e}")
                            break

                async def receive_gemini():
                    try:
                        # Initial prompt to start the 4-question flow with better transition
                        initial_prompt = f"That was such a wonderful part of the story! I'm still thinking about everything that happened. (Start by asking the first question: Cognitive goal)"
                        await gemini_session.send_client_content(
                            turns=types.Content(role="user", parts=[types.Part(text=initial_prompt)]),
                            turn_complete=True
                        )
                        
                        while True:
                            async for response in gemini_session.receive():
                                if response.server_content:
                                    turn = response.server_content.model_turn
                                    if turn and turn.parts:
                                        # Reset timeout on AI activity
                                        qa_state["last_activity"] = time.time()
                                        for part in turn.parts:
                                            if hasattr(part, 'inline_data') and part.inline_data:
                                                await websocket.send(part.inline_data.data)
                                            if hasattr(part, 'text') and part.text:
                                                await websocket.send(json.dumps({"type": "transcript", "text": part.text}))
                                                # More robust detection of the closing phase
                                                text_lower = part.text.lower()
                                                if any(phrase in text_lower for phrase in [
                                                    "next chapter", 
                                                    "see you when it", 
                                                    "i'm ready for more", 
                                                    "that was so much fun",
                                                    "see you when it’s done",
                                                    "see you when it's done"
                                                ]):
                                                    qa_state["is_closing"] = True

                                    if response.server_content.turn_complete:
                                        await websocket.send(json.dumps({"type": "turn_complete"}))
                                        # Ensure we only exit after the closing phrase has been sent
                                        if qa_state["is_closing"]:
                                            logger.info("QA session finished naturally via closing phrase")
                                            await websocket.send(json.dumps({"type": "qa_complete", "score": 100}))
                                            return
                            await asyncio.sleep(0.01)
                    except websockets.exceptions.ConnectionClosed:
                        logger.info("Websocket closed in receive_gemini")
                        return
                    except Exception as e:
                        logger.error(f"Error in receive_gemini: {e}")
                        return

                async def check_qa_timeout():
                    while True:
                        await asyncio.sleep(2)
                        elapsed = time.time() - qa_state["last_activity"]
                        # Timeout only if NO activity (AI hasn't spoken)
                        if elapsed > QA_TIMEOUT_SECONDS and not qa_state["is_closing"]:
                            logger.info(f"QA session timeout ({elapsed:.1f}s). Sending timeout message and returning to IDLE...")
                            # Send a final message before switching
                            timeout_msg = "It looks like you're busy! Let’s start the next chapter and I'll see you when it’s done!"
                            await gemini_session.send_client_content(
                                turns=types.Content(role="user", parts=[types.Part(text=f"The child hasn't responded for a while. Please say exactly this: {timeout_msg}")]),
                                turn_complete=True
                            )
                            # Wait a bit for the audio to be received/processed before exiting to idle fallback
                            await asyncio.sleep(5)
                            return

                # Use wait instead of gather so we exit as soon as any task returns
                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(forward_audio()), 
                        asyncio.create_task(receive_gemini()), 
                        asyncio.create_task(check_qa_timeout())
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                
                # Always return to IDLE after leaving the QA session tasks
                logger.info("Exiting QA session block, ensuring IDLE state...")
                await state["control_queue"].put("idle")
        except asyncio.CancelledError:
            logger.info("QA session task cancelled")
        except Exception as e:
            logger.error(f"QA session error: {e}")
            await state["control_queue"].put("idle")

    async def run_trigger_session(self, websocket, state):
        params = state["params"]
        trigger = params.get("trigger", "")
        logger.info(f"Triggering audio: {trigger}")
        
        messages = []
        for event, msgs in self.greetings.items():
            if trigger.lower() in event.lower():
                messages.extend(msgs)
        
        if not messages:
            await websocket.send(json.dumps({"type": "error", "message": f"No audio for {trigger}"}))
            await state["control_queue"].put("chat") # Revert to chat
            return

        message = random.choice(messages).replace("Kian", params["child_name"])
        audio_data = await self._get_cached_audio(message, params["voice_profile"])
        
        if audio_data:
            await websocket.send(json.dumps({"type": "config", "data": {"mode": "trigger", "output_sample_rate": OUTPUT_SAMPLE_RATE}}))
            chunk_size = 4800
            for i in range(0, len(audio_data), chunk_size):
                await websocket.send(audio_data[i:i+chunk_size])
                await asyncio.sleep(0.05)
            await websocket.send(json.dumps({"type": "turn_complete"}))
            logger.info(f"Trigger {trigger} finished")
        
        # After trigger, automatically go to idle mode (not chat)
        await state["control_queue"].put("idle")

    async def start(self):
        logger.info(f"Server starting on ws://{self.host}:{self.port}")
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()

if __name__ == "__main__":
    server = VoiceAIServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"FATAL: {e}")
        sys.exit(1)
