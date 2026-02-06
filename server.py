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

from agents import get_agent_config, DEFAULT_AGENT, DEFAULT_VOICE_PROFILE, QA_GOALS, METADATA_FILTER_KEYWORDS, get_qa_initial_prompt
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
SESSION_TIMEOUT_SECONDS = 20  # 3 minutes

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
            "trigger": "",
            "is_last_chapter": False
        }
        if path and "?" in path:
            parsed = parse_qs(urlparse(path).query)
            for k in params:
                if k in parsed:
                    val = parsed[k][0]
                    if k == "is_last_chapter":
                        params[k] = val.lower() == 'true'
                    else:
                        params[k] = val
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
                elif mode == "intro":
                    task = asyncio.create_task(self.run_intro_session(websocket, state))
                    state["active_tasks"].append(task)
                elif mode == "stopped":
                    task = asyncio.create_task(self.run_stopped_session(websocket, state))
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
        QA_TIMEOUT_SECONDS = 20

        qa_state = {
            "question_index": 0, 
            "is_closing": False, 
            "last_activity": time.time(),
            "attempts": 0,
            "waiting_for_answer": True,
            "turn_count": 0
        }

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
        system_instruction = system_instruction.replace("[Character Name]", character_name)
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
                        # Initial prompt to start the session
                        is_last_chapter = story.is_last_chapter(params["chapter_id"])
                        
                        initial_prompt = get_qa_initial_prompt(
                            child_name=params['child_name'],
                            character_name=character_name,
                            story_name=story.story_name,
                            story_summary=story_summary,
                            combined_chapter_context=combined_chapter_context,
                            first_goal_focus=QA_GOALS[0]['focus']
                        )
                        
                        await gemini_session.send_client_content(
                            turns=types.Content(role="user", parts=[types.Part(text=initial_prompt)]),
                            turn_complete=True
                        )
                        
                        while True:
                            async for response in gemini_session.receive():
                                if response.server_content:
                                    turn = response.server_content.model_turn
                                    if turn and turn.parts:
                                        qa_state["last_activity"] = time.time()
                                        qa_state["turn_count"] += 1
                                        turn_text = ""
                                        for part in turn.parts:
                                            if hasattr(part, 'inline_data') and part.inline_data:
                                                await websocket.send(part.inline_data.data)
                                            if hasattr(part, 'text') and part.text:
                                                content = part.text.strip()
                                                turn_text += " " + content
                                                logger.info(f"RECEIVED TEXT: '{content}'")
                                                # Filter metadata
                                                content_lower = content.lower()
                                                metadata_keywords = METADATA_FILTER_KEYWORDS
                                                
                                                if content.startswith("**") or content.startswith("(") or any(x in content_lower for x in metadata_keywords):
                                                    logger.info(f"FILTERED METADATA: '{content[:100]}...'")
                                                    continue
                                                
                                                await websocket.send(json.dumps({"type": "transcript", "text": content}))
                                        
                                        # Only check completion logic on the FULL accumulated turn text or significantly large chunks
                                        # Also SKIP monitoring on the FIRST turn to reduce latency and resource usage
                                        if turn_text.strip() and qa_state["turn_count"] > 1:
                                            full_text = turn_text.strip()
                                            
                                            # Parallel LLM call to monitor session completion
                                            async def monitor_session(text):
                                                try:
                                                    monitor_prompt = (
                                                        "Analyze this dialogue from a story character to a child. "
                                                        "Has the character finished all 4 questions and is now saying goodbye or concluding the session? "
                                                        "Look for phrases like 'That was so much fun', 'I'm ready for more', 'See you next time', or any final farewell. "
                                                        "Answer ONLY 'YES' or 'NO'.\n\n"
                                                        f"Dialogue: \"{text}\""
                                                    )
                                                    response = await self.gemini_client.aio.models.generate_content(
                                                        model="gemini-2.0-flash",
                                                        contents=monitor_prompt
                                                    )
                                                    decision = response.text.strip().upper()
                                                    logger.info(f"MONITOR DECISION: '{decision}' for text: '{text[:50]}...'")
                                                    if "YES" in decision:
                                                        logger.info(f"✅ Monitor detected session completion. Setting is_closing=True")
                                                        qa_state["is_closing"] = True
                                                except Exception as e:
                                                    logger.error(f"Error in monitor_session: {e}")

                                            asyncio.create_task(monitor_session(full_text))

                                            if any(phrase in full_text.lower() for phrase in ["let’s start the next chapter", "let's start the next chapter", "see you when it’s done", "see you when it's done", "that was so much fun"]):
                                                logger.info(f"✅ Keyword match detected for closing. Setting is_closing=True")
                                                qa_state["is_closing"] = True
                                                # Optional: If we found the closing phrase, we can stop processing further text parts to avoid delay from long thought generations
                                                # But we must continue the loop to let the 'turn_complete' signal pass through.

                                    if response.server_content.turn_complete:
                                        if qa_state["is_closing"]:
                                            logger.info("🏁 Session closing detected. Sending qa_complete and exiting receive_gemini.")
                                            await websocket.send(json.dumps({"type": "qa_complete", "score": 100}))
                                            return

                                        await websocket.send(json.dumps({"type": "turn_complete"}))
                                            
                                        # The model finished a turn. If it didn't ask a question or got distracted,
                                        # the next time the child speaks, the model's instructions (in initial_prompt)
                                        # should guide it to pivot back.
                                            
                            await asyncio.sleep(0.01)
                    except Exception as e:
                        logger.error(f"Error in receive_gemini: {e}")

                async def check_qa_timeout():
                    while True:
                        await asyncio.sleep(2)
                        elapsed = time.time() - qa_state["last_activity"]
                        if elapsed > QA_TIMEOUT_SECONDS and not qa_state["is_closing"]:
                            timeout_msg = "It looks like you're busy! Let’s start the next chapter and I'll see you when it’s done!"
                            await gemini_session.send_client_content(
                                turns=types.Content(role="user", parts=[types.Part(text=f"The child hasn't responded. Say exactly: {timeout_msg}")]),
                                turn_complete=True
                            )
                            await asyncio.sleep(5)
                            return

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
                await state["control_queue"].put("idle")
        except Exception as e:
            logger.error(f"QA session error: {e}")
            await state["control_queue"].put("idle")

    async def run_intro_session(self, websocket, state):
        params = state["params"]
        story = get_story(params["story_id"])
        
        if not story:
            await websocket.send(json.dumps({"type": "error", "message": "Story not found"}))
            return

        # Configuration
        INTRO_TIMEOUT_SECONDS = 15

        intro_state = {
            "is_closing": False, 
            "last_activity": time.time(),
            "turn_count": 0,
            "true_turn_count": 0
        }

        await websocket.send(json.dumps({
            "type": "config",
            "data": {
                "mode": "intro",
                "story_name": story.story_name,
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE
            }
        }))

        agent = get_agent_config("story_intro")
        character_name = getattr(story, 'character_name', "the story character")
        
        system_instruction = agent['system_prompt']
        system_instruction = system_instruction.replace("[Character Name]", character_name)
        system_instruction = system_instruction.replace("[Kid Name]", params['child_name'])
        system_instruction = system_instruction.replace("[Story Summary]", story.story_summary)
        
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=system_instruction)])
        )

        try:
            async with self.gemini_client.aio.live.connect(model=GEMINI_MODEL, config=config) as gemini_session:
                logger.info("✅ Gemini Intro session established")

                async def forward_audio():
                    while True:
                        try:
                            audio_data = await state["audio_queue"].get()
                            # if intro_state["is_closing"]:
                            #    return
                            await gemini_session.send_realtime_input(
                                audio=types.Blob(data=audio_data, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                            )
                        except Exception as e:
                            logger.error(f"Error forwarding audio: {e}")
                            break

                async def receive_gemini():
                    try:
                        # Initial prompt
                        initial_prompt = agent['initial_prompt_template']
                        initial_prompt = initial_prompt.replace("[Character Name]", character_name)
                        initial_prompt = initial_prompt.replace("[Kid Name]", params['child_name'])
                        
                        await gemini_session.send_client_content(
                            turns=types.Content(role="user", parts=[types.Part(text=initial_prompt)]),
                            turn_complete=True
                        )
                        
                        while True:
                            async for response in gemini_session.receive():
                                if response.server_content:
                                    turn = response.server_content.model_turn
                                    if turn and turn.parts:
                                        intro_state["last_activity"] = time.time()
                                        intro_state["turn_count"] += 1
                                        turn_text = ""
                                        for part in turn.parts:
                                            if hasattr(part, 'inline_data') and part.inline_data:
                                                await websocket.send(part.inline_data.data)
                                            if hasattr(part, 'text') and part.text:
                                                content = part.text.strip()
                                                turn_text += " " + content
                                                logger.info(f"RECEIVED TEXT: '{content}'")
                                                # Reuse existing metadata filter
                                                content_lower = content.lower()
                                                metadata_keywords = METADATA_FILTER_KEYWORDS
                                                
                                                if content.startswith("**") or content.startswith("(") or any(x in content_lower for x in metadata_keywords):
                                                    logger.info(f"FILTERED METADATA: '{content[:100]}...'")
                                                    continue
                                                
                                                await websocket.send(json.dumps({"type": "transcript", "text": content}))
                                        
                                        if turn_text.strip():
                                            full_text = turn_text.strip()
                                            
                                            # Check keywords for closing
                                            closing_keywords = [
                                                "adventure awaits", "let's get this story started", 
                                                "here we go", "can't wait for you to hear", 
                                                "what happens next"
                                            ]
                                            # Skip detection on the very first greeting (Turn 1) to avoid false positives
                                            # The greeting is fixed and doesn't contain these phrases, but safety first.
                                            # We use a simple counter that increments on turn_complete to track true turns.
                                            if intro_state["true_turn_count"] > 0 and any(phrase in full_text.lower() for phrase in closing_keywords):
                                                logger.info(f"✅ Keyword match detected for intro closing. Setting is_closing=True")
                                                intro_state["is_closing"] = True

                                    if response.server_content.turn_complete:
                                        intro_state["true_turn_count"] += 1
                                        if intro_state["is_closing"]:
                                            logger.info("🏁 Intro session closing detected. Sending intro_complete.")
                                            await websocket.send(json.dumps({"type": "intro_complete"}))
                                            # Wait a bit for audio to play out on client before cutting connection/mode
                                            await asyncio.sleep(0.5) 
                                            return

                                        await websocket.send(json.dumps({"type": "turn_complete"}))
                                            
                            await asyncio.sleep(0.01)
                    except Exception as e:
                        logger.error(f"Error in receive_gemini: {e}")

                async def check_intro_timeout():
                    while True:
                        await asyncio.sleep(2)
                        elapsed = time.time() - intro_state["last_activity"]
                        if elapsed > INTRO_TIMEOUT_SECONDS and not intro_state["is_closing"]:
                            timeout_msg = "Alright, adventure awaits! Let's get this story started!"
                            # Force model to say the timeout message
                            await gemini_session.send_client_content(
                                turns=types.Content(role="user", parts=[types.Part(text=f"The child didn't respond. Say exactly: {timeout_msg}")]),
                                turn_complete=True
                            )
                            # We don't return immediately; we let receive_gemini handle the output and closing detection
                            # But we might want to force close after a short delay to ensure it doesn't hang
                            await asyncio.sleep(5)
                            return

                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(forward_audio()), 
                        asyncio.create_task(receive_gemini()), 
                        asyncio.create_task(check_intro_timeout())
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await state["control_queue"].put("idle")
        except Exception as e:
            logger.error(f"Intro session error: {e}")
            await state["control_queue"].put("idle")

    async def run_stopped_session(self, websocket, state):
        params = state["params"]
        story = get_story(params["story_id"])
        chapter = story.get_chapter(params["chapter_id"]) if story else None
        
        if not story or not chapter:
            await websocket.send(json.dumps({"type": "error", "message": "Story/Chapter not found"}))
            return

        # Configuration
        TIMEOUT_PROMPT_SECONDS = 20
        TIMEOUT_TERMINATE_SECONDS = 50 # 20 + 30

        stopped_state = {
            "is_closing": False, 
            "last_activity": time.time(),
            "turn_count": 0,
            "true_turn_count": 0,
            "timeout_prompt_sent": False
        }

        await websocket.send(json.dumps({
            "type": "config",
            "data": {
                "mode": "stopped",
                "story_name": story.story_name,
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE
            }
        }))
        
        # Check if is_last_chapter is in params (from client), otherwise fallback to story logic
        if "is_last_chapter" in params:
             is_last = params["is_last_chapter"]
        else:
             is_last = story.is_last_chapter(params["chapter_id"])

        if is_last:
            agent = get_agent_config("story_stopped_finished")
            character_name = "Wippi" # Wippi voice for finished
            # Use default voice profile for Wippi (usually Indian Female) if not specified differently, 
            # or we can force it. The prompt says "Voice: Wippi (General AI Voice)". 
            # We'll assume the client/story params might override, but for Wippi we should probably force default or specific wippi voice.
            # Let's stick to the params['voice_profile'] but ideally it should be Wippi's voice.
            # If the story has a character voice mapped, we might need to override it back to Wippi.
            # For now, I will not force the voice profile change here to keep it simple, 
            # unless "Wippi" voice profile exists. It uses 'indian_female' by default.
        else:
            agent = get_agent_config("story_stopped_mid")
            character_name = getattr(story, 'character_name', "the story character")
        
        system_instruction = agent['system_prompt']
        system_instruction = system_instruction.replace("[Character Name]", character_name)
        system_instruction = system_instruction.replace("[Kid Name]", params['child_name'])
        system_instruction = system_instruction.replace("[Chapter Name]", chapter.chapter_name)
        system_instruction = system_instruction.replace("[Chapter Summary]", chapter.summary if chapter.summary else "")
        system_instruction = system_instruction.replace("[Story Name]", story.story_name) # For finished agent
        
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=system_instruction)])
        )

        try:
            async with self.gemini_client.aio.live.connect(model=GEMINI_MODEL, config=config) as gemini_session:
                logger.info("✅ Gemini Stopped session established")

                async def forward_audio():
                    while True:
                        try:
                            audio_data = await state["audio_queue"].get()
                            await gemini_session.send_realtime_input(
                                audio=types.Blob(data=audio_data, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                            )
                        except Exception as e:
                            logger.error(f"Error forwarding audio: {e}")
                            break

                async def receive_gemini():
                    try:
                        # Initial prompt
                        initial_prompt = agent['initial_prompt_template']
                        
                        await gemini_session.send_client_content(
                            turns=types.Content(role="user", parts=[types.Part(text=initial_prompt)]),
                            turn_complete=True
                        )
                        
                        while True:
                            async for response in gemini_session.receive():
                                if response.server_content:
                                    turn = response.server_content.model_turn
                                    if turn and turn.parts:
                                        stopped_state["last_activity"] = time.time()
                                        stopped_state["turn_count"] += 1
                                        turn_text = ""
                                        for part in turn.parts:
                                            if hasattr(part, 'inline_data') and part.inline_data:
                                                await websocket.send(part.inline_data.data)
                                            if hasattr(part, 'text') and part.text:
                                                content = part.text.strip()
                                                turn_text += " " + content
                                                logger.info(f"RECEIVED TEXT: '{content}'")
                                                # Reuse existing metadata filter
                                                content_lower = content.lower()
                                                metadata_keywords = METADATA_FILTER_KEYWORDS
                                                
                                                if content.startswith("**") or content.startswith("(") or any(x in content_lower for x in metadata_keywords):
                                                    logger.info(f"FILTERED METADATA: '{content[:100]}...'")
                                                    continue
                                                
                                                await websocket.send(json.dumps({"type": "transcript", "text": content}))
                                        
                                        if turn_text.strip():
                                            full_text = turn_text.strip()
                                            
                                            # Check keywords for closing
                                            closing_keywords = [
                                                "talk to you later", "see ya", "everyone needs a break sometimes",
                                                "insert my card", "bye"
                                            ]
                                            
                                            if stopped_state["true_turn_count"] > 0 and any(phrase in full_text.lower() for phrase in closing_keywords):
                                                logger.info(f"✅ Keyword match detected for stopped closing. Setting is_closing=True")
                                                stopped_state["is_closing"] = True

                                    if response.server_content.turn_complete:
                                        stopped_state["true_turn_count"] += 1
                                        if stopped_state["is_closing"]:
                                            logger.info("🏁 Stopped session closing detected. Sending stopped_complete.")
                                            await websocket.send(json.dumps({"type": "stopped_complete"}))
                                            # Wait a bit for audio to play out on client before cutting connection/mode
                                            await asyncio.sleep(0.5) 
                                            return

                                        await websocket.send(json.dumps({"type": "turn_complete"}))
                                            
                            await asyncio.sleep(0.01)
                    except Exception as e:
                        logger.error(f"Error in receive_gemini: {e}")

                async def check_stopped_timeout():
                    while True:
                        await asyncio.sleep(2)
                        elapsed = time.time() - stopped_state["last_activity"]
                        
                        if elapsed > TIMEOUT_TERMINATE_SECONDS and not stopped_state["is_closing"]:
                            logger.info("Stopped session termination timeout reached.")
                            timeout_msg = "I'll let you get to your other toys now. Talk to you later!"
                            await gemini_session.send_client_content(
                                turns=types.Content(role="user", parts=[types.Part(text=f"The child didn't respond for a long time. Say exactly: {timeout_msg}")]),
                                turn_complete=True
                            )
                            await asyncio.sleep(5)
                            stopped_state["is_closing"] = True # Trigger close
                            return

                        elif elapsed > TIMEOUT_PROMPT_SECONDS and not stopped_state["timeout_prompt_sent"] and not stopped_state["is_closing"]:
                            logger.info("Stopped session prompt timeout reached.")
                            # Send a prompt to nudge the user
                            await gemini_session.send_client_content(
                                turns=types.Content(role="user", parts=[types.Part(text="The child hasn't responded. Gently prompt them once to see if they are still there. Keep it short.")]),
                                turn_complete=True
                            )
                            stopped_state["timeout_prompt_sent"] = True
                            # We don't return, we keep waiting for termination timeout or user input

                done, pending = await asyncio.wait(
                    [
                        asyncio.create_task(forward_audio()), 
                        asyncio.create_task(receive_gemini()), 
                        asyncio.create_task(check_stopped_timeout())
                    ],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await state["control_queue"].put("idle")
        except Exception as e:
            logger.error(f"Stopped session error: {e}")
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
