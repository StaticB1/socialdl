"""Core download logic, shared by the CLI, MCP server, and HTTP API.

Everything here is UI-agnostic: `download()` and `probe()` take a
`DownloadOptions` and return a `DownloadResult` that serializes cleanly to
JSON. No printing, no sys.exit — callers decide how to present the result.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable

from . import config

SUPPORTED_PLATFORMS = ("instagram", "tiktok", "facebook")

# Domain fragments used to auto-detect the platform from a URL.
PLATFORM_DOMAINS = {
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
    "facebook": ("facebook.com", "fb.com", "fb.watch"),
}

IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif", "heic", "heif")
VIDEO_EXTS = ("mp4", "mov", "webm", "mkv", "m4v", "m4a")
SIDECAR_EXTS = ("json", "txt")

# Instagram post `type` values that are videos (used by --top-liked selection).
VIDEO_POST_TYPES = ("reel", "tv", "igtv", "clips")
# Safety cap on how many posts --top-liked will enumerate while ranking.
SCAN_CAP = 1000


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #
@dataclass
class DownloadOptions:
    """All inputs for a download/probe. Unset (None) fields fall back to
    environment variables and the config file."""
    target: str
    platform: str | None = None
    out: str | None = None
    limit: int | None = None
    images_only: bool = False
    videos_only: bool = False
    since: str | None = None          # "YYYY-MM-DD"
    until: str | None = None          # "YYYY-MM-DD"
    metadata: bool = False            # write <file>.json sidecar
    captions: bool = False            # write <file>.txt caption
    cookies: str | None = None        # path to a cookies.txt
    cookies_from_browser: str | None = None
    no_archive: bool = False          # ignore the dedup archive (force re-fetch)
    timeout: float | None = 600.0     # seconds; None disables
    top_liked: int | None = None      # rank posts by likes; take the top N (Instagram)
    backfill: bool = False            # write sidecars for already-downloaded files
                                      # (no media downloaded); implies metadata+captions


@dataclass
class MediaFile:
    path: str
    filename: str
    type: str                         # image | video | other
    size_bytes: int | None = None


@dataclass
class DownloadResult:
    ok: bool
    target: str
    platform: str | None = None
    account: str | None = None
    source_url: str | None = None
    output_dir: str | None = None
    downloaded: list[MediaFile] = field(default_factory=list)
    downloaded_count: int = 0
    skipped_count: int = 0            # already present (archive dedup)
    wrote_metadata: bool = False
    wrote_captions: bool = False
    simulated: bool = False
    exit_code: int | None = None
    errors: list[str] = field(default_factory=list)
    # Populated only by --top-liked: the ranked posts that were chosen.
    selected_posts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class InstaError(ValueError):
    """Bad input (unknown platform, malformed date, ...)."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def detect_platform(target: str) -> str | None:
    """Return the platform for a URL, or None if it isn't a recognized URL."""
    if not re.match(r"^https?://", target, re.I):
        return None
    for platform, domains in PLATFORM_DOMAINS.items():
        if any(d in target.lower() for d in domains):
            return platform
    return None


def build_url(target: str, platform: str) -> str:
    """Turn a bare username/@handle into a profile URL for the platform."""
    handle = target.lstrip("@").strip("/")
    if platform == "instagram":
        return f"https://www.instagram.com/{handle}/"
    if platform == "tiktok":
        return f"https://www.tiktok.com/@{handle}"
    if platform == "facebook":
        return f"https://www.facebook.com/{handle}"
    raise InstaError(f"unknown platform: {platform!r}")


def account_label(target: str, platform: str) -> str:
    """A filesystem-safe folder name for this account."""
    if detect_platform(target):
        path = re.sub(r"^https?://[^/]+/", "", target, flags=re.I)
        seg = path.strip("/").split("/")[0] or "account"
        label = seg.lstrip("@")
    else:
        label = target.lstrip("@").strip("/")
    return re.sub(r"[^A-Za-z0-9._@-]", "_", label) or "account"


def _valid_date(value: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    if not m:
        raise InstaError(f"date must be YYYY-MM-DD, got {value!r}")
    y, mo, d = (int(g) for g in m.groups())
    try:
        _dt.date(y, mo, d)
    except ValueError as exc:
        raise InstaError(f"invalid date {value!r}: {exc}")
    return y, mo, d


def _classify(ext: str) -> str | None:
    ext = ext.lower().lstrip(".")
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in SIDECAR_EXTS:
        return None                   # sidecar, not a media item
    return "other"


def _build_filter(opts: DownloadOptions) -> str | None:
    """Compose the gallery-dl --filter expression from date/type options.

    Feeds are newest-first, so --since uses `or abort()` to stop paginating
    once posts older than the cutoff are reached. Videos can bypass the file
    filter, so images-only is handled via the extractor's `videos=false`.
    """
    parts: list[str] = []
    if opts.since:
        y, mo, d = _valid_date(opts.since)
        parts.append(f"(date >= datetime({y}, {mo}, {d}) or abort())")
    if opts.until:
        y, mo, d = _valid_date(opts.until)
        parts.append(f"date <= datetime({y}, {mo}, {d}, 23, 59, 59)")
    if opts.videos_only:
        parts.append(f"extension not in {IMAGE_EXTS!r}")
    return " and ".join(parts) if parts else None


# --------------------------------------------------------------------------- #
# Command building + execution
# --------------------------------------------------------------------------- #
def _resolve_options(opts: DownloadOptions) -> dict:
    """Apply env/config fallbacks; validate; return a plan dict."""
    if opts.images_only and opts.videos_only:
        raise InstaError("images_only and videos_only are mutually exclusive")

    platform = opts.platform or detect_platform(opts.target)
    if platform is None:
        raise InstaError(
            "could not detect platform; pass platform="
            f"{'|'.join(SUPPORTED_PLATFORMS)} or a full URL"
        )
    if platform not in SUPPORTED_PLATFORMS:
        raise InstaError(f"unsupported platform {platform!r}")

    # Validate dates up front so bad input becomes a structured error, not a
    # crash deep in command building.
    if opts.since:
        _valid_date(opts.since)
    if opts.until:
        _valid_date(opts.until)

    cfg = config.load_config()
    out_val = config.resolve(opts.out, "SOCIALDL_OUT", cfg, "out", str(config.DEFAULT_OUT))
    cookies = config.resolve(opts.cookies, "SOCIALDL_COOKIES", cfg, "cookies")
    cfb = config.resolve(
        opts.cookies_from_browser, "SOCIALDL_COOKIES_FROM_BROWSER",
        cfg, "cookies_from_browser",
    )
    want_meta = config.resolve_bool(opts.metadata, "SOCIALDL_METADATA", cfg, "metadata")
    want_caps = config.resolve_bool(opts.captions, "SOCIALDL_CAPTIONS", cfg, "captions")
    # Backfill is meaningless without sidecars — default to writing both.
    if opts.backfill and not (want_meta or want_caps):
        want_meta = want_caps = True

    is_url = bool(detect_platform(opts.target))
    url = opts.target if is_url else build_url(opts.target, platform)
    label = account_label(opts.target, platform)
    dest = (Path(out_val).expanduser() / platform / label).resolve()

    return {
        "platform": platform, "url": url, "label": label, "dest": dest,
        "cookies": cookies, "cookies_from_browser": cfb,
        "metadata": want_meta, "captions": want_caps,
    }


def _build_command(opts: DownloadOptions, plan: dict, simulate: bool) -> list[str]:
    cmd = [sys.executable, "-m", "gallery_dl", "--directory", str(plan["dest"])]

    if simulate:
        cmd.append("--simulate")
    elif opts.backfill:
        # Write sidecars for files already on disk; download no media. The
        # archive is skipped so the file-exists check (and 'skip' event) fires.
        cmd.append("--no-download")
    elif not opts.no_archive:
        # Per-account archive so re-runs only fetch new posts.
        cmd += ["--download-archive", str(plan["dest"] / ".archive.sqlite")]

    if opts.limit:
        cmd += ["--range", f"1-{int(opts.limit)}"]
    if opts.images_only:
        cmd += ["-o", "videos=false"]

    filt = _build_filter(opts)
    if filt:
        cmd += ["--filter", filt]

    # In backfill mode, fire the metadata postprocessor ONLY on the 'skip'
    # event (files already on disk). Under --no-download the 'file' event still
    # fires for absent posts, which would create orphan sidecars — so exclude it.
    ev = {"event": "skip"} if opts.backfill else {}
    pp = []
    if plan["metadata"]:
        pp.append({"name": "metadata", "mode": "json", **ev})
    if plan["captions"]:
        pp.append({"name": "metadata", "mode": "custom",
                   "extension": "txt", "content-format": "{description}\n", **ev})
    if pp and not simulate:
        cmd += ["-o", "postprocessors=" + json.dumps(pp)]

    if plan["cookies"]:
        cmd += ["--cookies", str(Path(plan["cookies"]).expanduser())]
    if plan["cookies_from_browser"]:
        cmd += ["--cookies-from-browser", plan["cookies_from_browser"]]

    cmd.append(plan["url"])
    return cmd


def _parse_output(stdout: str, dest: Path, simulate: bool) -> tuple[list[MediaFile], int]:
    """Parse gallery-dl's stdout into (media_files, skipped_count).

    Real mode: a plain path line = a file just downloaded; `# path` = a file
    skipped because it's already in the archive.
    Simulate mode: gallery-dl prints `# <name>` for every item it *would*
    download — those are the results, and nothing is "skipped".
    """
    downloaded: list[MediaFile] = []
    skipped = 0
    for raw in stdout.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        is_hashed = line.startswith("# ")
        path_str = line[2:] if is_hashed else line

        if is_hashed and not simulate:
            skipped += 1
            continue

        p = Path(path_str)
        if not p.is_absolute():
            p = dest / path_str
        kind = _classify(p.suffix)
        if kind is None:      # sidecar (.json/.txt) — not a media item
            continue
        size = p.stat().st_size if p.exists() else None
        downloaded.append(MediaFile(str(p), p.name, kind, size))
    return downloaded, skipped


def _extract_errors(stderr: str) -> list[str]:
    errors = []
    for line in stderr.splitlines():
        line = line.strip()
        if not line:
            continue
        if "][error]" in line or line.startswith("[error]") or "Error" in line:
            errors.append(line)
    return errors


def _run_capture(cmd: list[str], timeout: float | None) -> tuple[int, str, str]:
    """Run to completion, capturing all output (silent — for agents/JSON)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        return 124, out, f"timed out after {timeout}s"


def _run_streaming(
    cmd: list[str], timeout: float | None, on_output: Callable[[str, bool], None]
) -> tuple[int, str, str]:
    """Run while teeing each line to `on_output(line, is_stderr)` live, and also
    buffering stdout/stderr for parsing. Gives the CLI real-time feedback."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1,
    )
    out_buf: list[str] = []
    err_buf: list[str] = []

    def reader(stream, buf, is_err):
        for line in stream:
            buf.append(line)
            on_output(line.rstrip("\n"), is_err)
        stream.close()

    threads = [
        threading.Thread(target=reader, args=(proc.stdout, out_buf, False)),
        threading.Thread(target=reader, args=(proc.stderr, err_buf, True)),
    ]
    for t in threads:
        t.start()

    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait()
    for t in threads:
        t.join()

    code = 124 if timed_out else proc.returncode
    stderr = "".join(err_buf) + (f"\ntimed out after {timeout}s" if timed_out else "")
    return code, "".join(out_buf), stderr


def _execute(
    opts: DownloadOptions, simulate: bool,
    on_output: Callable[[str, bool], None] | None = None,
) -> DownloadResult:
    try:
        plan = _resolve_options(opts)
    except InstaError as exc:
        return DownloadResult(ok=False, target=opts.target, errors=[str(exc)])

    result = DownloadResult(
        ok=False, target=opts.target, platform=plan["platform"],
        account=plan["label"], source_url=plan["url"],
        output_dir=str(plan["dest"]), simulated=simulate,
        wrote_metadata=plan["metadata"] and not simulate,
        wrote_captions=plan["captions"] and not simulate,
    )

    plan["dest"].mkdir(parents=True, exist_ok=True)
    cmd = _build_command(opts, plan, simulate)

    try:
        if on_output is not None:
            code, stdout, stderr = _run_streaming(cmd, opts.timeout, on_output)
        else:
            code, stdout, stderr = _run_capture(cmd, opts.timeout)
    except FileNotFoundError:
        return DownloadResult(
            ok=False, target=opts.target,
            errors=[f"Python interpreter not found: {sys.executable}"],
        )

    downloaded, skipped = _parse_output(stdout, plan["dest"], simulate)
    errors = _extract_errors(stderr)
    if "No module named gallery_dl" in stderr:
        errors = ["gallery-dl is not installed in this environment; run setup.sh"]

    result.skipped_count = skipped
    result.exit_code = code
    result.errors = errors
    if opts.backfill:
        # --no-download: nothing is fetched. Would-download paths (parsed as
        # 'downloaded') are not real; only skipped==existing files got sidecars.
        result.downloaded = []
        result.downloaded_count = 0
        result.ok = not errors            # --no-download's exit code is not a failure
    else:
        result.downloaded = downloaded
        result.downloaded_count = len(downloaded)
        result.ok = code == 0 and not errors

    # Helpful nudge when an unauthenticated fetch fails.
    if not result.ok and not (plan["cookies"] or plan["cookies_from_browser"]):
        result.errors.append(
            "no credentials provided — these platforms usually require login; "
            "pass cookies (a cookies.txt path) to authenticate"
        )
    return result


# --------------------------------------------------------------------------- #
# --top-liked: rank posts by likes, then download the top N
# --------------------------------------------------------------------------- #
def _posts_scan_url(platform: str, profile_url: str) -> str:
    """The listing endpoint that yields per-post metadata (incl. likes)."""
    if platform != "instagram":
        raise InstaError("--top-liked is currently supported for Instagram only")
    return profile_url.rstrip("/") + "/posts/"


def _scan_posts(plan: dict, opts: DownloadOptions, on_output) -> list[dict]:
    """Enumerate posts (deduped) with their like counts, without downloading."""
    if any(seg in plan["url"] for seg in ("/p/", "/reel/", "/tv/")):
        raise InstaError("--top-liked needs an account/profile, not a single post URL")

    scan_url = _posts_scan_url(plan["platform"], plan["url"])
    cmd = [sys.executable, "-m", "gallery_dl", "-j", "--range", f"1-{SCAN_CAP}"]
    if opts.since:
        y, mo, d = _valid_date(opts.since)
        cmd += ["--filter", f"date >= datetime({y}, {mo}, {d}) or abort()"]
    if plan["cookies"]:
        cmd += ["--cookies", str(Path(plan["cookies"]).expanduser())]
    if plan["cookies_from_browser"]:
        cmd += ["--cookies-from-browser", plan["cookies_from_browser"]]
    cmd.append(scan_url)

    # Stream only stderr (progress) — stdout is the big JSON blob we parse.
    if on_output is not None:
        tee = lambda line, is_err: on_output(line, is_err) if is_err else None
        code, out, _err = _run_streaming(cmd, opts.timeout, tee)
    else:
        code, out, _err = _run_capture(cmd, opts.timeout)

    if code == 124:
        raise InstaError(
            "scan timed out — use a more recent --since, or raise --timeout"
        )
    try:
        rows = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        raise InstaError("could not parse post metadata from the scan")

    seen: dict[str, dict] = {}
    for row in rows:
        d = next((x for x in row if isinstance(x, dict)), {})
        sc = d.get("post_shortcode")
        if sc and sc not in seen:
            seen[sc] = {
                "shortcode": sc,
                "likes": d.get("likes") or 0,
                "type": d.get("type"),
                "url": d.get("post_url"),
                "date": str(d.get("date"))[:10] if d.get("date") else None,
            }
    return list(seen.values())


def _rank_posts(opts: DownloadOptions, plan: dict, on_output) -> list[dict]:
    posts = _scan_posts(plan, opts, on_output)
    if opts.videos_only:
        cand = [p for p in posts if p["type"] in VIDEO_POST_TYPES]
    elif opts.images_only:
        cand = [p for p in posts if p["type"] not in VIDEO_POST_TYPES]
    else:
        cand = list(posts)
    cand.sort(key=lambda p: (p["likes"] or 0, p["date"] or ""), reverse=True)
    return cand[: max(0, int(opts.top_liked))]


def _download_post(post_url: str, plan: dict, opts: DownloadOptions, on_output):
    """Download a single post URL into the account's folder."""
    post_opts = replace(opts, target=post_url, top_liked=None,
                        since=None, until=None, limit=None)
    post_plan = dict(plan)
    post_plan["url"] = post_url            # dest stays the account folder
    cmd = _build_command(post_opts, post_plan, simulate=False)
    if on_output is not None:
        code, out, err = _run_streaming(cmd, opts.timeout, on_output)
    else:
        code, out, err = _run_capture(cmd, opts.timeout)
    files, skipped = _parse_output(out, post_plan["dest"], simulate=False)
    return files, skipped, _extract_errors(err), code


def _selected_summary(selected: list[dict]) -> list[dict]:
    return [{"url": p["url"], "likes": p["likes"], "date": p["date"],
             "type": p["type"]} for p in selected]


def _top_liked_download(opts: DownloadOptions, plan: dict, on_output) -> DownloadResult:
    selected = _rank_posts(opts, plan, on_output)
    dest = plan["dest"]
    dest.mkdir(parents=True, exist_ok=True)

    result = DownloadResult(
        ok=False, target=opts.target, platform=plan["platform"],
        account=plan["label"], source_url=plan["url"], output_dir=str(dest),
        wrote_metadata=plan["metadata"], wrote_captions=plan["captions"],
        selected_posts=_selected_summary(selected),
    )
    if not selected:
        result.errors.append("no matching posts found in the scan window")
        result.exit_code = 0
        return result

    files, errors, skipped, codes = [], [], 0, []
    for p in selected:
        if on_output is not None:
            on_output(f"↓ likes={p['likes']}  {p['url']}", True)
        f, sk, errs, code = _download_post(p["url"], plan, opts, on_output)
        files += f
        skipped += sk
        errors += errs
        codes.append(code)

    result.downloaded = files
    result.downloaded_count = len(files)
    result.skipped_count = skipped
    result.errors = errors
    result.exit_code = 0 if all(c == 0 for c in codes) else max(codes)
    result.ok = all(c == 0 for c in codes) and not errors
    return result


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def download(
    opts: DownloadOptions,
    on_output: Callable[[str, bool], None] | None = None,
) -> DownloadResult:
    """Download media for `opts.target` and return a structured result.

    If `on_output` is given, each line of gallery-dl output is streamed to it
    live as (line, is_stderr) — used by the CLI for real-time progress. When
    None (the default, used by MCP/HTTP), output is captured silently.
    """
    if opts.top_liked:
        try:
            plan = _resolve_options(opts)
            return _top_liked_download(opts, plan, on_output)
        except InstaError as exc:
            return DownloadResult(ok=False, target=opts.target, errors=[str(exc)])
    return _execute(opts, simulate=False, on_output=on_output)


def probe(
    opts: DownloadOptions,
    on_output: Callable[[str, bool], None] | None = None,
) -> DownloadResult:
    """Dry-run: report what *would* be downloaded, without downloading.

    With `top_liked`, this scans and ranks posts by likes and returns the chosen
    posts under `selected_posts` — without downloading any media.
    """
    if opts.top_liked:
        try:
            plan = _resolve_options(opts)
            selected = _rank_posts(opts, plan, on_output)
        except InstaError as exc:
            return DownloadResult(ok=False, target=opts.target,
                                  simulated=True, errors=[str(exc)])
        return DownloadResult(
            ok=True, target=opts.target, platform=plan["platform"],
            account=plan["label"], source_url=plan["url"],
            output_dir=str(plan["dest"]), simulated=True, exit_code=0,
            selected_posts=_selected_summary(selected),
        )
    return _execute(opts, simulate=True, on_output=on_output)


def list_platforms() -> list[str]:
    return list(SUPPORTED_PLATFORMS)
