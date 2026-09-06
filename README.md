# footage-scout

> Agent skill: search & download **real video footage** — stock b-roll +
> archival/public-domain film — for video production. 给视频创作自动找真实素材。

Turns "my video is 100% motion graphics, I want real footage like those AI
history compilations" into a one-command pipeline. The agent derives concrete
visual queries from the script; this skill searches four sources, downloads
clips, builds review contact sheets, and keeps a license manifest so every
frame in the final video has a paper trail.

```
script/storyboard ──► scene-queries.json ──► footage_scout search
                                                    │
                                     manifest.json  +  per-query candidates
                                                    ▼
                                        footage_scout download --thumbs
                                                    │
                                    clips + .license.json + contact sheets
                                                    ▼
                                    review → ffmpeg crop/duotone → timeline
```

## Install (any SKILL.md-compatible agent)

Copy or clone into your user skills directory:

```bash
# ZCode
git clone https://github.com/W-jiesen/footage-scout.git ~/.agents/skills/footage-scout
# Claude Code
git clone https://github.com/W-jiesen/footage-scout.git ~/.claude/skills/footage-scout
```

Requirements: Python 3.9+ (stdlib only). `ffmpeg` on PATH enables thumbnails
and contact sheets (optional but recommended).

Optional free API keys (stock providers; archival sources need no key):

```bash
cp .env.example .env   # then fill in
```

- `PEXELS_API_KEY` — <https://www.pexels.com/api/> (instant, free)
- `PIXABAY_API_KEY` — <https://pixabay.com/api/docs/> (free)

## Usage

```bash
# 1. search (pexels+pixabay stock, archive.org archival; 9:16, ≤25s clips)
python scripts/footage_scout.py search \
  --queries "1960s mainframe computer room, data center server racks" \
  --providers pexels,pixabay,archive \
  --orientation portrait --max-duration 25 --out scout-pass1

# ...or from a scene→queries JSON produced by your agent:
python scripts/footage_scout.py search --queries-file examples/scene-queries.example.json --out scout-pass1

# 2. download top-2 per query + thumbnails + contact sheets
python scripts/footage_scout.py download --manifest scout-pass1/manifest.json --top 2 --thumbs

# 2b. or download specific ids after reviewing
python scripts/footage_scout.py download --manifest scout-pass1/manifest.json --ids pexels_8124071,archive_JATP_007
```

Outputs:

- `manifest.json` — every candidate with author / license / source URL /
  duration / orientation; downloads update it in place
- `downloads/*.mp4|webm` + matching `*.license.json` sidecars
- `thumbs/` frame grabs + `sheet_<query>.jpg` contact sheets for review

On networks that block archive.org / Wikimedia (e.g. CN direct): add
`--proxy http://127.0.0.1:7890`.

## Sources & licensing

| Provider | Key | License summary | Notes |
| --- | --- | --- | --- |
| Pexels | free key | commercial use OK, no attribution | modern b-roll, vertical |
| Pixabay | free key | commercial use OK, no attribution | texture variety |
| Internet Archive (`prelinger`/`nasa`/…) | none | free access; verify per item commercially | the archival goldmine behind AI-history compilations |
| Wikimedia Commons | none | per-file CC (attribution for BY/SA) | usually webm/ogv |

Details and caveats: [references/providers.md](references/providers.md).
Full worked pipeline (query derivation → review → duotone blend into motion
graphics): [references/workflow.md](references/workflow.md).

## Design notes

- **Agent does semantics, script does mechanics.** Choosing *what to look for
  and why* is the model's job; searching, downloading, thumbnailing, and
  license bookkeeping are deterministic CLI steps any agent can run.
- **Noise on disk, one line to stdout** — friendly to agent contexts.
- **License sidecars ship with the clips** — compilations are legal edits, not
  scraped reuploads.
- Inspired by / informed by:
  [internetarchive/internet-archive-skills](https://github.com/internetarchive/internet-archive-skills)
  (canonical archive.org URL discipline),
  [Bomx/super-video-maker-skill](https://github.com/Bomx/super-video-maker-skill)
  (b-roll-by-beat-purpose routing, contact-sheet QC), and the broader
  [awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills)
  ecosystem.

## License

MIT — see [LICENSE](LICENSE).
