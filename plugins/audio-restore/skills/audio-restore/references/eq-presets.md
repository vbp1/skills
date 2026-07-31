# EQ Presets Reference

Proven EQ presets for common audio restoration scenarios. All values use ffmpeg `equalizer` filter syntax.

## Phone Concert Recording (Noise Suppression Rolloff)

The most common case: phone's noise suppression kills frequencies above 1 kHz, making audio sound "like from a barrel". Requires aggressive HF boost with de-essing.

### Per-Stem Approach (Recommended)

**Vocals:**
```bash
ffmpeg -y -i vocals.wav \
  -af "volume=-4dB,\
equalizer=f=1000:t=q:w=1.0:g=10,\
equalizer=f=2000:t=q:w=1.0:g=13,\
equalizer=f=4000:t=q:w=1.2:g=8,\
equalizer=f=8000:t=q:w=2.5:g=10,\
equalizer=f=12000:t=q:w=3.0:g=8,\
highshelf=f=6000:g=6" \
  -ar 48000 vocals_eq.wav
```

Key points:
- `volume=-4dB` — headroom before boosting
- 4 kHz kept moderate (+8) to avoid sibilance
- Wide Q at 8k/12k (w=2.5/3.0) to prevent ringing
- No de-essing notch needed at these moderate levels

**Instruments:**
```bash
ffmpeg -y -i no_vocals.wav \
  -af "volume=-6dB,\
equalizer=f=1000:t=q:w=1.0:g=12,\
equalizer=f=2000:t=q:w=1.0:g=15,\
equalizer=f=4000:t=q:w=1.2:g=18,\
equalizer=f=8000:t=q:w=2.0:g=18,\
equalizer=f=12000:t=q:w=2.5:g=15,\
highshelf=f=6000:g=12" \
  -ar 48000 instruments_eq.wav
```

Key points:
- More aggressive boost (+15 to +18 dB) — instruments tolerate it better
- More headroom (`volume=-6dB`) for the larger boost
- Aggressive highshelf (+12 dB at 6 kHz)

**Mix:**
```bash
ffmpeg -y -i vocals_eq.wav -i instruments_eq.wav \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=longest,\
loudnorm=I=-14:TP=-1:LRA=11" \
  -ar 48000 output.wav
```

### Single-File Approach (Simpler, Good Enough)

When source separation is not available or not worth it:

```bash
ffmpeg -y -i input.wav \
  -af "volume=-6dB,\
equalizer=f=1000:t=q:w=1.0:g=12,\
equalizer=f=2000:t=q:w=1.0:g=15,\
equalizer=f=4000:t=q:w=1.2:g=14,\
equalizer=f=5500:t=q:w=0.7:g=-5,\
equalizer=f=7000:t=q:w=0.7:g=-5,\
equalizer=f=8000:t=q:w=2.5:g=12,\
equalizer=f=12000:t=q:w=3.0:g=10,\
highshelf=f=6000:g=8,\
loudnorm=I=-14:TP=-1:LRA=11" \
  -ar 48000 output.wav
```

Key points:
- 4 kHz reduced to +14 to limit sibilance
- De-essing notches at 5.5 kHz and 7 kHz (w=0.7, narrow)
- 8k/12k with wide Q to avoid ringing
- Moderate highshelf (+8 dB)

## Mild Compression Artifacts (Low Bitrate)

For audio compressed at low bitrate (64-128 kbps) with gradual HF loss:

```bash
ffmpeg -y -i input.wav \
  -af "equalizer=f=4000:t=q:w=1.5:g=4,\
equalizer=f=8000:t=q:w=2.0:g=6,\
equalizer=f=12000:t=q:w=2.5:g=4,\
highshelf=f=8000:g=3,\
loudnorm=I=-14:TP=-1:LRA=11" \
  -ar 48000 output.wav
```

Much gentler boost — compression artifacts are less severe than noise suppression.

## Common Adjustments

| Problem | Fix |
|---------|-----|
| Sibilance/lisping on "s", "sh" | Add notch: `equalizer=f=5500:t=q:w=0.7:g=-5` and `equalizer=f=7000:t=q:w=0.7:g=-5` |
| Clicking on "t" consonants | Widen notch: increase `w` from 0.7 to 1.0, or reduce 4 kHz boost |
| Ringing/harsh highs | Widen Q: increase `w` at 8k/12k to 3.0+, reduce gain by 2-3 dB |
| Still muffled | Increase boost amounts by 3-5 dB per band |
| Too bright/thin | Reduce all boosts by 30%, check stem volume balance |
| Hissing on consonants | Reduce 4 kHz boost, add wider notch at 5-7 kHz range |
