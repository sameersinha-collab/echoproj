#!/usr/bin/env python3
"""
WebSocket Voice AI Server (Pre-Optimization Version)
Receives audio from clients, processes through Gemini Live API, 
and streams AI-generated audio responses back.
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
from typing import Dict, Optional, Any
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

# Event-based greetings configuration
GREETINGS_FILE = "Questions - Greetings.csv"
GREETINGS_CACHE_DIR = "audio_cache"

class VoiceAIServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
        self.greetings = self._load_greetings()
        if not os.path.exists(GREETINGS_CACHE_DIR):
            os.makedirs(GREETINGS_CACHE_DIR)

    def _load_greetings(self) -> Dict[str, list]:
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
        # Simple hash-based filename for caching
        import hashlib
        msg_hash = hashlib.md5(f"{message}_{voice_profile}".encode()).hexdigest()
        cache_path = os.path.join(GREETINGS_CACHE_DIR, f"{msg_hash}.pcm")
        
        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                return f.read()
        
        # If not cached, generate using Gemini (one-time)
        logger.info(f"Generating audio for message: {message}")
        agent = get_agent_config("default") # Use default friendly agent
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=agent["system_prompt"])])
        )
        
        audio_data = bytearray()
        try:
            async with self.gemini_client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
                # Ask Gemini to just say the specific message
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
            "mode": "chat",
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
        # In websockets v10+, the path is in websocket.request.path
        if path is None and hasattr(websocket, 'request'):
            actual_path = websocket.request.path
        else:
            actual_path = path or "/"
            
        params = self.parse_params(actual_path)
        logger.info(f"New {params['mode']} session from {websocket.remote_address} (path: {actual_path})")

        # Handle trigger-based audio events
        if params["trigger"]:
            await self.handle_trigger_event(websocket, params)
            return

        if params["mode"] == "qa":
            await self.handle_qa_session(websocket, params)
        else:
            await self.handle_chat_session(websocket, params)

    async def handle_trigger_event(self, websocket, params):
        trigger = params["trigger"]
        logger.info(f"Handling trigger event: {trigger}")
        
        # Find matching messages for this trigger
        # The CSV has 'Event' and 'Trigger' columns, let's check both
        messages = []
        for event, msgs in self.greetings.items():
            if trigger.lower() in event.lower():
                messages.extend(msgs)
        
        if not messages:
            logger.warning(f"No messages found for trigger: {trigger}")
            await websocket.send(json.dumps({"type": "error", "message": f"No audio for trigger: {trigger}"}))
            return

        # Pick a random message for variety
        message = random.choice(messages)
        # Personalize with child name if placeholder exists (assuming {name} or similar, 
        # but the CSV seems to have hardcoded 'Kian'. Let's replace 'Kian' with child_name)
        message = message.replace("Kian", params["child_name"])
        
        logger.info(f"Selected message: {message}")
        
        # Get cached audio or generate it
        audio_data = await self._get_cached_audio(message, params["voice_profile"])
        
        if audio_data:
            # Send config first so client knows what's coming
            await websocket.send(json.dumps({
                "type": "config",
                "data": {
                    "mode": "trigger",
                    "output_sample_rate": OUTPUT_SAMPLE_RATE
                }
            }))
            
            # Stream the audio in chunks to simulate real-time
            chunk_size = 4800 # 100ms of 24kHz 16-bit mono
            for i in range(0, len(audio_data), chunk_size):
                await websocket.send(audio_data[i:i+chunk_size])
                await asyncio.sleep(0.05) # Small delay to not overwhelm
            
            await websocket.send(json.dumps({"type": "turn_complete"}))
            logger.info(f"Trigger audio delivered for: {trigger}")
        else:
            await websocket.send(json.dumps({"type": "error", "message": "Failed to generate audio"}))

    async def handle_chat_session(self, websocket, params):
        agent = get_agent_config(params["agent_name"])
        
        # Send initial config to client
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

        # Gemini config
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=agent["system_prompt"])]
            )
        )

        async with self.gemini_client.aio.live.connect(model=GEMINI_MODEL, config=config) as gemini_session:
            logger.info("✅ Gemini chat session established")

            async def receive_from_client():
                try:
                    async for message in websocket:
                        if isinstance(message, bytes):
                            await gemini_session.send_realtime_input(
                                audio=types.Blob(data=message, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                            )
                        elif isinstance(message, str):
                            data = json.loads(message)
                            if data.get("type") == "text" and data.get("text"):
                                await gemini_session.send_client_content(
                                    turns=types.Content(role="user", parts=[types.Part(text=data["text"])]),
                                    turn_complete=True
                                )
                except Exception as e:
                    logger.error(f"Error receiving from client: {e}")

            async def send_to_client():
                try:
                    while True:
                        async for response in gemini_session.receive():
                            if response.server_content:
                                model_turn = response.server_content.model_turn
                                if model_turn and model_turn.parts:
                                    for part in model_turn.parts:
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
                            
                            if response.tool_call:
                                pass # Handle tool calls if needed
                        await asyncio.sleep(0.01)
                except Exception as e:
                    logger.error(f"Error sending to client: {e}")

            await asyncio.gather(receive_from_client(), send_to_client())

    async def handle_qa_session(self, websocket, params):
        story = get_story(params["story_id"])
        chapter = story.get_chapter(params["chapter_id"]) if story else None
        
        if not story or not chapter:
            await websocket.send(json.dumps({"type": "error", "message": "Story or Chapter not found"}))
            return

        qa_session = QASession(
            session_id=f"qa_{id(websocket)}",
            story_id=params["story_id"],
            current_chapter_id=params["chapter_id"]
        )
        
        questions = chapter.questions
        state = {
            "current_question_idx": 0,
            "waiting_for_answer": False,
            "question_being_asked": False,
            "audio_sent_this_turn": False
        }

        # Send initial config
        await websocket.send(json.dumps({
            "type": "config",
            "data": {
                "mode": "qa",
                "chapter_name": chapter.chapter_name,
                "total_questions": len(questions),
                "input_sample_rate": INPUT_SAMPLE_RATE,
                "output_sample_rate": OUTPUT_SAMPLE_RATE
            }
        }))

        agent = get_agent_config("story_qa")
        summary = chapter.summary if hasattr(chapter, 'summary') else ""
        system_instruction = f"{agent['system_prompt']}\n\nSTORY: {story.story_name}\nCHAPTER: {chapter.chapter_name}\nSUMMARY: {summary}\nCHILD NAME: {params['child_name']}"
        
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(parts=[types.Part(text=system_instruction)])
        )

        async with self.gemini_client.aio.live.connect(model=GEMINI_MODEL, config=config) as gemini_session:
            logger.info("✅ Gemini Q&A session established")

            async def ask_question(idx):
                if idx < len(questions):
                    q = questions[idx]
                    if idx == 0:
                        # For the first question, include a brief summary intro
                        prompt = f"Briefly summarize the chapter in 1-2 friendly sentences for {params['child_name']}, then ask Question 1: \"{q.question_text}\". The expected answer is \"{q.expected_answers[0]}\"."
                    else:
                        prompt = f"Question {idx+1}: Ask the child: \"{q.question_text}\". The expected answer is \"{q.expected_answers[0]}\". Just ask the question clearly."
                    
                    state["question_being_asked"] = True
                    state["audio_sent_this_turn"] = False
                    await gemini_session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(text=prompt)]),
                        turn_complete=True
                    )

            async def evaluate_answer(user_answer):
                q = questions[state["current_question_idx"]]
                is_correct = q.check_answer(user_answer)
                qa_session.record_answer(q, user_answer, is_correct)
                
                if is_correct:
                    feedback = "That's correct! Great job!"
                else:
                    feedback = f"Actually, the answer is {q.expected_answers[0]}. Let's try the next one!"
                
                await gemini_session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text=f"The child answered: \"{user_answer}\". This is {'correct' if is_correct else 'incorrect'}. {feedback}")]),
                    turn_complete=True
                )

            async def receive_from_client():
                try:
                    async for message in websocket:
                        if isinstance(message, bytes):
                            await gemini_session.send_realtime_input(
                                audio=types.Blob(data=message, mime_type=f"audio/pcm;rate={INPUT_SAMPLE_RATE}")
                            )
                        elif isinstance(message, str):
                            data = json.loads(message)
                            if data.get("type") == "text" and data.get("text"):
                                await gemini_session.send_client_content(
                                    turns=types.Content(role="user", parts=[types.Part(text=data["text"])]),
                                    turn_complete=True
                                )
                except Exception as e:
                    logger.error(f"QA Receive Error: {e}")

            async def send_to_client():
                try:
                    # Ask first question immediately after connection
                    await ask_question(0)

                    while True:
                        async for response in gemini_session.receive():
                            if response.server_content:
                                turn = response.server_content.model_turn
                                if turn and turn.parts:
                                    for part in turn.parts:
                                        if hasattr(part, 'inline_data') and part.inline_data:
                                            state["audio_sent_this_turn"] = True
                                            await websocket.send(part.inline_data.data)
                                        if hasattr(part, 'text') and part.text:
                                            await websocket.send(json.dumps({"type": "transcript", "text": part.text}))

                                if response.server_content.turn_complete:
                                    if state["question_being_asked"] and state["audio_sent_this_turn"]:
                                        state["question_being_asked"] = False
                                        state["waiting_for_answer"] = True
                                        await websocket.send(json.dumps({"type": "turn_complete"}))
                                        logger.info(f"Question {state['current_question_idx']+1} spoken to client")
                                    
                                    elif state["waiting_for_answer"] and state["audio_sent_this_turn"]:
                                        # This was the feedback turn
                                        state["waiting_for_answer"] = False
                                        state["current_question_idx"] += 1
                                        
                                        if state["current_question_idx"] < len(questions):
                                            # Reduced delay between feedback and next question
                                            await asyncio.sleep(0.05)
                                            await ask_question(state["current_question_idx"])
                                        else:
                                            # End of session
                                            await websocket.send(json.dumps({"type": "turn_complete"}))
                                            praise = qa_session.get_praise_message()
                                            await gemini_session.send_client_content(
                                                turns=types.Content(role="user", parts=[types.Part(text=f"The Q&A is over. {praise}")]),
                                                turn_complete=True
                                            )
                                            await websocket.send(json.dumps({"type": "qa_complete", "score": qa_session.score}))
                                            return

                        await asyncio.sleep(0.01)
                except Exception as e:
                    logger.error(f"QA Send Error: {e}")

            await asyncio.gather(receive_from_client(), send_to_client())

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
