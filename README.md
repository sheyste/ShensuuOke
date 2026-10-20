# ShensuuOke

A desktop karaoke and media playback workstation built with Python 3.12+ and PySide6 (Qt6). Plays MIDI/KAR files through native FluidSynth with real-time soundfont switching and dynamic bass enhancement, plays audio and video tracks through FFmpeg/QtMultimedia, and routes **all playback through a unified 10-band equalizer and DSP chain**.

Includes a dual-screen karaoke display, synchronized lyric highlight engine, phone-accessible LAN remote control, and a high-performance indexed library.

---

<img width="1920" height="998" alt="image" src="https://github.com/user-attachments/assets/38913a57-fdae-47cd-a991-0595976b2806" />
<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/0dcf3de2-edbd-4077-b810-57bc032a304b" />
<img width="414" height="896" alt="IMG_2915" src="https://github.com/user-attachments/assets/d169873b-aca4-4b3b-9f42-08ee80485b10" />
<img width="414" height="896" alt="IMG_2916" src="https://github.com/user-attachments/assets/25d4667a-32c3-41f9-8062-2b5640b0f36e" />




## Key Features

- **Audio & MIDI Synthesizer Engine**:
  - Sample-accurate MIDI/KAR playback via native FluidSynth 3.x.
  - Real-time SoundFont hot-swapping without playback interruption.
  - **Bass Punch DSP**: Low-frequency harmonic saturation and punch for punchy bass drums and basslines.
  - **10-Band Equalizer**: RBJ biquad filters with persistent state, bass boost, and custom user presets.
  - Multi-format audio decoding via FFmpeg (MP3, WAV, FLAC, OGG, M4A, etc.).

- **Karaoke View & Visuals**:
  - Synchronized, continuous syllable lyric coloring (smooth progressive fill).
  - Background video playback (MP4, MKV, AVI, WebM) with seamless looping.

- **High-Performance Song Library**:
  - Instant debounced search across title, artist, filename, format, and path.
  - Stable 1-based karaoke song numbers for fast keypad selection.
  - Automated library folder watcher, duplicate detector, and clean-up for missing songs.

- **Smartphone Web Remote Control**:
  - Built-in LAN HTTP remote server; scan the on-screen QR code with any mobile device to connect.
  - Mobile keypad to queue tracks by song number with live title/artist preview.
  - Browse library songs with shuffle discovery and search.
  - View live queue status with one-tap play and remove actions.

---

## Architecture Overview

```
MidiSource (mido sequencer → FluidSynth.get_samples) ┐
                                                      ├→ Bass Punch DSP → 10-Band Equalizer → Limiter → sounddevice (PortAudio)
FileSource (FFmpeg-decoded float32 PCM)              ┘
```

| Layer | Path | Description |
|---|---|---|
| **Audio** | `app/audio/` | `audio_engine.py`, `midi_engine.py`, `fluidsynth_backend.py`, `equalizer.py` (10-band biquads + bass punch saturation), `audio_decoder.py` |
| **Library** | `app/library/` | `database.py` (SQLite with `PRAGMA user_version` migrations and stable numbering), `scanner.py`, `metadata.py` |
| **Services** | `app/services/` | `playback.py` (Qt controller), `play_queue.py`, `remote_server.py` (mobile LAN web interface), `settings.py`, `scan_worker.py` |
| **UI** | `app/ui/` | `main_window.py`, `karaoke_window.py`, `lyrics_view.py` (countdown & lyric rendering), `song_library.py` (lazy-loading table), `settings_view.py`, `equalizer_view.py`, `soundfont_manager.py` |
| **Packaging** | `packaging/` | `bump_version.py`, `build_windows.bat`, `build.ps1`, `installer.iss`, `file_version_info.txt`, `version.json` |

---

## Development Setup

### Prerequisites

- **Python 3.12+** (Windows 64-bit recommended; ensure "Add Python to PATH" is checked during installation).
- **Git** (recommended for version control and repository management).

### 1. Clone & Set Up Virtual Environment

Open a terminal (PowerShell or Command Prompt) in the project directory:

```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (CMD):
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt
```

### 2. Runtime Binaries & SoundFonts

The project stores native runtimes and soundfonts in the `runtime/` folder:

- **FluidSynth DLLs**: Native 64-bit runtime libraries reside in `runtime/fluidsynth/`.
- **FFmpeg**: Executable lives in `runtime/ffmpeg/ffmpeg.exe`. If downloaded from git as an archive, run:
  ```powershell
  Expand-Archive -Path runtime\ffmpeg\ffmpeg.zip -DestinationPath runtime\ffmpeg -Force
  ```
- **SoundFont**: The default soundfont (`runtime/soundfonts/KaraOke_King_v2.sf2`) is stored as split git parts. To extract it:
  ```powershell
  python -c "import io, zipfile; data = open(r'runtime/soundfonts/KaraOke_King_v2.zip.part1','rb').read() + open(r'runtime/soundfonts/KaraOke_King_v2.zip.part2','rb').read(); zipfile.ZipFile(io.BytesIO(data)).extractall(r'runtime/soundfonts')"
  ```
  *(Note: The build scripts unpack these automatically if missing).*

### 3. Run Application

```powershell
python main.py
```

---

## Running the Test Suite

The automated test suite contains 72 tests covering DSP filters, equalizer curves, database migrations, stable song numbering, scanner recursion, remote server endpoints, playback queue, lyrics timing, and version bumping.

```powershell
# Run all tests
pytest

# Run tests with short summary
pytest -v
```

---

## Building Standalone Executable & Installer

ShensuuOke includes automated packaging with automatic version bumping on every build.

### Build Command (Batch)

Double-click or run from terminal:
```cmd
packaging\build_windows.bat
```

### Build Command (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

### What the Build Script Does:
1. **Auto-Increments Version**: Runs `packaging/bump_version.py` to bump the patch version across `version.json`, `app/version.py`, `file_version_info.txt`, and `installer.iss`.
2. **Bundles with PyInstaller**: Uses `ShensuuOke.spec` to package the app, Qt6 plugins, SoundFonts, and runtime DLLs into `dist\ShensuuOke\`.
3. **Creates Setup Installer**: Invokes Inno Setup (if installed) to generate `dist\ShensuuOke-Setup-v<version>.exe` with desktop icons, file associations, and uninstaller.

---

## Troubleshooting

| Issue | Solution |
|---|---|
| **FluidSynth DLL not found** | Verify `runtime\fluidsynth\libfluidsynth-3.dll` exists. If using an external build, ensure both Python and DLLs are 64-bit and set the folder under *Audio Settings*. |
| **No SoundFont active** | Open *SoundFont Manager*, ensure `KaraOke_King_v2.sf2` is selected and set as default. |
| **Audio output error** | Go to *Audio Settings* and select your primary audio output device (e.g. Speakers / Headphones) and test with the 440 Hz tone button. |
| **Missing songs in library** | In *Application Settings*, click **Clean missing songs** to purge deleted or renamed files, or click **Rescan** to automatically update file paths while preserving favorites and play counts. |
| **Audio crackling / dropouts** | In *Audio Settings*, lower the output gain slightly or ensure no exclusive-mode applications are blocking PortAudio. |

---

## Third-Party Licenses

| Component | License | Notes |
|---|---|---|
| **PySide6 / Qt6** | LGPL-3.0 | Dynamically linked Qt6 binaries. |
| **FluidSynth / pyfluidsynth** | LGPL-2.1 | Native MIDI soundfont synthesizer. |
| **FFmpeg** | LGPL-2.1+ / GPL-2+ | Media decoding utility. |
| **sounddevice / PortAudio** | MIT | Real-time audio stream output. |
| **mido** | MIT | MIDI event parser and timing engine. |
| **NumPy / SciPy** | BSD-3-Clause | DSP audio filtering & biquad calculation. |
| **qrcode** | BSD | Mobile connection QR code generation. |
| **mutagen** | GPL-2.0+ | Audio metadata tag extraction. |
