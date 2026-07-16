# ClipCatcher

Watches a Twitch stream's live chat in real time, detects hype spikes, and automatically saves video clips locally. One-click TikTok export (9:16 crop) included.

---

## Quick start

### 1. Install Python dependencies

```bash
pip install streamlink requests
```

Tkinter is built into Python — no install needed.

### 2. Install ffmpeg

**Windows:**
1. Download from https://ffmpeg.org/download.html (get the "Windows builds" zip)
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your system PATH
   - Search "environment variables" in Start → Edit System Environment Variables → Path → New → `C:\ffmpeg\bin`
4. Restart your terminal and verify: `ffmpeg -version`

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg    # Debian/Ubuntu
sudo dnf install ffmpeg    # Fedora
```

### 3. Run

```bash
python main.py
```

---

## How it works

1. **Paste a Twitch channel URL** (e.g. `twitch.tv/xqc`) and click Connect
2. ClipCatcher connects to Twitch IRC (no API key needed — anonymous read access)
3. It monitors the live chat message rate every 500ms
4. When messages per second exceeds your threshold, it saves a clip
5. The clip captures the last N seconds before the spike + N seconds after
6. All clips are saved as `.mp4` to `~/Videos/ClipCatcher`

### Architecture

```
Twitch IRC  ──(TCP socket)──▶  TwitchChatMonitor  ──rate──▶  HypeDetector
                                                                    │
                                                              triggers clip
                                                                    │
streamlink  ──(pipe)──▶  ffmpeg (segments)  ──────────▶  StreamRecorder
                              (rolling buffer)                      │
                                                            saves .mp4 clip
```

---

## Settings

| Setting | Default | Description |
|---|---|---|
| Spike sensitivity | 8 msg/s | Messages per second to trigger a clip |
| Buffer before | 15s | Seconds captured before the hype peak |
| Buffer after | 10s | Seconds captured after the hype peak |
| Cooldown | 30s | Gap between clips (prevents duplicate clips) |
| Quality | best | Stream quality (best, 1080p, 720p, 480p…) |
| Save folder | ~/Videos/ClipCatcher | Where .mp4 files are saved |

---

## TikTok export

Each clip card has a **📱 Export for TikTok** button. This runs:

```
ffmpeg -vf "crop=ih*9/16:ih,scale=1080:1920" ...
```

It crops the 16:9 stream to portrait 9:16 from the centre, scales to 1080×1920, and saves to `~/Videos/ClipCatcher/tiktok_exports/`.

Then upload that file directly to TikTok on desktop or phone.

---

## Troubleshooting

**"Channel not found" even though it exists**
→ Try the bare channel name without `twitch.tv/`

**No clips being saved (chat works but no video)**
→ Check that streamlink and ffmpeg are both installed and in your PATH
→ Open Settings → Required tools to see the status

**streamlink error "No streams found"**
→ The channel isn't currently live

**Clips are very short**
→ The rolling buffer needs a few seconds to fill — connect and wait 30 seconds before the hype spike

---

## Content Engine & Auto-Shorts Pipeline

ClipCatcher includes a premium automated video generation subsystem called the **Content Engine**.

### Features

1. **Niche-Agnostic Content Engine**: Rotates templates, schedules, compiles 9:16 vertical shorts dynamically from niche JSON packs (`content_engine/niches/`).
2. **Auto-Shorts Pipeline**: Automatically center-crops widescreen Twitch clips (16:9) to portrait (9:16), transcribes audio using Gemini, burns in word-by-word highlighted subtitles, and generates viral metadata.
3. **Secure Connections**: Chat monitors connect anonymously to Twitch IRC using secure SSL/TLS sockets on port 6697.

### File Layout

```
clipcatcher/
├── main.py               ← entry point: python main.py
├── requirements.txt
├── README.md
├── app/
│   ├── gui.py            ← main window (tkinter)
│   ├── chat_monitor.py   ← Twitch IRC over secure SSL/TLS
│   ├── recorder.py       ← streamlink + ffmpeg rolling buffer + clip cutting
│   ├── hype_detector.py  ← rate monitoring + threshold + cooldown
│   └── settings.py       ← JSON config persistence
└── content_engine/
    ├── niches/           ← JSON niche packs (World Cup 2026, History, Finance)
    ├── niche_loader.py   ← dynamic niche loader & Gemini topic refilling
    ├── clip_polisher.py  ← auto-shorts vertical cropper & Gemini transcriber
    ├── engine.py         ← video pipeline coordinator
    └── scheduler.py      ← production scheduler & history tracker
```
