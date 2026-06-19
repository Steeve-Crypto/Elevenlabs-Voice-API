# ElevenLabs Voice API Project

A simple, ready-to-use Python tool to turn your video script into high-quality voice-over audio using **your own cloned voice** from ElevenLabs.

## ✅ Quick Setup (5 minutes)

1. **Install requirements**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create `.env` file** (in the same folder)
   Create a new file named `.env` and add:
   ```
   ELEVENLABS_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ELEVENLABS_VOICE_ID=your_voice_id_here
   ```
   - Get your **API Key**: ElevenLabs dashboard → Profile icon (bottom left) → API Keys
   - Get your **Voice ID**: ElevenLabs → Voices tab → Click your cloned voice → Copy the long ID string (example: `21m00Tcm4TlvDq8ikWAM`)

3. **Add your VIDEO SCRIPT**
   - **Recommended (easiest for long scripts)**: Create a file called `script.txt` in this folder and paste your full video script into it.
   - Or pass it directly when running the command (see Usage below).

## 🚀 How to Use

### Option 1: Using `script.txt` (Best for video scripts)
1. Create `script.txt` in this folder.
2. Paste your entire video script inside `script.txt` and save.
3. Run:
   ```bash
   python generate_audio.py
   ```
   The audio will be saved as `output.mp3`.

### Option 2: Pass script directly in terminal
```bash
python generate_audio.py "Hello everyone, welcome to my video about..." my_voiceover.mp3
```

## 📍 Where to Put Things

| What              | Where to Put It                                      | How |
|-------------------|------------------------------------------------------|-----|
| **Voice ID**      | In the `.env` file (recommended) or inside `generate_audio.py` | Replace `your_cloned_voice_id_here` or set `ELEVENLABS_VOICE_ID=...` in `.env` |
| **Video Script**  | Create `script.txt` in the project folder (recommended) | Paste your full narration/script into the text file |
| **API Key**       | In the `.env` file                                   | `ELEVENLABS_API_KEY=sk-...` |

## Features
- Uses the fast **eleven_flash_v2_5** model (supports up to ~40 minutes of audio in one go)
- Works great with your cloned voice
- Simple and free to run locally
- Handles long scripts

## Notes for YouTube
- Since you're using **your own cloned voice**, YouTube does **not** require any AI disclosure for monetization.
- Just make sure your overall content is original and valuable.

## Need help?
- Find your Voice ID: ElevenLabs dashboard → Voices → select your voice → the ID is displayed at the top.
- For very long scripts: Split into 2-3 parts, generate separate MP3s, then combine them with ffmpeg.

Enjoy creating your voice-overs! 🎙️
