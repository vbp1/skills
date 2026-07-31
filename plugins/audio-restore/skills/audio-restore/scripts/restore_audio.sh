#!/bin/bash
# Audio restoration pipeline: Demucs separation + per-stem EQ + mix + normalize
# Usage: ./restore_audio.sh input.wav [output.wav] [duration_seconds]
#
# Requires: ffmpeg, demucs (in active venv)

set -euo pipefail

INPUT="${1:?Usage: $0 input.wav [output.wav] [duration_seconds]}"
OUTPUT="${2:-restored.wav}"
DURATION="${3:-}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

BASENAME="$(basename "$INPUT" .wav)"

echo "=== Audio Restoration Pipeline ==="
echo "Input: $INPUT"
echo "Output: $OUTPUT"

# Step 1: Source separation
echo ""
echo "[1/4] Running Demucs source separation..."
python3 -m demucs --two-stems=vocals -n htdemucs "$INPUT" -o "$WORKDIR"

VOCALS="$WORKDIR/htdemucs/$BASENAME/vocals.wav"
INSTRUMENTS="$WORKDIR/htdemucs/$BASENAME/no_vocals.wav"

if [ ! -f "$VOCALS" ] || [ ! -f "$INSTRUMENTS" ]; then
    echo "ERROR: Demucs output not found"
    exit 1
fi

# Duration flag
TRIM=""
if [ -n "$DURATION" ]; then
    TRIM="-t $DURATION"
    echo "Trimming to ${DURATION}s"
fi

# Step 2: Vocals EQ
echo ""
echo "[2/4] Applying vocals EQ..."
ffmpeg -y -i "$VOCALS" $TRIM \
  -af "volume=-4dB,\
equalizer=f=1000:t=q:w=1.0:g=10,\
equalizer=f=2000:t=q:w=1.0:g=13,\
equalizer=f=4000:t=q:w=1.2:g=8,\
equalizer=f=8000:t=q:w=2.5:g=10,\
equalizer=f=12000:t=q:w=3.0:g=8,\
highshelf=f=6000:g=6" \
  -ar 48000 "$WORKDIR/vocals_eq.wav" 2>/dev/null

# Step 3: Instruments EQ
echo "[3/4] Applying instruments EQ..."
ffmpeg -y -i "$INSTRUMENTS" $TRIM \
  -af "volume=-6dB,\
equalizer=f=1000:t=q:w=1.0:g=12,\
equalizer=f=2000:t=q:w=1.0:g=15,\
equalizer=f=4000:t=q:w=1.2:g=18,\
equalizer=f=8000:t=q:w=2.0:g=18,\
equalizer=f=12000:t=q:w=2.5:g=15,\
highshelf=f=6000:g=12" \
  -ar 48000 "$WORKDIR/instruments_eq.wav" 2>/dev/null

# Step 4: Mix and normalize
echo "[4/4] Mixing and normalizing..."
ffmpeg -y -i "$WORKDIR/vocals_eq.wav" -i "$WORKDIR/instruments_eq.wav" \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=longest,loudnorm=I=-14:TP=-1:LRA=11" \
  -ar 48000 "$OUTPUT" 2>/dev/null

echo ""
echo "=== Done ==="
DURATION_SEC=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUTPUT" 2>/dev/null)
echo "Output: $OUTPUT (${DURATION_SEC}s)"
