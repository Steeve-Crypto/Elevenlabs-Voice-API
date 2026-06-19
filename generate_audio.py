#!/usr/bin/env python3
"""
ElevenLabs Voice Pro - Multi-Voice + Auto-Subtitles Edition
Professional voice-over generator with:
- Automatic long-script chunking with Request Stitching
- Multi-Voice / Character Switching via [SPEAKER] tags
- Automatic SRT + VTT subtitle generation using Forced Alignment
- Batch processing support

YouTube-monetization safe when using your own cloned voice.
"""

import os
import re
import sys
import json
import argparse
import tempfile
import shutil
from io import BytesIO
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from pydub import AudioSegment
from tqdm import tqdm

load_dotenv()

# ============== CONFIGURATION ==============
API_KEY = os.getenv("ELEVENLABS_API_KEY")
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5")
MAX_CHUNK_CHARS = int(os.getenv("MAX_CHUNK_CHARS", "35000"))

# Voice settings (can be overridden per generation if needed)
STABILITY = float(os.getenv("STABILITY", "0.75"))
SIMILARITY_BOOST = float(os.getenv("SIMILARITY_BOOST", "0.85"))
STYLE = float(os.getenv("STYLE", "0.0"))
USE_SPEAKER_BOOST = os.getenv("USE_SPEAKER_BOOST", "true").lower() == "true"

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
SCRIPTS_DIR = Path("scripts")
TEMP_DIR = Path(tempfile.mkdtemp(prefix="elevenlabs_segments_"))

VOICES_FILE = Path("voices.json")


def print_header():
    print("\n" + "="*72)
    print("🎙️  ElevenLabs Voice Pro — Multi-Voice + Auto-Subtitles")
    print("   Long Script • Character Switching • Request Stitching • SRT/VTT Subs")
    print("="*72 + "\n")


def validate_config():
    if not API_KEY:
        print("❌ ERROR: ELEVENLABS_API_KEY not found in .env")
        print("   Create .env with: ELEVENLABS_API_KEY=sk-...")
        sys.exit(1)
    if not DEFAULT_VOICE_ID and not VOICES_FILE.exists():
        print("❌ ERROR: No default voice or voices.json found.")
        print("   Add ELEVENLABS_VOICE_ID to .env OR create voices.json")
        sys.exit(1)


def load_voices() -> Dict[str, str]:
    """Load voice mappings. Supports voices.json or falls back to single default voice."""
    voices = {"default": DEFAULT_VOICE_ID or ""}
    
    if VOICES_FILE.exists():
        try:
            with open(VOICES_FILE, "r", encoding="utf-8") as f:
                custom = json.load(f)
            voices.update(custom)
            print(f"✅ Loaded {len(custom)} voice mappings from voices.json")
        except Exception as e:
            print(f"⚠️  Warning: Could not load voices.json ({e}). Using default only.")
    return voices


def parse_script_for_voices(script_text: str) -> List[Dict]:
    """
    Parse script with optional [SPEAKER] tags.
    Returns list of segments: [{"speaker": "NARRATOR", "text": "...", "original": "..."}]
    If no tags found, returns one segment with speaker="default".
    """
    script_text = script_text.strip()
    if not script_text:
        return []

    # Regex to capture [UPPER_TAG] sections (case insensitive for tag, but we upper it)
    # Matches [TAG] followed by text until next [TAG] or end
    pattern = r'\[([A-Za-z0-9_]+)\](.*?)(?=\n*\[[A-Za-z0-9_]+\]|$)'
    matches = list(re.finditer(pattern, script_text, re.DOTALL | re.IGNORECASE))

    segments = []
    if matches:
        for match in matches:
            speaker = match.group(1).upper().strip()
            text = match.group(2).strip()
            if text:
                segments.append({
                    "speaker": speaker,
                    "text": text,
                    "original_tag": f"[{match.group(1)}]"
                })
    else:
        # No tags found — treat entire script as default speaker
        segments.append({
            "speaker": "default",
            "text": script_text,
            "original_tag": ""
        })

    return segments


def split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> List[str]:
    """Intelligent chunking (paragraphs → sentences). Never mid-sentence."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                chunks.append(current)
            current = para
            while len(current) > max_chars:
                sentences = re.split(r'(?<=[.!?])\s+', current)
                temp = ""
                for sent in sentences:
                    if len(temp) + len(sent) + 1 <= max_chars:
                        temp += (" " if temp else "") + sent
                    else:
                        break
                if temp:
                    chunks.append(temp)
                    current = current[len(temp):].strip()
                else:
                    # Fallback: hard split (rare)
                    chunks.append(current[:max_chars])
                    current = current[max_chars:].strip()
    if current:
        chunks.append(current)
    return chunks


def generate_audio_segment(
    client: ElevenLabs,
    text: str,
    voice_id: str,
    model_id: str,
    previous_request_ids: List[str] = None,
    stability: float = STABILITY,
    similarity_boost: float = SIMILARITY_BOOST,
    style: float = STYLE,
    use_speaker_boost: bool = USE_SPEAKER_BOOST
) -> Tuple[bytes, Optional[str]]:
    """Generate one chunk. Returns (audio_bytes, request_id)."""
    if previous_request_ids is None:
        previous_request_ids = []

    try:
        with client.text_to_speech.with_raw_response.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            previous_request_ids=previous_request_ids[-3:] if previous_request_ids else None,  # max 3
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost
        ) as response:
            request_id = response._response.headers.get("request-id")
            audio_bytes = b"".join(chunk for chunk in response.data)
            return audio_bytes, request_id
    except Exception as e:
        print(f"\n❌ Generation error for voice {voice_id[:8]}...: {e}")
        raise


def create_srt_content(words: List) -> str:
    """Create well-formatted SRT from ElevenLabs word alignment list."""
    if not words:
        return ""

    def format_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    subtitles = []
    current_words = []
    current_start = 0.0
    MAX_DUR = 7.0
    MAX_CHARS = 42 * 2  # ~2 lines

    for i, word in enumerate(words):
        if not current_words:
            current_start = word.start

        current_words.append(word.text)
        duration = word.end - current_start
        char_count = len(" ".join(current_words))

        # Decide to break
        should_break = False
        if duration > MAX_DUR and len(current_words) >= 3:
            should_break = True
        elif char_count > MAX_CHARS and len(current_words) >= 4:
            should_break = True
        elif i == len(words) - 1:
            should_break = True

        if should_break:
            end_time = current_words and words[i].end or current_start + 1.0
            text = " ".join(current_words)
            subtitles.append((current_start, end_time, text))
            current_words = []
            current_start = word.end if i + 1 < len(words) else word.end

    # Build SRT string
    srt_lines = []
    for idx, (start, end, text) in enumerate(subtitles, 1):
        srt_lines.append(str(idx))
        srt_lines.append(f"{format_time(start)} --> {format_time(end)}")
        srt_lines.append(text)
        srt_lines.append("")  # blank line

    return "\n".join(srt_lines)


def create_vtt_content(words: List) -> str:
    """Create VTT from same word list (YouTube also accepts VTT)."""
    if not words:
        return "WEBVTT\n\n"

    def format_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    vtt = ["WEBVTT", ""]

    current_words = []
    current_start = 0.0
    MAX_DUR = 7.0
    MAX_CHARS = 42 * 2

    for i, word in enumerate(words):
        if not current_words:
            current_start = word.start
        current_words.append(word.text)
        duration = word.end - current_start
        char_count = len(" ".join(current_words))

        should_break = False
        if duration > MAX_DUR and len(current_words) >= 3:
            should_break = True
        elif char_count > MAX_CHARS and len(current_words) >= 4:
            should_break = True
        elif i == len(words) - 1:
            should_break = True

        if should_break:
            end_time = word.end
            text = " ".join(current_words)
            vtt.append(f"{format_time(current_start)} --> {format_time(end_time)}")
            vtt.append(text)
            vtt.append("")
            current_words = []
            current_start = end_time

    return "\n".join(vtt)


def generate_subtitles(client: ElevenLabs, mp3_path: Path, full_text: str, base_name: str):
    """Generate SRT and VTT using Forced Alignment on the final audio."""
    print("📝 Generating subtitles with Forced Alignment...")
    try:
        with open(mp3_path, "rb") as audio_file:
            alignment = client.forced_alignment.create(file=audio_file, text=full_text)

        words = alignment.words
        if not words:
            print("⚠️  No word alignment returned. Skipping subtitles.")
            return

        srt_content = create_srt_content(words)
        vtt_content = create_vtt_content(words)

        srt_path = OUTPUT_DIR / f"{base_name}.srt"
        vtt_path = OUTPUT_DIR / f"{base_name}.vtt"

        srt_path.write_text(srt_content, encoding="utf-8")
        vtt_path.write_text(vtt_content, encoding="utf-8")

        print(f"✅ Subtitles created: {srt_path.name} + {vtt_path.name} ({len(words)} words aligned)")
    except Exception as e:
        print(f"⚠️  Subtitle generation failed: {e}")
        print("   (You can still use the MP3. Forced Alignment requires good audio-text match.)")


def process_single_script(
    client: ElevenLabs,
    script_path: Path,
    voices: Dict[str, str],
    generate_subs: bool = True
) -> Optional[Path]:
    """Process one script file → final MP3 (+ optional subs). Returns output MP3 path or None."""
    print(f"\n📄 Processing: {script_path.name}")
    script_text = script_path.read_text(encoding="utf-8")

    segments = parse_script_for_voices(script_text)
    if not segments:
        print("⚠️  Script is empty after parsing.")
        return None

    print(f"   Found {len(segments)} speaker segment(s)")

    # Expand long segments into sub-chunks (keeps same speaker for stitching)
    all_chunks = []  # list of (speaker, chunk_text, voice_id)
    for seg in segments:
        speaker = seg["speaker"]
        voice_id = voices.get(speaker) or voices.get("default") or DEFAULT_VOICE_ID
        if not voice_id:
            print(f"❌ No voice ID found for speaker '{speaker}' or default.")
            return None

        sub_chunks = split_into_chunks(seg["text"])
        for chunk in sub_chunks:
            all_chunks.append((speaker, chunk, voice_id))

    print(f"   Total chunks to generate: {len(all_chunks)}")

    # Per-speaker request history for stitching
    speaker_request_history: Dict[str, List[str]] = defaultdict(list)

    segment_files = []
    full_text_parts = []

    pbar = tqdm(all_chunks, desc="Generating audio", unit="chunk")
    for idx, (speaker, chunk_text, voice_id) in enumerate(pbar, 1):
        prev_ids = speaker_request_history[speaker]
        try:
            audio_bytes, req_id = generate_audio_segment(
                client, chunk_text, voice_id, MODEL_ID, previous_request_ids=prev_ids
            )
            if req_id:
                speaker_request_history[speaker].append(req_id)

            # Save temp segment
            seg_path = TEMP_DIR / f"seg_{idx:04d}_{speaker}.mp3"
            seg_path.write_bytes(audio_bytes)
            segment_files.append((seg_path, speaker))

            full_text_parts.append(chunk_text)
        except Exception as e:
            print(f"\n❌ Failed on chunk {idx}: {e}")
            return None

    pbar.close()

    if not segment_files:
        print("❌ No audio generated.")
        return None

    # === CONCATENATE with smart pauses between speakers ===
    print("🔗 Merging audio segments...")
    final_audio = AudioSegment.empty()
    prev_speaker = None

    for seg_path, speaker in segment_files:
        audio = AudioSegment.from_mp3(seg_path)
        if prev_speaker is not None and speaker != prev_speaker:
            final_audio += AudioSegment.silent(duration=350)  # natural turn pause
        final_audio += audio
        prev_speaker = speaker

    base_name = script_path.stem
    final_mp3 = OUTPUT_DIR / f"{base_name}.mp3"
    final_audio.export(final_mp3, format="mp3", bitrate="192k")
    print(f"✅ Final audio saved: {final_mp3}")

    # Cleanup temp segments
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(exist_ok=True)  # recreate for next script if batch

    full_text = "\n\n".join(full_text_parts)

    if generate_subs:
        generate_subtitles(client, final_mp3, full_text, base_name)

    return final_mp3


def main():
    parser = argparse.ArgumentParser(
        description="ElevenLabs Voice Pro - Multi-Voice + Auto Subtitles"
    )
    parser.add_argument("script", nargs="?", default="script.txt",
                        help="Path to script file (default: script.txt)")
    parser.add_argument("--batch", action="store_true",
                        help="Process all .txt files in scripts/ folder")
    parser.add_argument("--no-subtitles", action="store_true",
                        help="Skip automatic SRT/VTT generation")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show how the script would be split without generating audio")
    args = parser.parse_args()

    print_header()
    validate_config()

    client = ElevenLabs(api_key=API_KEY)
    voices = load_voices()

    generate_subs = not args.no_subtitles

    if args.dry_run:
        print("🧪 DRY RUN MODE — No API calls will be made\n")
        print("Dry-run preview coming in next update. For now, just run without --dry-run on a short script first.")
        return

    if args.batch:
        if not SCRIPTS_DIR.exists():
            print(f"❌ scripts/ folder not found.")
            return
        scripts = list(SCRIPTS_DIR.glob("*.txt"))
        if not scripts:
            print("No .txt files found in scripts/")
            return
        print(f"📦 Batch mode: {len(scripts)} scripts found\n")
        for script_path in scripts:
            process_single_script(client, script_path, voices, generate_subs)
    else:
        script_path = Path(args.script)
        if not script_path.exists():
            print(f"❌ Script not found: {script_path}")
            print("   Create script.txt or pass path as argument.")
            return
        process_single_script(client, script_path, voices, generate_subs)

    print("\n🎉 Done! Check the outputs/ folder.")
    print("   Tip: Use your own cloned voice + these features = high retention + monetization safe.")


if __name__ == "__main__":
    main()
