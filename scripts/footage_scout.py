#!/usr/bin/env python3
"""footage-scout — search & download real video footage for video projects.

Providers:
  pexels     stock b-roll (free API key)          https://www.pexels.com/api/
  pixabay    stock b-roll (free API key)          https://pixabay.com/api/docs/
  archive    Internet Archive / Prelinger (keyless, archival & public domain)
  wikimedia  Wikimedia Commons video (keyless, CC / public domain)

Stdlib only (Python 3.9+). ffmpeg is optional, used for thumbnails.

Typical use:
  python footage_scout.py search --queries "server room, GPU racks" \
      --providers pexels,pixabay --orientation portrait --out ./scout
  python footage_scout.py download --manifest ./scout/manifest.json --top 2
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0.0"
UA = f"footage-scout/{VERSION} (agent skill; +https://github.com/W-jiesen/footage-scout)"
PROVIDERS = ("pexels", "pixabay", "archive", "wikimedia")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class ScoutError(Exception):
    """A provider or download failure with an agent-readable message."""


class MissingKey(ScoutError):
    def __init__(self, provider: str, env_var: str, register: str):
        super().__init__(
            f"provider '{provider}' needs an API key: set env {env_var} "
            f"(or pass --{provider}-key). Register free at {register}"
        )


# ---------------------------------------------------------------- env loading

ENV: dict = {}


def load_dotenv() -> None:
    """Tiny .env loader: script dir first, then CWD. Real env always wins."""
    for path in (os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
                 os.path.join(os.getcwd(), ".env")):
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                ENV.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_key(provider: str) -> str | None:
    return os.environ.get(f"{provider.upper()}_API_KEY") or ENV.get(f"{provider.upper()}_API_KEY")


# ---------------------------------------------------------------- http helpers

def build_opener(proxy: str | None) -> urllib.request.OpenerDirector:
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener()  # honors HTTP(S)_PROXY env vars


OPENER: urllib.request.OpenerDirector | None = None
TIMEOUT = 15
RETRIES = 2


def _fetch(req: urllib.request.Request) -> bytes:
    last = None
    for attempt in range(RETRIES + 1):
        try:
            with OPENER.open(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(400).decode("utf-8", "replace")
            except Exception:
                pass
            raise ScoutError(f"HTTP {exc.code} from {req.host}: {detail or exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            if attempt < RETRIES:
                time.sleep(1.0 + attempt)
    raise ScoutError(
        f"cannot reach {req.host} after {RETRIES + 1} attempts ({last}). "
        "If this network blocks the provider, pass --proxy http://127.0.0.1:7890 "
        "or set HTTPS_PROXY."
    )


def fetch_json(url: str, headers: dict | None = None) -> dict:
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    raw = _fetch(req)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ScoutError(f"non-JSON response from {req.host}: {raw[:120]!r}") from exc


def download_file(url: str, dest: str, referer: str | None = None) -> str:
    h = {"User-Agent": UA}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    tmp = dest + ".part"
    with OPENER.open(req, timeout=TIMEOUT * 4) as resp, open(tmp, "wb") as fh:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            fh.write(chunk)
    os.replace(tmp, dest)
    return dest


# ---------------------------------------------------------------- entry helpers

def base_entry(provider: str, query: str) -> dict:
    return {
        "provider": provider,
        "query": query,
        "id": None,
        "title": None,
        "duration": None,
        "width": None,
        "height": None,
        "orientation": None,
        "file_url": None,
        "file_format": "mp4",
        "page_url": None,
        "thumb_url": None,
        "author": None,
        "license": None,
        "year": None,
        "local_file": None,
        "thumb": None,
    }


def finish_entry(entry: dict) -> dict:
    w, h = entry.get("width"), entry.get("height")
    if w and h:
        entry["orientation"] = "portrait" if h > w else ("landscape" if w > h else "square")
    return entry


def keep(entry: dict, args) -> bool:
    dur = entry.get("duration")
    if dur is not None and not (args.min_duration <= dur <= args.max_duration):
        return False
    want = args.orientation
    if want and want != "any" and entry.get("orientation") and entry["orientation"] != want:
        return False
    return True


def slugify(text: str, limit: int = 28) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:limit] or "clip"


# ---------------------------------------------------------------- providers

def search_pexels(query: str, args) -> list[dict]:
    key = args.pexels_key or get_key("pexels")
    if not key:
        raise MissingKey("pexels", "PEXELS_API_KEY", "https://www.pexels.com/api/")
    params = {"query": query, "per_page": str(max(args.max_per_query * 3, 9))}
    if args.orientation in ("portrait", "landscape"):
        params["orientation"] = args.orientation
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(params)
    data = fetch_json(url, {"Authorization": key})
    entries = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("file_type") == "video/mp4" and f.get("link")]
        if not files:
            continue
        want_h = v.get("height") or 0
        want_w = v.get("width") or 0
        portrait = want_h > want_w
        # prefer the largest file at or under 1920 on the long edge
        def long_edge(f):
            return max(f.get("width") or 0, f.get("height") or 0)
        under = sorted([f for f in files if long_edge(f) <= 1920], key=long_edge)
        pick = under[-1] if under else sorted(files, key=long_edge)[0]
        e = base_entry("pexels", query)
        e.update({
            "id": str(v.get("id")),
            "title": (v.get("url") or "").rstrip("/").split("/")[-1].rsplit("-", 1)[0].replace("-", " ") or None,
            "duration": float(v.get("duration") or 0) or None,
            "width": pick.get("width"), "height": pick.get("height"),
            "file_url": pick["link"], "file_format": "mp4",
            "page_url": v.get("url"),
            "thumb_url": v.get("image"),
            "author": (v.get("user") or {}).get("name"),
            "license": "Pexels License (free to use, no attribution required)",
        })
        entries.append(finish_entry(e))
    return entries


def search_pixabay(query: str, args) -> list[dict]:
    key = args.pixabay_key or get_key("pixabay")
    if not key:
        raise MissingKey("pixabay", "PIXABAY_API_KEY", "https://pixabay.com/api/docs/")
    params = {"key": key, "q": query, "per_page": str(max(args.max_per_query * 3, 9)),
              "safesearch": "true"}
    if args.orientation == "portrait":
        params["orientation"] = "vertical"
    elif args.orientation == "landscape":
        params["orientation"] = "horizontal"
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(params)
    data = fetch_json(url)
    entries = []
    for hit in data.get("hits", []):
        variants = hit.get("videos") or {}
        cands = [v for v in variants.values() if v and v.get("url")]
        if not cands:
            continue
        def area(v):
            return (v.get("width") or 0) * (v.get("height") or 0)
        under = sorted([v for v in cands if max(v.get("width") or 0, v.get("height") or 0) <= 1920],
                       key=area)
        pick = under[-1] if under else sorted(cands, key=area)[-1]
        e = base_entry("pixabay", query)
        e.update({
            "id": str(hit.get("id")),
            "title": (hit.get("tags") or "").split(",")[0].strip() or None,
            "duration": float(hit.get("duration") or 0) or None,
            "width": pick.get("width"), "height": pick.get("height"),
            "file_url": pick["url"],
            "file_format": "mp4",
            "page_url": hit.get("pageURL"),
            "author": hit.get("user"),
            "license": "Pixabay Content License (free to use, no attribution required)",
        })
        entries.append(finish_entry(e))
    return entries


_LICENSE_MAP = [
    ("creativecommons.org/publicdomain/zero", "CC0 1.0 (public domain)"),
    ("creativecommons.org/licenses/by-nc", "CC BY-NC (non-commercial — check before use)"),
    ("creativecommons.org/licenses/by", "CC BY (attribution required)"),
    ("creativecommons.org/publicdomain/mark", "Public Domain Mark"),
]


def _friendly_license(licenseurl: str | None, collection: str) -> str:
    for needle, label in _LICENSE_MAP:
        if licenseurl and needle in licenseurl:
            return label
    if "prelinger" in collection:
        return "Prelinger Collection — free access, verify rights per item for commercial use"
    return licenseurl or "check item page"


def _archive_duration_to_seconds(text) -> float | None:
    if not text:
        return None
    text = str(text).strip()
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        sec = 0.0
        for p in parts:
            sec = sec * 60 + p
        return sec
    try:
        return float(text)
    except ValueError:
        return None


def search_archive(query: str, args) -> list[dict]:
    collection = (args.collection or "prelinger").lower()
    q = f"({query}) AND mediatype:(movies)"
    if collection != "any":
        q += f" AND collection:({collection})"
    params = {"q": q, "rows": str(max(args.max_per_query * 4, 12)), "page": "1", "output": "json"}
    url = ("https://archive.org/advancedsearch.php?" + urllib.parse.urlencode(params)
           + "&fl[]=identifier&fl[]=title&fl[]=year&fl[]=creator&fl[]=licenseurl")
    data = fetch_json(url)
    docs = (data.get("response") or {}).get("docs") or []
    entries = []
    for doc in docs:
        if len(entries) >= args.max_per_query:
            break
        ident = doc.get("identifier")
        if not ident:
            continue
        try:
            meta = fetch_json(f"https://archive.org/metadata/{urllib.parse.quote(ident)}")
        except ScoutError as exc:
            print(f"  ! archive: skip '{ident}' ({exc})", file=sys.stderr)
            continue
        mp4s = [f for f in meta.get("files", [])
                if str(f.get("name", "")).lower().endswith(".mp4")
                or str(f.get("format", "")).lower() in ("h.264", "mpeg4", "512kb mpeg4")]
        if not mp4s:
            continue
        def rank(f):
            name = str(f.get("format", "")).lower()
            size = int(f.get("size") or 0)
            return (0 if "h.264" in name else 1, -size)
        pick = sorted(mp4s, key=rank)[0]
        ident_q = urllib.parse.quote(ident)
        e = base_entry("archive", query)
        e.update({
            "id": str(ident),
            "title": doc.get("title") or ident,
            "duration": _archive_duration_to_seconds(pick.get("length")),
            "file_url": f"https://archive.org/download/{ident_q}/{urllib.parse.quote(pick['name'])}",
            "file_format": "mp4",
            "page_url": f"https://archive.org/details/{ident_q}",
            "thumb_url": f"https://archive.org/services/img/{ident_q}",
            "author": doc.get("creator") if isinstance(doc.get("creator"), str) else None,
            "license": _friendly_license(doc.get("licenseurl"), collection),
            "year": doc.get("year"),
        })
        entries.append(finish_entry(e))
        time.sleep(0.8)  # be polite to the metadata API
    return entries


def _strip_html(text) -> str | None:
    if not text:
        return None
    clean = re.sub(r"<[^>]+>", "", str(text))
    return clean.strip() or None


def search_wikimedia(query: str, args) -> list[dict]:
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"filetype:video {query}", "gsrnamespace": "6",
        "gsrlimit": str(max(args.max_per_query * 3, 9)),
        "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": "360",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    data = fetch_json(url)
    entries = []
    for page in (data.get("query") or {}).get("pages", {}).values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        original = info.get("url") or ""
        ext = os.path.splitext(urllib.parse.urlparse(original).path)[1].lstrip(".").lower()
        if ext not in ("webm", "ogv", "mp4", "mov", "ogg"):
            continue
        extmeta = info.get("extmetadata") or {}
        license_label = _strip_html((extmeta.get("LicenseShortName") or {}).get("value")) or "see file page"
        e = base_entry("wikimedia", query)
        e.update({
            "id": str(page.get("pageid")),
            "title": page.get("title"),
            "duration": None,
            "width": info.get("width"), "height": info.get("height"),
            "file_url": original,
            "file_format": ext,
            "page_url": f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(str(page.get('title') or '').replace(' ', '_'))}",
            "thumb_url": info.get("thumburl"),
            "author": _strip_html((extmeta.get("Artist") or {}).get("value")),
            "license": f"{license_label} (Wikimedia Commons)",
        })
        entries.append(finish_entry(e))
    return entries


SEARCHERS = {
    "pexels": search_pexels,
    "pixabay": search_pixabay,
    "archive": search_archive,
    "wikimedia": search_wikimedia,
}


# ---------------------------------------------------------------- ffmpeg extras

def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=10)
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def make_thumb(video_path: str, duration: float | None, out_path: str) -> str | None:
    at = max(0.5, min(1.0, (duration or 2) / 2))
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{at}", "-i", video_path,
             "-frames:v", "1", "-vf", "scale=360:-2", out_path],
            capture_output=True, timeout=60, check=True)
        return out_path
    except (OSError, subprocess.SubprocessError) as exc:
        err = getattr(exc, "stderr", None)
        print(f"  ! thumbnail failed for {os.path.basename(video_path)}: "
              f"{err.decode('utf-8', 'replace').strip() if err else exc}", file=sys.stderr)
        return None


def make_contact_sheet(thumbs: list[str], out_path: str) -> str | None:
    if len(thumbs) < 2:
        return None
    cols = min(4, len(thumbs))
    rows = max(1, math.ceil(len(thumbs) / cols))
    listing = out_path + ".list.txt"
    with open(listing, "w", encoding="utf-8") as fh:
        for t in thumbs:
            fh.write(f"file '{os.path.abspath(t)}'\nduration 0.12\n")
        fh.write(f"file '{os.path.abspath(thumbs[-1])}'\n")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
             "-i", listing, "-vf", f"scale=320:-2,tile={cols}x{rows}", "-frames:v", "1", out_path],
            capture_output=True, timeout=60, check=True)
        return out_path
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if os.path.exists(listing):
            os.remove(listing)


# ---------------------------------------------------------------- commands

def cmd_search(args) -> int:
    global OPENER, TIMEOUT, RETRIES
    TIMEOUT, RETRIES = args.timeout, args.retries
    OPENER = build_opener(args.proxy)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    queries = [q.strip() for q in args.queries.split(",") if q.strip()] if args.queries else []
    if args.queries_file:
        with open(args.queries_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        items = payload.get("queries", payload) if isinstance(payload, dict) else payload
        if isinstance(items, list):
            for it in items:
                queries.append(it if isinstance(it, str) else it.get("query", ""))
        elif isinstance(items, dict):
            for group, qlist in items.items():
                for q in (qlist if isinstance(qlist, list) else [qlist]):
                    queries.append(q if isinstance(q, str) else q.get("query", ""))
    queries = [q for q in dict.fromkeys(q for q in queries if q)]

    if not queries:
        print("error: no queries given (--queries 'a, b' or --queries-file file.json)", file=sys.stderr)
        return 2
    providers = [p.strip() for p in args.providers.split(",") if p.strip() in PROVIDERS]
    if not providers:
        print(f"error: --providers must be a subset of {','.join(PROVIDERS)}", file=sys.stderr)
        return 2

    manifest = {"tool": "footage-scout", "version": VERSION, "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "queries": queries, "providers": providers, "errors": [], "results": []}
    total = 0
    for query in queries:
        print(f"searching: {query}")
        for provider in providers:
            try:
                found = [e for e in SEARCHERS[provider](query, args) if keep(e, args)]
                found = found[: args.max_per_query]
            except MissingKey as exc:
                print(f"  - {provider}: {exc}")
                manifest["errors"].append({"query": query, "provider": provider, "error": str(exc)})
                continue
            except ScoutError as exc:
                print(f"  - {provider}: ERROR {exc}")
                manifest["errors"].append({"query": query, "provider": provider, "error": str(exc)})
                continue
            print(f"  - {provider}: {len(found)} candidate(s)")
            manifest["results"].extend(found)
            total += len(found)
            time.sleep(0.4)
    manifest["total"] = total
    mpath = os.path.join(out, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    for err in manifest["errors"]:
        print(f"note: {err['provider']}/{err['query']}: {err['error']}", file=sys.stderr)
    print(f"found {total} candidate(s) -> {mpath}")
    if total:
        print("next: python footage_scout.py download "
              f"--manifest \"{mpath}\" --top 2 --thumbs")
    return 0 if total else 2


def cmd_download(args) -> int:
    global OPENER, TIMEOUT, RETRIES
    TIMEOUT, RETRIES = args.timeout, args.retries
    OPENER = build_opener(args.proxy)
    with open(args.manifest, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    out = os.path.abspath(args.out or os.path.dirname(os.path.abspath(args.manifest)))
    dl_dir = os.path.join(out, "downloads")
    th_dir = os.path.join(out, "thumbs")
    os.makedirs(dl_dir, exist_ok=True)

    results = manifest.get("results", [])
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",") if i.strip()}
        selected = [e for e in results if e.get("id") in wanted]
    else:
        top = args.top
        per_query: dict = {}
        selected = []
        for e in results:
            per_query.setdefault(e["query"], []).append(e)
        for group in per_query.values():
            order = {"pexels": 0, "pixabay": 1, "archive": 2, "wikimedia": 3}
            group.sort(key=lambda e: (order.get(e["provider"], 9), -(e.get("duration") or 0)))
            selected.extend(group[:top])
    if not selected:
        print("error: nothing selected (bad --ids or empty manifest)", file=sys.stderr)
        return 2

    has_ffmpeg = ffmpeg_available() and args.thumbs
    if args.thumbs and not has_ffmpeg:
        print("note: ffmpeg not found on PATH, skipping thumbnails", file=sys.stderr)
    th_dir = os.path.join(out, "thumbs")
    if has_ffmpeg:
        os.makedirs(th_dir, exist_ok=True)

    manifest_path = os.path.abspath(args.manifest)
    by_index = {id(e): e for e in results}
    downloaded, thumbs_by_query = 0, {}
    for e in selected:
        ext = e.get("file_format") or "mp4"
        dest = os.path.join(dl_dir, f"{e['provider']}_{slugify(str(e['id']))}_{slugify(e['query'])}.{ext}")
        try:
            download_file(e["file_url"], dest, referer=e.get("page_url"))
        except ScoutError as exc:
            print(f"  ! download failed [{e['provider']}/{e['id']}]: {exc}", file=sys.stderr)
            manifest.setdefault("errors", []).append(
                {"query": e["query"], "provider": e["provider"], "error": f"download: {exc}"})
            continue
        e["local_file"] = dest
        e["chosen"] = True
        downloaded += 1
        print(f"  + {os.path.basename(dest)}  ({e.get('duration') or '?'}s, {e['license']})")
        sidecar = dest.rsplit(".", 1)[0] + ".license.json"
        with open(sidecar, "w", encoding="utf-8") as fh:
            json.dump({k: e.get(k) for k in
                       ("provider", "id", "title", "author", "license", "page_url",
                        "file_url", "query")}, fh, ensure_ascii=False, indent=2)
        if has_ffmpeg:
            thumb = make_thumb(dest, e.get("duration"),
                               os.path.join(th_dir, os.path.basename(dest).rsplit(".", 1)[0] + ".jpg"))
            if thumb and os.path.exists(thumb):
                e["thumb"] = thumb
                thumbs_by_query.setdefault(e["query"], []).append(thumb)

    sheets = []
    if has_ffmpeg:
        os.makedirs(th_dir, exist_ok=True)
        for query, thumbs in thumbs_by_query.items():
            sheet = make_contact_sheet(thumbs, os.path.join(out, f"sheet_{slugify(query)}.jpg"))
            if sheet:
                sheets.append(sheet)

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"downloaded {downloaded}/{len(selected)} clip(s) -> {dl_dir}")
    if sheets:
        print("contact sheets: " + "; ".join(sheets))
    print(f"manifest updated -> {manifest_path}")
    return 0 if downloaded else 2


# ---------------------------------------------------------------- cli

def main(argv=None) -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(prog="footage-scout", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--proxy", help="HTTP(S) proxy, e.g. http://127.0.0.1:7890 "
                                        "(archive.org & wikimedia are blocked on some CN networks)")
    common.add_argument("--timeout", type=int, default=15)
    common.add_argument("--retries", type=int, default=2)
    common.add_argument("--orientation", choices=["any", "landscape", "portrait", "square"], default="any")
    common.add_argument("--min-duration", type=float, default=0.0)
    common.add_argument("--max-duration", type=float, default=60.0)
    common.add_argument("--max-per-query", type=int, default=4)
    common.add_argument("--pexels-key", help="Pexels API key (or env PEXELS_API_KEY)")
    common.add_argument("--pixabay-key", help="Pixabay API key (or env PIXABAY_API_KEY)")

    ps = sub.add_parser("search", parents=[common], help="search providers, write manifest.json")
    ps.add_argument("--queries", help="comma-separated visual queries")
    ps.add_argument("--queries-file", help="JSON file: [\"q1\", ...] or {scene: [\"q1\", ...]}")
    ps.add_argument("--providers", default="pexels,pixabay,archive,wikimedia")
    ps.add_argument("--collection", default="prelinger",
                    help="archive.org collection filter (prelinger | nasa | any | ...)")
    ps.add_argument("--out", default="scout-" + time.strftime("%Y%m%d-%H%M%S"))
    ps.set_defaults(func=cmd_search)

    pd = sub.add_parser("download", parents=[common], help="download selected clips + thumbnails")
    pd.add_argument("--manifest", required=True)
    pd.add_argument("--ids", help="comma-separated entry ids to download (default: top N per query)")
    pd.add_argument("--top", type=int, default=2, help="clips per query when --ids not given")
    pd.add_argument("--thumbs", action="store_true", default=True)
    pd.add_argument("--no-thumbs", dest="thumbs", action="store_false")
    pd.add_argument("--out", help="output dir (default: manifest's dir)")
    pd.set_defaults(func=cmd_download)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
