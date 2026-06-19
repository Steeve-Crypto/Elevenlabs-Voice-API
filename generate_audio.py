#!/usr/bin/env python3
"""
ElevenLabs Voice Pro - Multi-Voice + Emotion Tags + Smart Chapters Edition
Professional voice-over generator with:
- Automatic long-script chunking with Request Stitching (per-speaker)
- Multi-Voice / Character Switching via [SPEAKER] tags
- Per-section Emotion & Style control via inline tags: [excited], [whisper], [calm]...
- Smart Chapter detection (## Heading, Chapter 1, etc.) → separate + full MP3s
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

# Emotion / Style presets — map tags like [excited] to generation parameters
EMOTION_PRESETS: Dict[str, Dict] = {
    "excited": {"style": 0.65, "speed": 1.08, "stability": 0.65},
    "whisper": {"stability": 0.35, "style": 0.15, "speed": 0.90},
    "dramatic": {"style": 0.78, "stability": 0.55, "speed": 0.95},
    "calm": {"stability": 0.92, "style": 0.08, "speed": 0.88},
    "energetic": {"style": 0.55, "speed": 1.12, "stability": 0.70},
    "serious": {"stability": 0.88, "style": 0.18, "speed": 0.92},
    "sad": {"stability": 0.80, "style": 0.25, "speed": 0.85},
    "happy": {"style": 0.50, "speed": 1.05, "stability": 0.75},
    "pause": {"pause_seconds": 0},  # special, handled in merging
}

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)
SCRIPTS_DIR = Path("scripts")
TEMP_DIR = Path(tempfile.mkdtemp(prefix="elevenlabs_segments_"))

VOICES_FILE = Path("voices.json")


def print_header():
    print("\n" + "="*72)
    print("🎙️  ElevenLabs Voice Pro — Multi-Voice + Emotion Tags + Smart Chapters")
    print("   Long Script • Character Switching • Emotion Control • Auto Chapters • SRT/VTT")
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


def parse_script_for_voices_and_emotions(script_text: str) -> List[Dict]:
    """
    Advanced parser supporting:
    - [SPEAKER] tags (e.g. [NARRATOR], [EXPERT])
    - Inline emotion/style tags: [excited], [whisper], [dramatic], [calm], [happy], [sad], [energetic], [serious]
    - Pause tags: [pause 2s] or [pause 1.5]
    Returns list of atomic blocks:
    [{"type": "speech", "speaker": "NARRATOR", "emotion": "excited", "text": "clean text"},
     {"type": "pause", "seconds": 2.0}]
    Tags are removed from spoken text. Unknown tags treated as speaker change.
    """
    script_text = script_text.strip()
    if not script_text:
        return []

    blocks = []
    last_end = 0
    current_speaker = "default"
    current_emotion = None

    tag_pattern_full = r'\[([A-Za-z0-9_]+(?:\s+\d+(?:\.\d+)?s?)?)\]'
    for match in re.finditer(tag_pattern_full, script_text, re.IGNORECASE):
        # Text before this tag
        preceding_text = script_text[last_end:match.start()].strip()
        if preceding_text:
            blocks.append({
                "type": "speech",
                "speaker": current_speaker,
                "emotion": current_emotion,
                "text": preceding_text
            })

        tag_content = match.group(1).strip().lower()
        tag_upper = match.group(1).strip().upper()

        if tag_content.startswith("/"):
            # Ignore closing tags like [/whisper] for now (simple state machine)
            last_end = match.end()
            continue

        # Decide if it's a known emotion/pause or a speaker tag
        is_pause = tag_content.startswith("pause")
        is_known_emotion = tag_content.split()[0] in EMOTION_PRESETS and tag_content.split()[0] != "pause"

        if is_pause:
            seconds = 0.8
            m = re.search(r'(\d+(?:\.\d+)?)', tag_content)
            if m:
                seconds = float(m.group(1))
            blocks.append({"type": "pause", "seconds": seconds})
        elif is_known_emotion:
            current_emotion = tag_content.split()[0]
        else:
            # Speaker change
            current_speaker = tag_upper
            current_emotion = None

        last_end = match.end()

    # Remaining text after last tag
    remaining = script_text[last_end:].strip()
    if remaining:
        blocks.append({
            "type": "speech",
            "speaker": current_speaker,
            "emotion": current_emotion,
            "text": remaining
        })

    # Fallback if no tags at all
    if not blocks:
        blocks.append({
            "type": "speech",
            "speaker": "default",
            "emotion": None,
            "text": script_text
        })

    # Clean empty speech blocks
    blocks = [b for b in blocks if b["type"] == "pause" or (b.get("text") and b["text"].strip())]
    return blocks


def split_into_chapters(script_text: str) -> List[Dict]:
    """
    Detect smart chapters using ## Heading, # Heading, Chapter X, Part X, etc.
    Returns list of {"title": "Chapter 1: Intro", "text": "..."}
    If no chapters found, returns one chapter with the full text.
    """
    script_text = script_text.strip()
    if not script_text:
        return [{"title": "Full Script", "text": ""}]

    # Common chapter patterns
    chapter_patterns = [
        r'^#{1,2}\s+(.+)$',                    # ## Chapter Title or # Title
        r'^(Chapter|Part|Section)\s+\d+[:\s]*(.*)$',  # Chapter 1: Foo
        r'^(Episode|Day)\s+\d+[:\s]*(.*)$',
    ]

    lines = script_text.splitlines(keepends=True)
    chapters = []
    current_title = "Full Script"
    current_text = ""

    found_chapter = False
    for line in lines:
        matched = False
        for pat in chapter_patterns:
            m = re.match(pat, line.strip(), re.IGNORECASE)
            if m:
                if current_text.strip():
                    chapters.append({"title": current_title, "text": current_text.strip()})
                # Build nice title
                if m.lastindex and m.group(1):
                    current_title = f"{m.group(1).title()} {m.group(2).strip()}" if m.lastindex > 1 else m.group(1).title()
                else:
                    current_title = line.strip().lstrip('#').strip()
                current_text = ""
                found_chapter = True
                matched = True
                break
        if not matched:
            current_text += line

    if current_text.strip():
        chapters.append({"title": current_title, "text": current_text.strip()})

    if not found_chapter or len(chapters) == 0:
        return [{"title": "Full Script", "text": script_text}]

    return chapters


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
    speed: float = 1.0,
    use_speaker_boost: bool = USE_SPEAKER_BOOST
) -> Tuple[bytes, Optional[str]]:
    """Generate one chunk. Returns (audio_bytes, request_id). Supports speed and per-chunk params."""
    if previous_request_ids is None:
        previous_request_ids = []

    try:
        with client.text_to_speech.with_raw_response.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            previous_request_ids=previous_request_ids[-3:] if previous_request_ids else None,
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            speed=speed,
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
    """Process one script file with full support for chapters, multi-voice, emotion tags, pauses.
    Outputs per-chapter MP3s (if chapters found) + one full merged MP3 + subtitles.
    Returns path to the full MP3 or None on failure.
    """
    print(f"\n📄 Processing: {script_path.name}")
    script_text = script_path.read_text(encoding="utf-8")

    # === Chapter detection ===
    chapters = split_into_chapters(script_text)
    has_chapters = len(chapters) > 1 or chapters[0]["title"] != "Full Script"

    if has_chapters:
        print(f"   📖 Detected {len(chapters)} chapters/sections")

    base_name = script_path.stem
    all_chapter_audios: List[AudioSegment] = []
    all_full_text_parts: List[str] = []
    chapter_mp3_paths: List[Path] = []

    # Per-speaker stitching history (global across chapters for consistent voice)
    speaker_request_history: Dict[str, List[str]] = defaultdict(list)

    for ch_idx, chapter in enumerate(chapters, 1):
        ch_title = chapter["title"]
        ch_text = chapter["text"]
        if not ch_text.strip():
            continue

        print(f"\n   ▶️  Chapter {ch_idx}: {ch_title[:60]}{'...' if len(ch_title) > 60 else ''}")

        blocks = parse_script_for_voices_and_emotions(ch_text)
        if not blocks:
            continue

        # Count speech vs pause for logging
        speech_blocks = [b for b in blocks if b["type"] == "speech"]
        print(f"      Found {len(speech_blocks)} speech segment(s) with emotion/pause support")

        # Build generation tasks: expand long speech into chunks, apply emotion params
        generation_tasks = []  # list of (speaker, chunk_text, voice_id, emotion, params_dict)
        for block in blocks:
            if block["type"] == "pause":
                generation_tasks.append(("__PAUSE__", block["seconds"], None, None, None))
                continue

            speaker = block["speaker"]
            emotion = block.get("emotion")
            text = block["text"]

            voice_id = voices.get(speaker) or voices.get("default") or DEFAULT_VOICE_ID
            if not voice_id:
                print(f"❌ No voice ID found for speaker '{speaker}'.")
                return None

            # Base params + emotion override
            params = {
                "stability": STABILITY,
                "similarity_boost": SIMILARITY_BOOST,
                "style": STYLE,
                "speed": 1.0,
                "use_speaker_boost": USE_SPEAKER_BOOST
            }
            if emotion and emotion in EMOTION_PRESETS:
                preset = EMOTION_PRESETS[emotion]
                for k, v in preset.items():
                    if k in params:
                        params[k] = v
                    elif k == "pause_seconds":
                        pass  # handled separately

            sub_chunks = split_into_chunks(text)
            for chunk in sub_chunks:
                generation_tasks.append((speaker, chunk, voice_id, emotion, params))

        print(f"      Total generation tasks (chunks + pauses): {len(generation_tasks)}")

        # Generate audio for this chapter
        ch_segment_files: List[Tuple[Path, str, Optional[str]]] = []  # (path, speaker, emotion)
        ch_text_parts = []

        pbar = tqdm(generation_tasks, desc=f"   Chapter {ch_idx}", unit="task", leave=False)
        for idx, task in enumerate(pbar, 1):
            if task[0] == "__PAUSE__":
                _, seconds, _, _, _ = task
                # We will insert silence later during merge
                ch_segment_files.append((None, "__PAUSE__", seconds))
                continue

            speaker, chunk_text, voice_id, emotion, params = task
            prev_ids = speaker_request_history[speaker]

            try:
                audio_bytes, req_id = generate_audio_segment(
                    client,
                    chunk_text,
                    voice_id,
                    MODEL_ID,
                    previous_request_ids=prev_ids,
                    stability=params["stability"],
                    similarity_boost=params["similarity_boost"],
                    style=params["style"],
                    speed=params.get("speed", 1.0),
                    use_speaker_boost=params.get("use_speaker_boost", True)
                )
                if req_id:
                    speaker_request_history[speaker].append(req_id)

                seg_path = TEMP_DIR / f"ch{ch_idx}_seg{idx:04d}_{speaker}.mp3"
                seg_path.write_bytes(audio_bytes)
                ch_segment_files.append((seg_path, speaker, emotion))
                ch_text_parts.append(chunk_text)
            except Exception as e:
                print(f"\n❌ Failed on chapter {ch_idx} task {idx}: {e}")
                return None
        pbar.close()

        if not ch_segment_files:
            continue

        # Merge chapter audio (with pauses and emotion-aware but no extra pause needed)
        print(f"   🔗 Merging chapter {ch_idx}...")
        ch_audio = AudioSegment.empty()
        prev_speaker = None

        for item in ch_segment_files:
            if item[0] is None:  # pause
                _, _, seconds = item
                ch_audio += AudioSegment.silent(duration=int(seconds * 1000))
                continue

            seg_path, speaker, emotion = item
            audio = AudioSegment.from_mp3(seg_path)
            if prev_speaker is not None and speaker != prev_speaker:
                ch_audio += AudioSegment.silent(duration=350)  # speaker turn pause
            ch_audio += audio
            prev_speaker = speaker

        # Save chapter MP3
        safe_title = re.sub(r'[^A-Za-z0-9_-]+', '_', ch_title)[:40]
        ch_mp3_name = f"{base_name}_ch{ch_idx:02d}_{safe_title}.mp3"
        ch_mp3_path = OUTPUT_DIR / ch_mp3_name
        ch_audio.export(ch_mp3_path, format="mp3", bitrate="192k")
        print(f"   ✅ Chapter saved: {ch_mp3_name}")
        chapter_mp3_paths.append(ch_mp3_path)
        all_chapter_audios.append(ch_audio)
        all_full_text_parts.extend(ch_text_parts)

    # === FINAL FULL AUDIO (merge all chapters with chapter break pauses) ===
    print("\n🔗 Creating full merged audio...")
    if not all_chapter_audios:
        print("❌ No audio generated for any chapter.")
        return None

    final_audio = AudioSegment.empty()
    for i, ch_audio in enumerate(all_chapter_audios):
        if i > 0:
            final_audio += AudioSegment.silent(duration=1200)  # ~1.2s break between chapters
        final_audio += ch_audio

    full_mp3 = OUTPUT_DIR / f"{base_name}_full.mp3"
    final_audio.export(full_mp3, format="mp3", bitrate="192k")
    print(f"✅ Full audio saved: {full_mp3.name}")

    # Also save a clean "main" output without _full suffix for convenience
    main_mp3 = OUTPUT_DIR / f"{base_name}.mp3"
    final_audio.export(main_mp3, format="mp3", bitrate="192k")
    print(f"✅ Main output also saved as: {main_mp3.name}")

    # Cleanup
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(exist_ok=True)

    full_text = "\n\n".join(all_full_text_parts)

    if generate_subs and full_text.strip():
        generate_subtitles(client, main_mp3, full_text, base_name)

    if has_chapters:
        print(f"\n📚 Generated {len(chapter_mp3_paths)} chapter files + full audio + subtitles")

    return main_mp3


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
        print("🧪 DRY RUN MODE — No API calls or credits used\n")
        script_text = Path(args.script if not args.batch else "script.txt").read_text(encoding="utf-8") if Path(args.script if not args.batch else "script.txt").exists() else ""
        if script_text:
            chapters = split_into_chapters(script_text)
            blocks = parse_script_for_voices_and_emotions(script_text)
            speakers = set(b.get("speaker", "default") for b in blocks if b["type"] == "speech")
            emotions = set(b.get("emotion") for b in blocks if b.get("emotion"))
            pauses = [b for b in blocks if b["type"] == "pause"]
            print(f"📖 Chapters detected: {len(chapters)}")
            for i, ch in enumerate(chapters, 1):
                print(f"   {i}. {ch['title'][:70]}")
            print(f"🎭 Speakers found: {', '.join(sorted(speakers))}")
            if emotions:
                print(f"🎨 Emotions detected: {', '.join(sorted(emotions))}")
            if pauses:
                print(f"⏸️  Pause tags: {len(pauses)} (will insert natural silences)")
            print(f"📝 Total speech blocks: {len([b for b in blocks if b['type']=='speech'])}")
            print("\n✅ Dry-run complete. Run without --dry-run to generate audio.")
        else:
            print("No script found for preview.")
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
