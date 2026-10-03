---
name: youtube-transcript
description: Extract transcripts from YouTube videos. Use when the user asks for a transcript, subtitles, or captions of a YouTube video and provides a YouTube URL (youtube.com/watch?v=, youtu.be/, or similar). Supports output with or without timestamps.
---

# YouTube Transcript

Extract transcripts from YouTube videos using the youtube-transcript-api.

## Usage

Run the script with a YouTube URL or video ID:

```bash
uv run scripts/get_transcript.py "VIDEO_URL_OR_ID"
```

With timestamps:

```bash
uv run scripts/get_transcript.py "VIDEO_URL_OR_ID" --timestamps
```

## Defaults

- **Without timestamps** (default): Plain text, one line per caption segment
- **With timestamps**: `[MM:SS] text` format (or `[HH:MM:SS]` for longer videos)

## Supported URL Formats

- `https://www.youtube.com/watch?v=VIDEO_ID`
- `https://youtu.be/VIDEO_ID`
- `https://youtube.com/embed/VIDEO_ID`
- Raw video ID (11 characters)

## Output

- Keep the transcript's words exactly as returned — no edits, summaries or corrections; the user relies on it as the verbatim record. Reflowing a transcript without timestamps into paragraphs (next point) is the only change allowed.
- If the transcript is without timestamps, reflow it into complete paragraphs so that no line breaks in the middle of a sentence.
- If you were asked to save the transcript to a specific file, save it to the requested file.
- If no output file was specified, use the YouTube video ID with a `-transcript.txt` suffix.
- Always copy the output file to `~/youtube-transcripts/` (create the directory if it doesn't exist).

## Notes

- Fetches auto-generated or manually added captions (whichever is available)
- Requires the video to have captions enabled
- Falls back to auto-generated captions if manual ones aren't available
