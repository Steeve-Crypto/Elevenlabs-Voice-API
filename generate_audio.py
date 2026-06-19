import os
import sys
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs import save

load_dotenv()

# Get API key from environment
api_key = os.getenv("ELEVENLABS_API_KEY")
if not api_key:
    print("Error: ELEVENLABS_API_KEY not found in .env file.")
    sys.exit(1)

client = ElevenLabs(api_key=api_key)

def generate_audio(text: str, output_path: str = "output.mp3", voice_id: str = None):
    """
    Generate audio from text using ElevenLabs.
    
    Args:
        text: The text to convert to speech (your video script)
        output_path: Path to save the audio file
        voice_id: Your cloned voice ID (find in ElevenLabs dashboard)
    """
    if not voice_id:
        # Load from environment variable if set, otherwise use placeholder
        voice_id = os.getenv("ELEVENLABS_VOICE_ID") or "your_cloned_voice_id_here"
        if voice_id == "your_cloned_voice_id_here":
            print("Warning: Using placeholder voice ID. Please set your real voice ID.")
    
    try:
        # Use Flash model for longer generations and speed (up to ~40 minutes)
        audio = client.generate(
            text=text,
            voice=voice_id,
            model="eleven_flash_v2_5",
            output_format="mp3_44100_128",
        )
        
        save(audio, output_path)
        print(f"✅ Audio saved to {output_path}")
        
    except Exception as e:
        print(f"Error generating audio: {e}")
        # Fallback to streaming for very long text
        try:
            print("Trying streaming fallback for long text...")
            audio_stream = client.generate(
                text=text,
                voice=voice_id,
                model="eleven_flash_v2_5",
                stream=True,
            )
            with open(output_path, "wb") as f:
                for chunk in audio_stream:
                    f.write(chunk)
            print(f"✅ Audio saved to {output_path} (via stream)")
        except Exception as e2:
            print(f"Streaming also failed: {e2}")


if __name__ == "__main__":
    text = None
    output = "output.mp3"

    if len(sys.argv) > 1:
        # Text provided directly as command-line argument
        text = sys.argv[1]
        if len(sys.argv) > 2:
            output = sys.argv[2]
    else:
        # No CLI argument — try reading from script.txt (best for long video scripts)
        script_file = "script.txt"
        if os.path.exists(script_file):
            with open(script_file, "r", encoding="utf-8") as f:
                text = f.read().strip()
            print(f"Loaded video script from {script_file}")
        else:
            print("No script text provided.")
            print("\n📍 How to add your VIDEO SCRIPT:")
            print("   Best way (recommended): Create a file called 'script.txt' in this folder")
            print("   and paste your full video script inside it. Then simply run:")
            print("      python generate_audio.py")
            print("\n   Alternative: Pass the text directly in the terminal:")
            print('      python generate_audio.py "Paste your full script here" output_audio.mp3')
            sys.exit(1)

    if not text:
        print("Error: No text found to convert to audio.")
        sys.exit(1)

    generate_audio(text, output)
    
    print("\n🎉 Done! Your voice-over audio is ready.")
    print("Tip: For extremely long scripts, split the text into multiple parts and combine the MP3s with ffmpeg.")
