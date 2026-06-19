# ElevenLabs Voice Pro — Multi-Voice + Emotion Tags + Smart Chapters

**Generate professional, natural-sounding voice-overs from your full YouTube scripts — automatically.**

This tool supports **Multi-Voice Character Switching**, **inline Emotion & Style Tags**, **Smart Chapter detection**, **Automatic SRT/VTT Subtitles**, and intelligent long-script handling with Request Stitching.

Perfect for faceless YouTube channels, storytelling, educational content, dialogue-style videos, and creators who want premium results without recording every take.

---

## ✅ What This Tool Actually Does

1. Takes your video script (text file) — supports [SPEAKER] tags, [excited] emotion tags, [pause Xs], and ## Chapter headings
2. Converts it to high-quality MP3 voice-over using **your own cloned voice** (or multiple voices)
3. Automatically detects chapters and outputs **separate chapter MP3s + one full merged audio**
4. Applies emotion/style settings per section for more expressive delivery
5. Uses Request Stitching (per speaker) so long content flows naturally
6. Generates perfect timed **SRT + VTT subtitles** automatically using ElevenLabs Forced Alignment
7. Supports batch processing of multiple scripts

**Result**: Professional, expressive voice-overs that sound like you recorded everything in one perfect session — with chapters and subtitles ready for YouTube.

---

## 🚀 Quick Start (5 minutes)

### 1. Install
```bash
pip install -r requirements.txt
```

### 2. Set up your credentials
Create a file called `.env` in the same folder and add:

```env
ELEVENLABS_API_KEY=sk_your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
```

**How to get your Voice ID**:
- Go to [ElevenLabs](https://elevenlabs.io) → Voices tab
- Click on your cloned voice
- Copy the long ID at the top (example: `21m00Tcm4TlvDq8ikWAM`)

### 3. Add your script
- **Single script**: Edit `script.txt` and paste your full video script
- **Multiple scripts (Batch)**: Put `.txt` files inside the `scripts/` folder

### 4. Generate audio

**Single script (recommended for first test):**
```bash
python generate_audio.py
```

**Quick test with text directly:**
```bash
python generate_audio.py "Hello, this is a test of my cloned voice."
```

**Batch mode (process all scripts in scripts/ folder):**
```bash
python generate_audio.py --batch
```

**Dry run (see how it will split without spending credits):**
```bash
python generate_audio.py --dry-run
```

All finished MP3 files appear in the `outputs/` folder.

---

## 📏 Long Script Support — How It Works

ElevenLabs' fastest model (`Flash v2.5`) supports up to **~40,000 characters** (~40 minutes of audio) per single generation.

Most YouTube scripts are shorter than this, but some storytelling or long-form videos go longer.

**This tool solves it automatically:**

- Splits your script at paragraph → sentence boundaries (never mid-sentence)
- Uses **Request Stitching** (ElevenLabs official method) — each new chunk knows exactly what was said before
- This keeps the voice tone, emotion, and pacing consistent from start to finish
- Finally merges everything into **one single seamless MP3**

You get natural, professional results even on 30–60+ minute scripts.

---

## 📦 Batch Processing

Want to generate voice-overs for 5, 10, or 20 videos at once?

1. Create `.txt` files for each video inside the `scripts/` folder
2. Run:
   ```bash
   python generate_audio.py --batch
   ```
3. All MP3s are saved in `outputs/` with matching filenames.

Perfect for batch-producing a whole week's content in one go.

---

## ⚙️ Customization (.env file)

You can tweak these settings:

| Variable              | Default          | What it does |
|-----------------------|------------------|--------------|
| `ELEVENLABS_MODEL_ID` | eleven_flash_v2_5 | Fast & high limit |
| `MAX_CHUNK_CHARS`     | 35000            | Safety buffer under 40k limit |
| `STABILITY`           | 0.75             | Higher = more consistent voice |
| `SIMILARITY_BOOST`    | 0.85             | How closely it matches your clone |
| `STYLE`               | 0.0              | Exaggeration of style (0 = natural) |

---

## 💰 Cost & ElevenLabs Usage

- You pay ElevenLabs per character generated (same as using their website)
- Flash v2.5 is one of the more affordable models
- Long scripts cost more because they contain more characters
- The tool shows you an estimated cost before generating
- Always check your ElevenLabs dashboard for current pricing and credits

**Tip**: Start with short scripts to test everything works before doing long ones.

---

## 🛠️ Troubleshooting

| Problem                        | Solution |
|--------------------------------|----------|
| "Invalid API key"              | Check your `.env` file |
| "Voice not found"              | Double-check `ELEVENLABS_VOICE_ID` |
| Generation fails on long script| Reduce `MAX_CHUNK_CHARS` to 30000 |
| Audio sounds robotic           | Increase `SIMILARITY_BOOST` or re-clone with more audio |
| pydub / ffmpeg error           | Install ffmpeg: `brew install ffmpeg` (Mac) or `sudo apt install ffmpeg` (Linux) |

Still stuck? Open an issue or check the ElevenLabs status page.

---

## 📜 License & Rights

- You can use this tool for personal and commercial projects (YouTube, client work, courses, etc.)
- You **cannot** resell or redistribute the Python code itself
- Generated audio files are yours to use however you want
- You are responsible for following ElevenLabs Terms of Service and YouTube monetization rules

---

## ❓ Does This Actually Work?

**Yes.**

The long-script chunking + Request Stitching method is the **official technique recommended by ElevenLabs** for maintaining natural prosody in long-form content (see their documentation on Request Stitching).

This exact approach is used by many professional creators for audiobooks, podcasts, and long YouTube videos.

**Important honesty**:
- It works **when you have a valid API key + cloned voice**
- Always test with a 30–60 second script first
- The more high-quality audio you used when cloning your voice, the better the results
- ElevenLabs is a paid service — you will be charged for the characters used

If something doesn't work, 95% of the time it's configuration (wrong Voice ID or no credits). The code itself follows ElevenLabs' own examples.

---

## 🆕 New in This Version: Multi-Voice + Automatic Subtitles

### Multi-Voice / Character Switching
You can now have different voices (narrator, expert, guest, child, etc.) in the **same video** automatically.

**How to use:**
1. Create `voices.json` (copy from `voices.json.example`)
2. In your script, use tags like:
   ```
   [NARRATOR]
   Welcome to the video...

   [EXPERT]
   In my experience...
   ```
3. The tool automatically:
   - Switches voices
   - Adds natural pauses between different speakers
   - Maintains prosody **within each speaker** using Request Stitching

**Example voices.json:**
```json
{
  "default": "your_main_voice_id",
  "NARRATOR": "your_narrator_id",
  "EXPERT": "your_expert_id"
}
```

### Automatic SRT + VTT Subtitles
After generating the MP3, the tool uses ElevenLabs **Forced Alignment** to create perfectly timed subtitles.

- `yourscript.srt` — ready for YouTube
- `yourscript.vtt` — also supported by YouTube & most editors

**Benefits:**
- Massive SEO boost (YouTube loves captions)
- Better retention (viewers read along)
- Accessibility + repurposing for Shorts/Reels

Just run normally — subtitles are generated by default. Use `--no-subtitles` to skip.

---

## 💡 Pro Tips for Best Results

1. Write in a natural, conversational tone (the way you actually speak)
2. Use short paragraphs — it helps the chunking algorithm
3. After generation, do light editing in Descript, CapCut, or Audacity (remove breaths, add music)
4. For faceless channels: combine with good stock footage + captions
5. Re-clone your voice every 6–12 months as the models improve

---

**You're ready to create consistent, high-quality voice-overs at scale.**

Run your first test now:
```bash
python generate_audio.py
```

Then move on to `--batch` when you're comfortable.

Happy creating! 🎬
