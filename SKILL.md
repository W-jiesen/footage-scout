---
name: footage-scout
description: Find and download real video footage — stock b-roll and archival/public-domain film — for any video project. Use whenever a video, script, storyboard, or HyperFrames composition needs real-world visuals instead of (or alongside) motion graphics — e.g. "find real footage for this video", "add b-roll", "给视频找真实素材/历史影像/资料画面", "我的视频全是动效，想加真实镜头". Searches Pexels + Pixabay (stock) and Internet Archive + Wikimedia Commons (archival) through one CLI, picks clips by beat purpose, and outputs reviewable thumbnails plus a license manifest.
---

# footage-scout

Give motion-graphics videos a spine of real footage: stock clips for
story/example beats, archival film for history beats. The agent decides *what
to look for and why*; `scripts/footage_scout.py` does the searching,
downloading, and license bookkeeping. Stdlib-only Python, no dependencies
(ffmpeg optional, for thumbnails).

## The workflow

### 1. Derive visual queries from the script — this is the agent's real job

Read the script/storyboard (e.g. `SCRIPT.md` / `STORYBOARD.md` in a HyperFrames
project). For each scene or beat, write 2–4 **concrete, filmable** queries.
A query is something a camera could have filmed: nouns + actions + setting.
Bad: "AI anxiety" / "技术进步". Good: "person staring at laptop late night",
"server room blue lights", "1970s office computer room".

Route each beat by its **purpose**, not by what sounds cool:

| Beat purpose | What to scout | Where |
| --- | --- | --- |
| History / "回顾70年" | archival film, era-qualified: "1960s computer laboratory", "Turing machine recreation" | `archive`, `wikimedia` |
| Story / example ("一位设计师在工作") | real footage of a real person doing the thing | `pexels`, `pixabay` |
| Proof / news ("GPT-6 发布") | real screenshot of the source page + Ken Burns — **not** stock footage | (browser screenshot; this skill is for footage) |
| Concept / metaphor | a single real object shot ("hourglass", "printer closeup"), or a typographic card — no abstract "AI glow" | `pexels`, `pixabay` |

Search terms in **English** — stock libraries are English-indexed even for
Chinese videos. Add era qualifiers (`1950s`, `cold war`, `vintage`) for archival
beats. Save the mapping as a JSON file so it's reviewable and re-runnable:

```json
{
  "frame1-anxiety": ["person staring at laptop late night", "office worker worried screen"],
  "frame2-history": ["1960s mainframe computer room", "punch card machine"]
}
```

See `examples/scene-queries.example.json` for a full worked example.

### 2. Search

```bash
python scripts/footage_scout.py search \
  --queries-file scene-queries.json \
  --providers pexels,pixabay,archive \
  --orientation portrait --max-duration 20 \
  --out scout-gpt6
```

Prints per-query candidate counts; errors stay in `scout-gpt6/manifest.json`
and stderr, never crash the run. `--orientation portrait` for 9:16 projects,
`landscape` for 16:9. Exit code 2 means zero results — try broader queries or
more providers.

### 3. Download + review

```bash
python scripts/footage_scout.py download --manifest scout-gpt6/manifest.json --top 2 --thumbs
```

Downloads the top N per query (or `--ids pexels_123,...` to choose), writes a
`.license.json` sidecar next to every clip, and builds a contact sheet per
query (`sheet_*.jpg`). **Open the contact sheets** and pick by: does it serve
the beat, does the texture vary from the previous clip, is the important
content outside the caption band (bottom ~17% on 9:16). Re-run `download
--ids ...` for better-ranked picks.

### 4. Cut into the project

Fit-to-fill crop, never letterbox (1080x1920 example):

```bash
ffmpeg -y -i clip.mp4 -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920" clip-916.mp4
```

Blend with a motion-graphics style instead of pasting raw clips: duotone /
paper-grain / a colored overlay that matches the canvas, or slow Ken Burns on
archival stills. If a `media-use` skill is available in the environment, prefer
its treatment pipeline; otherwise the ffmpeg recipe in
`references/workflow.md` is the fallback. Never loop a clip inside a long beat
— hold the last frame (`tpad=stop_mode=clone`) or cross-cut to another clip.

### 5. License hygiene (do not skip)

The manifest and sidecars record author / license / source URL for every clip.
Rules of thumb: Pexels + Pixabay licenses are free for commercial use without
attribution; Wikimedia needs attribution per its label (CC BY etc.); Internet
Archive / Prelinger is free-access but **verify per item for commercial use**.
Never present a licensed clip as your own creation; keep the sidecars with the
project. Never scrape YouTube/Douyin reuploads of other creators' edits — the
"AI history" videos you admire compile from the same public-domain archives
this skill searches; go to the source, not the copy.

## Provider notes

| Provider | Key needed | Best for | Reachability |
| --- | --- | --- | --- |
| `pexels` | `PEXELS_API_KEY` (free, instant) | modern b-roll, vertical clips | CN direct OK |
| `pixabay` | `PIXABAY_API_KEY` (free) | modern b-roll, mixed styles | CN direct OK |
| `archive` | none | historical/archival film, Prelinger & NASA | CN: needs `--proxy` |
| `wikimedia` | none | historical video, CC-licensed | CN: needs `--proxy` |

Blocked host error message already suggests `--proxy http://127.0.0.1:7890`.
Quotas and per-license details: read `references/providers.md`.

## Reference files

- `references/providers.md` — key registration, quotas, license summaries,
  Chinese stock platforms (paid, licensed) worth knowing about.
- `references/workflow.md` — full worked pipeline on a HyperFrames project,
  including ffmpeg blend/treatment recipes and the review checklist.
- `examples/scene-queries.example.json` — query-derivation example from a real
  120s AI-news explainer.
