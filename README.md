# ShensuuOke

A desktop karaoke application (Python 3.12+, PySide6). Plays MIDI/KAR through FluidSynth with swappable
SoundFonts, plays audio/video files through FFmpeg, and routes **everything through one shared 10-band equalizer**.

## Architecture

```
MidiSource (mido sequencer → FluidSynth.get_samples) ┐
                                                      ├→ Equalizer → volume/limiter → sounddevice (PortAudio)
FileSource (FFmpeg-decoded float32 PCM)              ┘
```

| Layer | Path | Notes |
|---|---|---|
| Audio | `app/audio/` | `equalizer.py` (RBJ biquads, scipy `sosfilt`, state kept across blocks), `fluidsynth_backend.py`, `midi_engine.py` (parser + sample-accurate sequencer), `audio_decoder.py`, `audio_engine.py` |
| Library | `app/library/` | `database.py` (SQLite, `PRAGMA user_version` migrations), `scanner.py`, `metadata.py` |
| Services | `app/services/` | `play_queue.py` (pure Python), `playback.py` (Qt controller), `scan_worker.py`, `settings.py` |
| UI | `app/ui/` | main window, library, playlists, now playing + queue, lyrics, karaoke window, EQ, SoundFont manager, settings |


## Windows setup (Windows 10/11)

1. **Python 3.12+** from python.org (tick "Add to PATH").
2. **FluidSynth** (native library, v2.x): download the Windows build from the FluidSynth GitHub releases, unzip e.g. to `C:\tools\fluidsynth`, and either add `C:\tools\fluidsynth\bin` to `PATH` **or** set that folder under *Audio Settings → FluidSynth DLL folder* (restart afterwards) **or** set the environment variable `FLUIDSYNTH_DLL_DIR`.
3. **FFmpeg**: install a build (e.g. `winget install Gyan.FFmpeg`) so `ffmpeg.exe` is on `PATH`, or set its path under *Audio Settings*.
4. Create the environment and run:
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
5. **SoundFont:** bring your own legally obtained `.sf2` (nothing is bundled). Add it in *SoundFont Manager* → *Use selected*.
6. **Songs:** *Song Library → Add folder…* (recursive) or *Add files…*, then double-click a song.

Linux (future): the code is platform-neutral apart from the DLL lookup; install `fluidsynth`, `ffmpeg` and `libportaudio2` from your package manager.

## Verifying real playback

```
python tools/make_sample_midi.py sample.kar     # creates a short KAR file with lyrics
python main.py
```
Add `sample.kar`, add your SoundFont, double-click the song: you should hear a scale and see highlighted lyrics.
Then (1) switch to a second `.sf2` mid-song — the timbre must change; (2) open *Equalizer* → *Bass Boost* — the sound must
change for both MIDI and audio files; (3) *Audio Settings → Test output* plays a 440 Hz tone through the same chain.

## Tests
```
pip install -r requirements.txt
pytest
```
Tests cover the EQ DSP, MIDI/KAR parsing and sequencing, FluidSynth backend and SoundFont switching (with a fake `fluidsynth`
module, so no native library is needed), engine callback/cleanup/error handling, SQLite + migrations, playlists, scanner
(recursion, duplicates, moved/missing files, unsupported files), queue behavior and lyric timing. GUI code is not unit-tested;
run the manual checks above.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "FluidSynth could not be loaded" | Install FluidSynth; add its `bin` folder to PATH or set it in Audio Settings; the Python and DLL bitness must match (64-bit both). |
| "No SoundFont is loaded" | Add an `.sf2` in SoundFont Manager and press *Use selected*. |
| "FFmpeg not found" | Add `ffmpeg.exe` to PATH or set the path in Audio Settings → *Save & check*. |
| "Cannot open audio output device" | Choose another device in Audio Settings; close apps using the device exclusively. |
| Crackling / dropouts | Lower synth gain, close CPU-heavy apps; larger block size is `AudioEngine(block=2048)`. |
| MIDI has no lyrics | Many `.mid` files have none; the lyrics panel says so. Only lyric/text events are shown. |
| File shows "Missing" | It moved or its drive is disconnected; *Rescan* re-links moved files (matched by content) and keeps favorites/play counts. |
| Reverb/chorus error message | Upgrade `pyfluidsynth` (`pip install -U pyfluidsynth`). |

Data lives in `%USERPROFILE%\Documents\ShensuuOke\library.db`. Removing songs/folders/SoundFonts from the app never deletes the original files.

## Packaging (optional)
```
pip install pyinstaller
packaging\build_windows.bat
```
Edit `FLUIDSYNTH_BIN` in the script to point at your FluidSynth `bin` folder; its DLLs are copied next to the executable
and found automatically. FFmpeg is not bundled by default (see licenses below).

## How to Build into Installable Package EXE?

1. First run `packaging\build_windows.bat`.
2. Wait until it finishes.
3. Find `dist\ShensuuOke-Setup.exe`.
4. Done!




## Third-party licenses (verify current terms before redistributing)

| Component | License | Note |
|---|---|---|
| PySide6 / Qt | LGPL-3.0 (or commercial) | Dynamic linking; keep license notices. |
| FluidSynth, pyfluidsynth | LGPL-2.1 | DLLs may be bundled with notices. |
| FFmpeg | LGPL-2.1+ or GPL-2+ depending on the build | Bundling a GPL build has GPL obligations; prefer asking users to install it. |
| mutagen | GPL-2.0-or-later | **Copyleft: distributing it inside a closed-source bundle needs a legal review.** Metadata reading degrades gracefully without it. |
| mido, sounddevice, PortAudio | MIT | |
| NumPy, SciPy | BSD-3-Clause | |
| SQLite | Public domain | |
| SoundFonts, karaoke files | Their own licenses | None are included; supply only media you may legally use. |



