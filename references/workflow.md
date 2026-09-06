# Worked pipeline — adding real footage to a motion-graphics explainer

Context: a 120s vertical (1080x1920) HyperFrames-style explainer that is 100%
kinetic typography and charts. Goal: weave in 4–6 real clips without breaking
the visual language. All paths below are examples — adapt to the project.

## 1. Read the script and mark footage-worthy beats

Open `SCRIPT.md` / `STORYBOARD.md`. Not every frame needs footage — usually
only 3–6 beats do:

- the emotional hook (a real person, a real desk, a real late night)
- the history/context beat (archival film)
- the "what actually changed" beat (a real environment: server room, lab, office)

Beat purposes that should NOT get stock footage: number reveals, chart
comparisons, conclusions — the motion graphics already own those.

## 2. Write the query file

`scene-queries.json` — group per frame/scene so the manifest stays readable:

```json
{
  "hook-anxiety": [
    "woman staring at laptop screen worried night",
    "office worker late night computer desk"
  ],
  "history-computing": [
    "1960s mainframe computer room",
    "punch card operator vintage"
  ],
  "datacenter-today": [
    "data center server racks blue light",
    "GPU server room walking"
  ]
}
```

Rules: English queries; nouns + action + setting; 2–4 per beat; era qualifiers
for archival. Avoid brand names in queries — results get worse and licenses
get riskier ("OpenAI office" → no; "modern AI startup office" → yes).

## 3. Scout

```bash
python scripts/footage_scout.py search \
  --queries-file scene-queries.json \
  --providers pexels,pixabay,archive \
  --orientation portrait --max-duration 25 \
  --out scout-pass1
```

Read the stderr notes: missing key → register (2 minutes, see
`providers.md`); blocked host → re-run adding `--proxy http://127.0.0.1:7890`.

Zero results for a query usually means too abstract — rewrite it filmable
("AI 未来" → "person walking into light futuristic corridor").

## 4. Review the contact sheets

```bash
python scripts/footage_scout.py download --manifest scout-pass1/manifest.json --top 2 --thumbs
```

Open `scout-pass1/sheet_*.jpg`. For each beat pick the clip that:
1. directly illustrates the narration line,
2. contrasts in texture with the adjacent graphics frames,
3. keeps its subject out of the bottom caption band (roughly bottom 17% of a
   9:16 frame),
4. has no watermarks/burned-ins, and whose license label is acceptable.

To swap in a different candidate from the manifest, re-run with explicit ids:

```bash
python scripts/footage_scout.py download --manifest scout-pass1/manifest.json \
  --ids pexels_8124071,archive_JATP_007
```

## 5. Normalize and blend

Fit-to-fill to the project canvas (never pad with bars):

```bash
ffmpeg -y -i downloads/pexels_8124071_hook-anxiety.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30" \
  clip-916.mp4
```

To sit inside a paper-toned motion-graphics world, treat the clip so it stops
looking like a separate stock layer. Two cheap recipes:

**Duotone / paper-tone match** (maps the clip into the project's two brand
colors; here ink `#1c1c1c` + cobalt `#2727e6` on warm paper):

```bash
ffmpeg -y -i clip-916.mp4 -vf "curves=r='0/0.93 1/1':g='0/0.93 1/1':b='0/0.88 1/1',\
  hue=s=0.35,colorbalance=rs=-0.05:bs=0.08" clip-treated.mp4
```

**Archival treatment** for old film (slight grain + vignette + slow push-in):

```bash
ffmpeg -y -i clip-916.mp4 -vf "noise=alls=6:allf=t,eq=contrast=1.05:saturation=0.75" \
  clip-archival.mp4
```

In a HyperFrames composition, drop the treated clip in as a media clip layered
behind the typography (e.g. 70–85% opacity, or split-screen with the type band
on top). If the environment has the `media-use` skill, prefer
`resolve --type grade` / its treatment pipeline over hand-rolled ffmpeg.

Timing rules: clip length ≤ the beat; if narration runs longer than the clip,
hold the last frame instead of looping —

```bash
ffmpeg -y -i clip-treated.mp4 -vf "tpad=stop_mode=clone:stop_duration=2" clip-held.mp4
```

## 6. Keep the paper trail

`manifest.json` + per-clip `*.license.json` sidecars live inside the project
folder (e.g. `assets/footage-scout/`). If a client or platform ever asks
"what is this clip and are you allowed to use it", the answer is one file
away. This is the difference between "compilation video" and "licensed edit".
