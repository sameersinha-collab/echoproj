#!/usr/bin/env python3
"""
Voice Analyzer & Mimicry Script
Analyzes a local Zara voice sample and asks Gemini to reverse-engineer a 
System Prompt, then immediately tests it by generating a Gemini-native sample.
"""

import sys
import asyncio
import os
import time
import shutil
import unicodedata
import pyaudio
import subprocess
import io

# Robust UTF-8 handling for terminal output
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except (AttributeError, io.UnsupportedOperation):
    pass # Fallback for environments where buffer isn't available

from google import genai
from google.genai import types

# API Keys (Hardcoded as requested)
GEMINI_API_KEY = "AIzaSyAWslb-USYfbD5ZLEb0xRwi4jiJ-SkJhps"

# Analysis settings
ANALYSIS_PROMPT = (
    "Listen to this audio sample carefully. Analyze the voice persona in the recording. "
    "1. TRANSCRIPTION: Provide a verbatim transcription of exactly what is being said in this audio file. "
    "2. ANALYSIS: Describe the voice in detail: its age, gender, warmth, clarity, pace, and specific accent nuances. "
    "3. SYSTEM PROMPT: Based on your analysis, write a concise but powerful 'System Instruction' "
    "for yourself (Gemini Live API) so that when you use your pre-built voices (like Kore or Aoede), "
    "you mimic this exact style, rhythm, and persona. "
    "Focus on descriptions of tone and personality that guide your speech generation. "
    "Format your response clearly with these three sections."
)

# Audio Settings for playback
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000
CHUNK = 2400

async def analyze_and_mimic(file_path):
    if not os.path.exists(file_path):
        print(f"❌ Error: File not found at the specified path.")
        return

    # Create an ASCII-safe copy for libraries that can't handle unicode paths
    original_name = os.path.basename(file_path)
    safe_name = unicodedata.normalize("NFKD", original_name).encode("ascii", "ignore").decode("ascii")
    if not safe_name:
        safe_name = "audio_sample"
    safe_path = os.path.join(os.path.dirname(file_path), f"ascii_{safe_name}")
    try:
        shutil.copyfile(file_path, safe_path)
    except Exception as e:
        print("⚠️ Could not create ASCII-safe copy. Falling back to original path.")
        safe_path = file_path

    print(f"\n🔊 Step 0: Playing Original Sample...")
    try:
        # Use afplay on macOS for easy MP3/WAV playback
        subprocess.run(["afplay", safe_path], check=True)
    except Exception as e:
        print(f"⚠️ Could not play original file automatically.")
        print("Please listen to your local file manually before proceeding.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    print(f"\n🧠 Step 1: Uploading file for analysis...")
    try:
        sample_file = client.files.upload(file=safe_path)
        
        while sample_file.state.name == "PROCESSING":
            print(".", end="", flush=True)
            time.sleep(1)
            sample_file = client.files.get(name=sample_file.name)
        
        print("\n🔍 Step 2: Analyzing and transcribing voice...")
        analysis_resp = client.models.generate_content(
            model="models/gemini-2.0-flash-exp",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(file_uri=sample_file.uri, mime_type="audio/mpeg" if safe_path.endswith('.mp3') else "audio/wav"),
                        types.Part.from_text(text=ANALYSIS_PROMPT)
                    ]
                )
            ]
        )

        full_analysis = analysis_resp.text
        print("\n" + "="*50)
        print("GEMINI'S ANALYSIS & TRANSCRIPTION")
        print("="*50)
        print(full_analysis)
        print("="*50)
        
        # Try to extract transcription for comparison
        # We'll ask Gemini to just give us the transcription separately if we can't parse it easily, 
        # but for now we'll use a second small call to get just the text for the test message.
        print("\n📝 Extracting transcription for side-by-side comparison...")
        text_resp = client.models.generate_content(
            model="models/gemini-2.0-flash-exp",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(file_uri=sample_file.uri, mime_type="audio/mpeg" if safe_path.endswith('.mp3') else "audio/wav"),
                        types.Part.from_text(text="Provide only the verbatim transcription of this audio file. No other text.")
                    ]
                )
            ]
        )
        comparison_text = text_resp.text.strip()
        
        print(f"\n🎧 Step 3: Generating Gemini-Native mimicry using the same words...")
        print(f"Words to be spoken: \"{comparison_text}\"")
        print("(Press Ctrl+C to stop if you have heard enough)")
        
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)

        # Use the full analysis as system instructions
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
                )
            ),
            system_instruction=types.Content(parts=[types.Part(text=full_analysis)])
        )

        async with client.aio.live.connect(model="models/gemini-2.5-flash-native-audio-latest", config=config) as session:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=comparison_text)]),
                turn_complete=True
            )
            
            async for response in session.receive():
                if response.server_content and response.server_content.model_turn:
                    for part in response.server_content.model_turn.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            stream.write(part.inline_data.data)
                if response.server_content and response.server_content.turn_complete:
                    break

        print("\n✅ Comparison test complete.")
        stream.stop_stream()
        stream.close()
        audio.terminate()

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if safe_path != file_path and os.path.exists(safe_path):
            try:
                os.remove(safe_path)
            except Exception:
                pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python voice_analyzer.py <path_to_audio_file>")
        print("Example: python voice_analyzer.py my_voice_sample.mp3")
    else:
        asyncio.run(analyze_and_mimic(sys.argv[1]))
