#!/usr/bin/env python3
"""
Final Voice Matcher - Fixed Verbatim Repetition
Uses Gemini 2.5 Flash Native Audio with Gemini-selected voice profile.
Saves the generated mimicry as a WAV file.
"""

import sys
import asyncio
import os
import pyaudio
import json
import subprocess
import wave
from google import genai
from google.genai import types

# API Key - HARDCODED AS REQUESTED
GEMINI_API_KEY = "AIzaSyDwSgMfmdfKIC8Rp8NZlsRKHulczWTCeto"

# Models
ANALYSIS_MODEL = "gemini-3-flash-preview"# Using 3.0 for robust file analysis
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-latest"

# Audio Settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 24000
CHUNK = 2400

ANALYSIS_PROMPT = """
Analyze this audio file carefully. 
Return a JSON object with these exact keys:
{
  "transcription": "The verbatim text spoken in the audio. Do not add any punctuation or words not present in the audio.",
  "system_prompt": "A detailed persona description to make a Gemini voice sound exactly like this sample (warmth, pace, Indian English accent).",
  "best_voice": "Choose the single closest matching voice from this list: [Achernar, Achird, Algenib, Algieba, Alnilam, Aoede, Autonoe, Callirrhoe, Charon, Despina, Enceladus, Erinome, Fenrir, Gacrux, Iapetus, Kore, Laomedeia, Leda, Orus, Pulcherrima, Puck, Rasalgethi, Sadachbia, Sadaltager, Schedar, Sulafat, Umbriel, Vindemiatrix, Zephyr, Zubenelgenubi]"
}
"""

async def main(file_path):
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return

    # 1. Play Original Sample First - Using a more robust method if afplay fails
    print(f"\n🔊 Step 0: Playing Original Sample...")
    try:
        # Try afplay first
        subprocess.run(["afplay", file_path], check=True, stderr=subprocess.PIPE)
    except Exception as e:
        print(f"⚠️ afplay failed. This often happens if the MP3 header is slightly non-standard.")
        print(f"Please listen to the file '{file_path}' manually if you don't hear anything.")

    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"📤 Uploading and Analyzing {file_path}...")
    try:
        with open(file_path, 'rb') as f:
            uploaded_file = client.files.upload(file=f, config={'mime_type': 'audio/mpeg'})
        
        while uploaded_file.state.name == "PROCESSING":
            await asyncio.sleep(1)
            uploaded_file = client.files.get(name=uploaded_file.name)
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return

    # 2. Get exact transcript, prompt, and voice choice
    print(f"🧠 Requesting Verbatim Transcription and Voice Selection using {ANALYSIS_MODEL}...")
    try:
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

        result = json.loads(resp.text)
        transcript = result.get('transcription', '').strip()
        persona_prompt = result.get('system_prompt', '').strip()
        selected_voice = result.get('best_voice', 'Sulafat').strip()
    except Exception as e:
        print(f"❌ Failed to parse Gemini response: {e}")
        print(f"Raw response: {resp.text}")
        return

    if not transcript:
        print("❌ Verbatim Transcript is empty. Gemini could not hear any speech.")
        return

    print(f"\n🎯 Gemini Selected Voice: {selected_voice}")
    print(f"📝 Verbatim Transcript Found: \"{transcript}\"")
    print(f"📌 Generated Persona Prompt: {persona_prompt}")
    print(f"🎧 Playing and saving mimicry...")

    # 3. Setup Audio Output and Storage
    output_filename = f"mimicry_{os.path.splitext(os.path.basename(file_path))[0]}.wav"
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True)
    
    all_audio_data = bytearray()

    # 4. Connect to Live API with strict Verbatim instructions
    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=selected_voice)
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
                            audio_chunk = part.inline_data.data
                            stream.write(audio_chunk)
                            all_audio_data.extend(audio_chunk)
                if response.server_content and response.server_content.turn_complete:
                    break
        
        # Save the captured audio as WAV (Python standard library handles this easily)
        if all_audio_data:
            with wave.open(output_filename, "wb") as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(2) # 16-bit
                wf.setframerate(RATE)
                wf.writeframes(all_audio_data)
            print(f"💾 Mimicry saved to: {output_filename} (WAV, 24kHz, 16-bit, Mono)")
            
    except Exception as e:
        print(f"❌ Mimicry Error: {e}")

    print("\n✅ Done.")
    stream.stop_stream()
    stream.close()
    audio.terminate()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python voice_analyzer.py <path_to_audio_file>")
    else:
        asyncio.run(main(sys.argv[1]))
