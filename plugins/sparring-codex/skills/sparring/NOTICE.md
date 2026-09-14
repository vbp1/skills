# Notice

This skill is derived from [nyxandro/sparring-skill](https://github.com/nyxandro/sparring-skill)
(© nyxandro; the upstream README declares the MIT licence). The sparring protocol, the
opponent prompt and the session-handling approach come from that project.

This build differs from upstream:

- one opponent only — Claude Code CLI;
- one command, `sparctl ask`, carrying the non-interactive path;
- prompts passed by file;
- the opponent's machine event stream is rendered as a readable progress log while it works;
- every run ends with one machine-readable terminal line, on success and on failure alike;
- the session id is recorded the moment the opponent announces it;
- machine state and the readable record of the debate live in separate files;
- the tmux screen-scraping mode is not included.
