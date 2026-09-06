# Providers — keys, quotas, licenses, reachability

## Pexels (stock, recommended default)

- **Key:** register free at <https://www.pexels.com/api/> — instant, no card.
  Env var `PEXELS_API_KEY`. Quota: 200 requests/hour on the free tier, plenty
  for a whole video per session.
- **License:** Pexels License — free for commercial use, no attribution
  required, no permission needed. You may not sell unmodified clips or imply
  endorsement by pictured people/brands. Identifiable people and logos still
  carry real-world publicity/trademark rights — avoid recognizable faces/brands
  in ads or sensitive contexts.
- **Content:** modern b-roll, strong vertical (portrait) catalog, `video/mp4`
  links without watermarks.
- **CN network:** `api.pexels.com` reachable directly.

## Pixabay (stock, second source for texture variety)

- **Key:** register at <https://pixabay.com/api/docs/> (free). Env var
  `PIXABAY_API_KEY`. Quota on free tier is generous but rate-limited per
  minute — the script sleeps between calls.
- **License:** Pixabay Content License — free for commercial use, no
  attribution required. Same real-world caveats about identifiable people,
  logos, and protected property.
- **CN network:** `pixabay.com` reachable directly.

## Internet Archive / Prelinger (archival)

- **Key:** none. Two requests per candidate: advancedsearch + item metadata.
- **Default collection:** `prelinger` (~10k advertising, educational,
  industrial and amateur films — the exact source family behind most "AI
  编年史" compilation videos). Switch with `--collection nasa` (space footage,
  public domain), `--collection any`, or any other collection identifier.
- **License:** mixed. Prelinger items are free to download and reuse; many are
  public domain but some carry restrictions — the manifest records the item's
  `licenseurl` when present, otherwise "verify item page". For commercial use,
  check the item's details page. NASA material is public domain.
- **Canonical URLs:** always `archive.org/details/<id>` and
  `archive.org/download/<id>/<file>` — never the per-server `ia?????.us.archive.org`
  mirrors (they break when items migrate).
- **CN network:** **blocked** — pass `--proxy http://127.0.0.1:7890` (or your
  own proxy) or set `HTTPS_PROXY`.

## Wikimedia Commons (archival, CC)

- **Key:** none.
- **License:** per-file, shown in the manifest, e.g. "CC BY-SA 4.0 (Wikimedia
  Commons)" — attribution **required** for CC BY/CC BY-SA; keep the sidecar.
  Formats are usually `.webm`/`.ogv` (plays in Chromium-based renderers and
  ffmpeg; transcode with `ffmpeg -i in.webm -c:v libx264 -c:a aac out.mp4` if
  your pipeline wants mp4).
- **CN network:** **blocked** — same `--proxy` treatment as archive.org.

## Quality bar when picking clips

- Serve the beat: the clip must illustrate the sentence being spoken, not
  merely "feel related".
- Vary texture between consecutive clips (close-up / wide, warm / cool, real
  footage / archival grain) — sameness reads as automated.
- For 9:16 projects, prefer native portrait clips (`--orientation portrait`)
  over cropping landscape footage.
- Reject clips with visible watermarks, burned-in captions, or dominant
  third-party logos.

## Beyond the four providers

- **Paid licensed stock** (Pond5, Artgrid, Storyblocks, 新片场, 摄图网,
  包图网): better exclusivity for commercial client work; no API in this skill —
  browse manually. 中国平台均需商用授权，别拿预览水印素材当正片。
- **Never** use yt-dlp to rip other creators' compilation videos as source
  material. Archive compilations are themselves edits of the same public-domain
  items this skill finds — go to the original items instead.
- This file is sourcing guidance, not legal advice; for client/broadcast work,
  confirm the license on the item page.
