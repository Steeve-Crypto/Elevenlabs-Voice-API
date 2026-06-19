#!/usr/bin/env python3
"""
ElevenLabs Voice Pro - Batch + Long Script Edition
Professional voice-over generator with automatic long-script chunking + Request Stitching
and batch processing support.

This tool uses ElevenLabs' official Request Stitching technique for natural prosody
across long videos. It is designed to be safe for YouTube monetization when using
your own cloned voice.

Author: Built for creators who want high-quality, long-form voice-overs without manual work.
"""

import os
import re
import sys
import argparse
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from pydub import AudioSegment
from tqdm import tqdm

# Load environment variables
load_dotenv()

# ============== CONFIGURATION ==============
API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "35000"))

# Voice settings
STABILITY = float(os.getenv("STABILITY", "0.75"))
SIMILARITY_BOOST = float(os.getenv("SIMILARITY_BOOST", "0.85"))
STYLE = float(os.getenv("STYLE", "0.0"))
USE_SPEAKER_BOOST = os.getenv("USE_SPEAKER_BOOST", "true").lower() == "true"

# Output folder
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

SCRIPTS_DIR = Path("scripts")


def print_header():
    print("\n" + "="*70)
    print("🎙️  ElevenLabs Voice Pro - Batch + Long Script Edition")
    print("   Automatic chunking • Natural prosody stitching • Batch processing")
    print("="*70 + "\n")


def validate_config():
    if not API_KEY:
        print("❌ ERROR: ELEVENLABS_API_KEY not found in .env file")
        print("   Create a .env file with your ElevenLabs API key.")
        sys.exit(1)
    if not VOICE_ID:
        print("❌ ERROR: ELEVENLABS_VOICE_ID not found in .env file")
        print("   Go to ElevenLabs → Voices → click your cloned voice → copy the ID.")
        sys.exit(1)


def split_text_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """
    Intelligently split long text into chunks.
    Prefers paragraph boundaries, then sentence boundaries.
    Never splits in the middle of a sentence.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    # First, try splitting by double newlines (paragraphs)
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_chars:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = para

            # If a single paragraph is still too long, split by sentences
            while len(current_chunk) > max_chars:
                # Find the last sentence end within limit
                sentences = re.split(r'(?<=[.!?])\s+', current_chunk)
                temp = ""
                for sent in sentences:
                    if len(temp) + len(sent) + 1 <= max_chars:
                        temp += (" " if temp else "") + sent
                    else:
                        break
                if temp:
                    chunks.append(temp.strip())
                    # Remove the used part
                    current_chunk = current_chunk[len(temp):].strip()
                else:
                    # Fallback: hard cut at max_chars (rare)
                    chunks.append(current_chunk[:max_chars])
                    current_chunk = current_chunk[max_chars:].strip()

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def estimate_cost(char_count: int) -> str:
    """Rough cost estimate (Flash v2.5 is one of the cheaper models)."""
    # As of 2026, Flash v2.5 is ~$0.30 per 1M characters on Creator plan (approximate)
    cost_per_million = 0.30
    cost = (char_count / 1_000_000) * cost_per_million
    return f"~${cost:.2f} USD (on Creator plan)"


def generate_long_audio(text: str, output_path: Path, dry_run: bool = False) -> bool:
    """
    Generate audio for potentially long text using Request Stitching.
    This is the core feature that makes long scripts sound natural.
    """
    client = ElevenLabs(api_key=API_KEY)

    chunks = split_text_into_chunks(text)
    total_chars = len(text)

    print(f"\n📄 Script length: {total_chars:,} characters (~{total_chars/150:.1f} minutes of speech)")
    print(f"📦 Will be split into {len(chunks)} chunk(s) for processing")
    print(f"💰 Estimated ElevenLabs cost: {estimate_cost(total_chars)}")
    print(f"🎯 Model: {MODEL_ID} | Voice ID: {VOICE_ID}")

    if dry_run:
        print("\n🔍 DRY RUN MODE — No API calls will be made.")
        for i, chunk in enumerate(chunks, 1):
            print(f"   Chunk {i}: {len(chunk):,} chars | Preview: {chunk[:80]}...")
        print(f"\n✅ Would produce: {output_path}")
        return True

    if len(chunks) == 1:
        # Simple single generation (faster, no stitching needed)
        print("\n🚀 Single generation (under limit) — no chunking required...")
        try:
            audio_stream = client.text_to_speech.convert(
                text=chunks[0],
                voice_id=VOICE_ID,
                model_id=MODEL_ID,
                output_format="mp3_44100_128",
                voice_settings={
                    "stability": STABILITY,
                    "similarity_boost": SIMILARITY_BOOST,
                    "style": STYLE,
                    "use_speaker_boost": USE_SPEAKER_BOOST,
                },
            )
            audio_bytes = b"".join(audio_stream)
            output_path.write_bytes(audio_bytes)
            print(f"✅ Successfully generated: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Generation failed: {e}")
            return False

    # === LONG SCRIPT: Use Request Stitching ===
    print("\n🔗 LONG SCRIPT MODE — Using Request Stitching for natural prosody...")
    print("   This keeps voice tone, pacing, and emotion consistent across chunks.\n")

    request_ids: List[str] = []
    audio_segments: List[AudioSegment] = []

    progress_bar = tqdm(chunks, desc="Generating chunks", unit="chunk")

    for i, chunk in enumerate(progress_bar):
        try:
            with client.text_to_speech.with_raw_response.convert(
                text=chunk,
                voice_id=VOICE_ID,
                model_id=MODEL_ID,
                output_format="mp3_44100_128",
                previous_request_ids=request_ids,   # ← KEY: Request Stitching
                voice_settings={
                    "stability": STABILITY,
                    "similarity_boost": SIMILARITY_BOOST,
                    "style": STYLE,
                    "use_speaker_boost": USE_SPEAKER_BOOST,
                },
            ) as response:
                # Get the new request ID for future stitching
                new_request_id = response._response.headers.get("request-id")
                if new_request_id:
                    request_ids.append(new_request_id)

                # Collect audio
                audio_bytes = b"".join(chunk for chunk in response.data)
                segment = AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")
                audio_segments.append(segment)

        except Exception as e:
            print(f"\n❌ Error on chunk {i+1}: {e}")
            print("   Possible causes: Invalid Voice ID, insufficient credits, or rate limit.")
            return False

    # Merge all segments into one seamless file
    print("\n🔗 Merging all chunks into final audio file...")
    final_audio = audio_segments[0]
    for seg in audio_segments[1:]:
        final_audio += seg

    final_audio.export(output_path, format="mp3", bitrate="128k")
    print(f"✅ Final merged file created: {output_path}")
    print(f"   Total duration: ~{len(final_audio)/1000/60:.1f} minutes")
    return True


def process_single_script(input_text: Optional[str] = None, input_file: Optional[Path] = None, dry_run: bool = False):
    """Process a single script (from file or CLI text)."""
    if input_file:
        text = input_file.read_text(encoding="utf-8")
        base_name = input_file.stem
    elif input_text:
        text = input_text
        base_name = "output"
    else:
        # Default to script.txt
        default_script = Path("script.txt")
        if not default_script.exists():
            print("❌ No script.txt found and no text provided.")
            print("   Create script.txt or use: python generate_audio.py \"Your text here\"")
            return
        text = default_script.read_text(encoding="utf-8")
        base_name = "output"

    output_path = OUTPUT_DIR / f"{base_name}.mp3"
    success = generate_long_audio(text, output_path, dry_run=dry_run)
    if success and not dry_run:
        print(f"\n🎉 Done! Your voice-over is ready at: {output_path}")


def process_batch(dry_run: bool = False):
    """Process all .txt files in the scripts/ folder."""
    if not SCRIPTS_DIR.exists():
        SCRIPTS_DIR.mkdir(exist_ok=True)
        print(f"📁 Created {SCRIPTS_DIR}/ folder. Add your .txt scripts there and run again.")
        return

    script_files = list(SCRIPTS_DIR.glob("*.txt"))
    if not script_files:
        print(f"❌ No .txt files found in {SCRIPTS_DIR}/")
        print("   Add your video scripts as .txt files inside the scripts/ folder.")
        return

    print(f"\n📦 BATCH MODE: Found {len(script_files)} script(s) to process.\n")

    for script_file in tqdm(script_files, desc="Processing scripts", unit="script"):
        text = script_file.read_text(encoding="utf-8")
        output_path = OUTPUT_DIR / f"{script_file.stem}.mp3"
        print(f"\n{'='*60}")
        print(f"📄 Processing: {script_file.name}")
        generate_long_audio(text, output_path, dry_run=dry_run)

    if not dry_run:
        print(f"\n🎉 Batch complete! All files saved in {OUTPUT_DIR}/")


def main():
    parser = argparse.ArgumentParser(
        description="ElevenLabs Voice Pro - Generate natural voice-overs from long scripts with batch support."
    )
    parser.add_argument("text", nargs="?", help="Text to convert (for quick single use)")
    parser.add_argument("-f", "--file", type=Path, help="Path to a single .txt script file")
    parser.add_argument("--batch", action="store_true", help="Process all .txt files in scripts/ folder")
    parser.add_argument("--dry-run", action="store_true", help="Show how the script would be split without calling the API")
    args = parser.parse_args()

    print_header()
    validate_config()

    if args.batch:
        process_batch(dry_run=args.dry_run)
    elif args.file:
        process_single_script(input_file=args.file, dry_run=args.dry_run)
    elif args.text:
        process_single_script(input_text=args.text, dry_run=args.dry_run)
    else:
        # Default behavior: use script.txt
        process_single_script(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
