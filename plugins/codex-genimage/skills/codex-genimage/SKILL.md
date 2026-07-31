---
name: codex-genimage
description: Generate images via Codex CLI (`codex exec` + built-in `image_gen` tool). Use whenever the user asks to create, generate, draw, or make a picture/image/illustration via codex / Codex CLI / OpenAI image generation. Triggers on phrases like "сгенерируй картинку через codex", "нарисуй через codex", "generate image with codex", "codex image". Also use when an image is needed as part of another task and codex is the chosen generator (no extra API key — billed via existing Codex auth).
---

# codex-genimage

Generate images by delegating to a separate `codex exec` invocation. Codex has a stable built-in `image_gen` tool, so no extra API key or HTTP call is needed — auth is the user's existing Codex session.

## When to use vs other image skills

- **codex-genimage** (this) — user explicitly mentions codex, or codex is the cheapest/already-authed option.
- **geminigen-image** — user mentions GeminiGen / nano-banana / Gemini 3 Pro Image.
- **nanobanana-genimage** — user mentions NanoBanana directly.

If the user just says "generate an image" without naming a provider, ask which one before guessing.

## Inputs you must have before calling codex

1. **prompt** — concrete description of the desired image. If the user's prompt is vague (e.g. "draw a cat") and the image is for a deliverable (slide, doc, customer-facing), ask one clarifying question via AskUserQuestion. For throwaway/exploratory images, proceed with sensible defaults and note the assumptions.
2. **output path** — absolute path including filename and extension (`.png` recommended). Codex's `image_gen` returns PNG.
   - User specified a path → use it verbatim.
   - User said "save somewhere" / didn't say → propose: inside a project use `./images/<descriptive_name>.png` or `./assets/<name>.png`; in free-form chat use `/tmp/<name>.png`. Confirm via AskUserQuestion only if path choice is ambiguous.
3. **reference images** (optional) — local file paths the codex agent should attach. Used for image-to-image edits (style transfer, identity-preserve, compositing, etc.).

## How to invoke

Use the bundled wrapper. It handles `mkdir -p`, prompt construction, codex flags, and post-run verification:

```bash
bash ~/.claude/skills/codex-genimage/scripts/generate.sh \
  --prompt "<text prompt>" \
  --output "/abs/path/to/file.png" \
  [--ref /abs/path/to/ref1.png] [--ref /abs/path/to/ref2.png]
```

Run it inline via the Bash tool with a generous timeout — generation typically takes **60–120 seconds**. Set `timeout: 240000` (4 min) to be safe. Don't run it in the background; you need the saved file before continuing.

The wrapper prints codex's transcript to stdout and ends with either:
- `✓ saved: <path>` and `file <path>` output, or
- `✗ no fresh image found ...` if codex refused to call `image_gen` (rare — usually means a refusal at the model level; check the transcript).

## After generation

- **User asked for the image directly** → use the Read tool on the saved path so the image renders inline in chat.
- **Image is for a downstream task** (embed in a doc, slide, README) → reference it by path in the next step; no need to Read it for display.

## Why a separate `codex exec` call (not in-process)

Codex's `image_gen` only runs inside the Codex agent — there's no standalone "render this prompt" CLI. Spawning `codex exec` gives the codex agent a fresh, locked-down sandbox, lets it call its tool, then exits.

The wrapper does three things to keep that turn minimal:

1. **Constrains the prompt** — tells codex to call `image_gen` and nothing else; do not plan, research, read files, run shell commands, or call MCP tools. Just produce the image and stop. The wrapper, not codex, is responsible for placing the file. (We tried asking codex to `cp` the result itself; it can't reliably, because `image_gen` returns a path inside the model's sandbox like `/mnt/data/0.png`, which the model can't translate to the host path.)
2. **Strips the user config with `--ignore-user-config`** — disables MCP servers (e.g. context7), `web_search = "live"`, custom personality, and other per-user defaults from `~/.codex/config.toml` that would otherwise nudge codex to "research" before generating. Auth still loads from `CODEX_HOME`.
3. **Forces `model_reasoning_effort=low`** — the lowest level the OpenAI API permits alongside `image_gen` (`minimal` is rejected). Cuts orchestration overhead vs. the user's default `high`.

After codex exits, the wrapper picks up the result this way:

1. `tee`s codex's stdout/stderr to a tempfile while still streaming it to the terminal.
2. Greps the startup banner (`session id: <uuid>`) — printed once per `codex exec` run.
3. Looks only inside `~/.codex/generated_images/<that-uuid>/` for the freshest `ig_*.png` and copies it to `--output`.

Scoping the pickup by session uuid (rather than "newest file globally by mtime") makes parallel `generate.sh` invocations race-safe: each codex exec gets its own uuid and its own subdirectory, so concurrent calls never see each other's files.

## Composing the prompt sent to codex

The wrapper wraps your prompt with a "do nothing else" preamble before calling codex:

```
Use only the built-in image_gen tool to produce one image for the prompt below.
Do not call any other tools. Do not run shell commands. Do not plan, research,
read files, browse the web, or call MCP tools. After image_gen returns, just
stop — the wrapper will pick up the file. Reply with the single word: done.

Image prompt:
<your prompt>
```

Tips for the user-facing part of the prompt:

- Be concrete: subject, composition, style, palette, lighting, aspect ratio. Codex's underlying model handles abstract prompts but rewards specificity.
- Aspect ratio / resolution → describe in words (e.g. "square 1024×1024", "16:9 widescreen, ~1920×1080"). There's no CLI flag for size; the codex agent picks based on the prompt.
- For text rendering (logos, infographics, posters): quote the exact text in the prompt and call out font weight/style.
- For reference-based edits, name each reference in the prompt: "Image 1 (subject) — keep face identity. Image 2 (style reference) — apply painterly texture." Their order matches the order of `--ref` flags.

## Examples

**Text-to-image, explicit path**

User: "Сгенерируй через codex иконку приложения с шестерёнкой и сохрани в ~/icons/gear.png"

```bash
bash ~/.claude/skills/codex-genimage/scripts/generate.sh \
  --prompt "Flat minimalist app icon: a single gear/cog wheel, monochrome dark gray on transparent background, square 1024x1024, suitable as an application icon." \
  --output "$HOME/icons/gear.png"
```

Then `Read ~/icons/gear.png` so the user sees the result.

**Text-to-image, path proposed**

User: "Нарисуй через codex обложку для статьи про postgres tuning"

Propose `./images/postgres_tuning_cover.png` (if in a project) or `/tmp/postgres_tuning_cover.png`, confirm, then run the wrapper.

**Image-to-image with one reference**

User: "Возьми ~/photo.jpg и сделай через codex акварельную версию в /tmp/watercolor.png"

```bash
bash ~/.claude/skills/codex-genimage/scripts/generate.sh \
  --prompt "Recreate the attached photograph as a watercolor painting. Preserve composition and subject identity but render with soft watercolor textures, visible paper grain, and gentle bleeding edges. Maintain the original aspect ratio." \
  --output "/tmp/watercolor.png" \
  --ref "~/photo.jpg"
```

## Notes

- **One image per call.** For multiple variants, call the wrapper multiple times. Sequential or concurrent both work — the wrapper scopes pickup by codex session id, so parallel calls don't collide.
- **Storage.** Codex keeps every original under `~/.codex/generated_images/<session>/ig_*.png`. The wrapper copies (not moves) the freshest one to your `--output`; the originals stay there as a cache.
- **Cost.** Billed via existing Codex auth — no `OPENAI_API_KEY`, no extra config. With the lean wrapper a single generation costs ~15–25k tokens (vs. 30k+ when codex was also running shell commands).
- **Sandbox / git check.** `--dangerously-bypass-approvals-and-sandbox` and `--skip-git-repo-check` are always passed so the wrapper works from `/tmp` and other non-git locations regardless of the user's config.
