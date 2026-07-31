---
name: audio-restore
description: Restore audio quality from low-quality recordings (phone concerts, dictaphone, compressed audio). Use when user asks to fix muffled/dull audio, restore high frequencies, improve phone recordings, enhance live concert audio, or any audio that sounds "like from a barrel". Triggers on requests involving audio restoration, frequency recovery, EQ correction, stem separation, or audio enhancement.
---

# Audio Restore

Restore audio quality from low-quality recordings using spectral analysis, AI source separation (Demucs), per-stem parametric EQ, and normalization.

## Prerequisites

- **ffmpeg** (required) — spectral analysis, parametric EQ, mixing, normalization
- **demucs** (required) — AI source separation into vocals/instruments stems
- **sox** (optional) — visual spectrogram generation for analysis
- **Python venv** — always create a venv before installing Python packages

Install demucs in a venv:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install demucs
```

## Workflow Decision Tree

```
Input audio file
  |
  v
[1. Spectral Analysis] -- Diagnose the problem
  |
  v
Is the issue frequency loss (muffled/dull)?
  |-- YES --> [2. Source Separation] --> [3. Per-Stem EQ] --> [4. Mix + Normalize]
  |-- MILD (slight dullness) --> [3b. Single-file EQ] --> [4. Normalize]
  |-- NO (noise/other) --> Different approach needed
```

## Step 1: Spectral Analysis

Diagnose the audio problem before applying any processing.

```bash
# Check frequency content with ffprobe
ffprobe -v error -show_entries stream=sample_rate,channels,codec_name,bit_rate -of default=noprint_wrappers=1 input.wav

# Generate spectrum stats to identify rolloff frequency
ffmpeg -i input.wav -af "asplit[a][b],[a]showspectrum=s=1024x512:mode=combined:color=intensity:scale=log,format=yuv420p[v]" -map "[v]" -frames:v 1 -y spectrum.png -map "[b]" -f null - 2>&1 | tail -5

# Quick frequency band levels (identify where rolloff starts)
ffmpeg -i input.wav -af "astats=metadata=1:reset=0,ametadata=print:key=lavfi.astats.Overall.RMS_level" -f null - 2>&1 | tail -3
```

**With sox (optional)** — generate a visual spectrogram:
```bash
sox input.wav -n spectrogram -o spectrogram.png -t "Audio Spectrum"
```

**What to look for:**
- Sharp rolloff above 1-4 kHz → phone noise suppression (most common)
- Gradual rolloff above 8 kHz → low bitrate compression
- Flat response → issue is not frequency loss

## Step 2: Source Separation with Demucs

Separate audio into stems for independent processing. This enables different EQ curves for vocals vs instruments.

```bash
source .venv/bin/activate
python3 -m demucs --two-stems=vocals -n htdemucs input.wav
```

Output: `separated/htdemucs/input/vocals.wav` and `separated/htdemucs/input/no_vocals.wav`

**When to use htdemucs:**
- `htdemucs` — best general-purpose model (default, recommended)
- `--two-stems=vocals` — split into vocals + everything else (simpler, recommended)
- Without `--two-stems` — splits into vocals, drums, bass, other (4 stems)

## Step 3: Per-Stem Parametric EQ

Apply different EQ curves to vocals and instruments. See [references/eq-presets.md](references/eq-presets.md) for proven presets.

**General approach:**
- Vocals need gentler boost (risk of sibilance/lisping)
- Instruments need more aggressive HF boost
- Always add de-essing notch filters on vocals when boosting above 4 kHz

**ffmpeg EQ filter syntax:**
```
equalizer=f=FREQ:t=q:w=WIDTH:g=GAIN_DB
highshelf=f=FREQ:g=GAIN_DB
```

- `f` — center frequency in Hz
- `w` — bandwidth (Q factor): 1.0 = normal, 2.0+ = wider/gentler, 0.5 = narrow/surgical
- `g` — gain in dB (positive = boost, negative = cut)

**De-essing:** Use narrow notch filters at sibilance frequencies:
```
equalizer=f=5500:t=q:w=0.7:g=-5   # 5.5 kHz notch
equalizer=f=7000:t=q:w=0.7:g=-5   # 7 kHz notch
```

## Step 4: Mix and Normalize

Combine processed stems with EBU R128 loudness normalization.

```bash
ffmpeg -y -i vocals_eq.wav -i instruments_eq.wav \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=longest,loudnorm=I=-14:TP=-1:LRA=11" \
  -ar 48000 output.wav
```

**Parameters:**
- `loudnorm=I=-14` — target integrated loudness (-14 LUFS, streaming standard)
- `TP=-1` — true peak limit (-1 dBTP, prevents clipping)
- `LRA=11` — loudness range (dynamic range target)

## Iterative Approach

Audio restoration is iterative. Always:

1. **Start with a short test clip** (30 seconds from a representative section with both vocals and instruments)
2. **Let the user listen** after each adjustment
3. **Adjust based on feedback** — common issues:
   - "Lisping/sibilance" → add de-essing notch filters, reduce 4-6 kHz boost
   - "Ringing/harsh" → widen Q (increase w parameter), reduce 8-12 kHz boost
   - "Still muffled" → increase boost amounts
   - "Too bright/thin" → reduce overall boost, check volume balance between stems
4. **Process full file** only after user approves the test clip

## Output Formats

```bash
# WAV (lossless)
ffmpeg -y -i output.wav -ar 48000 final.wav

# MP3 (best quality VBR)
ffmpeg -y -i output.wav -codec:a libmp3lame -q:a 0 final.mp3

# Trim to specific duration
ffmpeg -y -i output.wav -t SECONDS final.wav
```
