#!/usr/bin/env python3
"""
Final Voice Matcher - Fixed Verbatim Repetition
Uses Gemini 2.5 Flash Native Audio with Sulafat voice profile.
"""

import sys
import asyncio
import os
import pyaudio
import json
import subprocess
from google import genai
from google.genai import types

# API Key
GEMINI_API_KEY = "AIzaSyDwSgMfmdfKIC8Rp8NZlsRKHulczWTCeto"

# Models
ANALYSIS_MODEL = "models/gemini-2.5-flash"
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-latest"

# Audio Settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000
CHUNK = 2400

# Forced Voice Choice based on your staff's finding
SELECTED_VOICE = "Sulafat"

ANALYSIS_PROMPT = """
Analyze this audio file. 
Return a JSON object with these exact keys:
{
  "transcription": "The verbatim text spoken in the audio. Do not add any punctuation or words not present in the audio.",
  "system_prompt": "A detailed persona description to make the Sulafat voice sound exactly like this sample (warmth, pace, accent, etc.)."
}
"""

async def main(file_path):
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    # 1. Play Original Sample First
    print(f"\n🔊 Step 0: Playing Original Sample...")
    try:
        # Use afplay for macOS
        subprocess.run(["afplay", file_path], check=True)
    except Exception as e:
        print(f"⚠️ Could not play original file automatically: {e}")

    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"📤 Uploading and Analyzing {file_path}...")
    with open(file_path, 'rb') as f:
        uploaded_file = client.files.upload(file=f, config={'mime_type': 'audio/mpeg'})
    
    while uploaded_file.state.name == "PROCESSING":
        await asyncio.sleep(1)
        uploaded_file = client.files.get(name=uploaded_file.name)

    # 2. Get exact transcript and prompt
    print(f"🧠 Requesting Verbatim Transcription...")
    resp = client.models.generate_content(
        model=ANALYSIS_MODEL,
        contents=[
            types.Content(role="user", parts=[
                types.Part.from_uri(file_uri=uploaded_file.uri, mime_type="audio/mpeg"),
                types.Part.from_text(text=ANALYSIS_PROMPT)
            ])
        ],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )

    try:
        result = json.loads(resp.text)
        transcript = result['transcription']
        persona_prompt = result['system_prompt']
    except Exception as e:
        print(f"❌ Failed to parse Gemini response: {e}")
        print(f"Raw response: {resp.text}")
        return

    print(f"\n📝 Verbatim Transcript Found: \"{transcript}\"")
    print(f"📌 Generated Persona Prompt: {persona_prompt}")
    print(f"🎧 Playing Mimicry with voice: {SELECTED_VOICE}...")

    # 3. Setup Audio Output
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)

    # 4. Connect to Live API with strict Verbatim instructions
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=SELECTED_VOICE)
            )
        ),
        system_instruction=types.Content(parts=[types.Part(text=f"{persona_prompt}\n\nCRITICAL: You are a parrot. Repeat the user's text exactly. No greetings. No conversation. No changes.")])
    )

    try:
        async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
            # We send the transcript as the user input
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=transcript)]),
                turn_complete=True
            )
            
            async for response in session.receive():
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            stream.write(part.inline_data.data)
                if response.server_content and response.server_content.turn_complete:
                    break
    except Exception as e:
        print(f"❌ Mimicry Error: {e}")

    print("\n✅ Done.")
    stream.stop_stream()
    stream.close()
    audio.terminate()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python voice_analyzer.py <file.mp3>")
    else:
        asyncio.run(main(sys.argv[1]))
