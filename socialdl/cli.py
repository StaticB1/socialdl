#!/usr/bin/env python3
"""socialdl CLI — save images/videos from public social accounts.

Human-friendly by default; add --json for machine-readable output that AI
agents (or scripts) can parse. `--probe` reports what would download without
downloading.

Examples:
    socialdl natgeo --platform instagram --images-only
    socialdl https://www.instagram.com/natgeo/ --json
    socialdl @nasa -p tiktok --probe --json
    socialdl NASA -p facebook --since 2026-01-01 --cookies cookies.txt
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .config import DEFAULT_OUT
from .core import DownloadOptions, SUPPORTED_PLATFORMS, download, probe


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="socialdl",
        description="Save images/videos from public Instagram, TikTok, and Facebook accounts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  socialdl natgeo --platform instagram --images-only\n"
            "  socialdl https://www.instagram.com/natgeo/ --json\n"
            "  socialdl @nasa -p tiktok --probe --json\n"
            "  socialdl NASA -p facebook --since 2026-01-01 --cookies cookies.txt\n"
            "\n"
            "responsible use:\n"
            "  Only download media you have a right to access, and respect each\n"
            "  platform's Terms of Service and the rights of content owners.\n"
            "  Cookies make requests run as YOUR account, which platforms may\n"
            "  rate-limit or ban -- use a throwaway account. No warranty; see\n"
            "  the Legal & responsible use section of the README.\n"
        ),
    )
    p.add_argument("target", help="a username/@handle, or a full profile/post URL")
    p.add_argument("-p", "--platform", choices=sorted(SUPPORTED_PLATFORMS),
                   help="required for a bare username; auto-detected from URLs")
    p.add_argument("-o", "--out", default=None,
                   help=f"base output directory (default: {DEFAULT_OUT})")
    p.add_argument("-n", "--limit", type=int, metavar="N",
                   help="download at most N of the most recent items")

    kind = p.add_mutually_exclusive_group()
    kind.add_argument("--images-only", action="store_true", help="keep only images")
    kind.add_argument("--videos-only", action="store_true", help="keep only videos")

    p.add_argument("--since", metavar="YYYY-MM-DD", help="only posts on/after this date")
    p.add_argument("--until", metavar="YYYY-MM-DD", help="only posts on/before this date")
    p.add_argument("--top-liked", type=int, metavar="N", dest="top_liked",
                   help="rank posts by likes and take the top N (Instagram; "
                        "combine with --videos-only / --since to scope the scan)")
    p.add_argument("--metadata", action="store_true",
                   help="write a <file>.json sidecar of full post metadata")
    p.add_argument("--captions", action="store_true",
                   help="write the caption to a <file>.txt sidecar")
    p.add_argument("--backfill", action="store_true",
                   help="write captions+metadata sidecars for files ALREADY "
                        "downloaded (downloads no new media)")
    p.add_argument("--cookies", metavar="FILE",
                   help="path to a cookies.txt for authentication (best for headless use)")
    p.add_argument("--cookies-from-browser", metavar="BROWSER",
                   help="read cookies from a browser (firefox, chrome, ...)")
    p.add_argument("--no-archive", action="store_true",
                   help="ignore the dedup archive and re-fetch everything")
    p.add_argument("--timeout", type=float, default=600.0, metavar="SEC",
                   help="max seconds to run (default: 600)")

    p.add_argument("--probe", "--dry-run", dest="probe", action="store_true",
                   help="report what would download, without downloading")
    p.add_argument("--json", action="store_true",
                   help="emit the result as JSON (for scripts/agents)")
    p.add_argument("--version", action="version", version=f"socialdl {__version__}")
    return p


def _print_human(result, is_probe: bool, is_backfill: bool = False) -> None:
    r = result
    print(f"→ platform : {r.platform}")
    print(f"→ account  : {r.account}")
    print(f"→ source   : {r.source_url}")
    print(f"→ saving to: {r.output_dir}")
    n = r.downloaded_count
    imgs = sum(1 for f in r.downloaded if f.type == "image")
    vids = sum(1 for f in r.downloaded if f.type == "video")
    verb = "would download" if is_probe else "downloaded"
    if r.selected_posts:
        print(f"→ ranked by likes: top {len(r.selected_posts)} post(s)")
        for p in r.selected_posts:
            print(f"    likes={p['likes']:<6} {p['date']}  {p['type']:<5} {p['url']}")
    if r.ok:
        if is_backfill:
            print(f"✓ wrote caption/metadata sidecars for {r.skipped_count} "
                  "existing file(s); downloaded no new media")
        elif is_probe and r.selected_posts:
            print(f"✓ selected {len(r.selected_posts)} post(s) — run without --probe to download")
        else:
            extra = f" ({imgs} images, {vids} videos)" if (imgs or vids) else ""
            print(f"✓ {verb} {n} file{'s' if n != 1 else ''}{extra}"
                  + (f", {r.skipped_count} already present" if r.skipped_count else ""))
    for err in r.errors:
        print(f"! {err}", file=sys.stderr)


def _stream(line: str, is_err: bool) -> None:
    """Tee gallery-dl output to the terminal live so long runs aren't silent."""
    if line.strip():
        print(line, file=sys.stderr if is_err else sys.stdout, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    opts = DownloadOptions(
        target=args.target, platform=args.platform, out=args.out, limit=args.limit,
        images_only=args.images_only, videos_only=args.videos_only,
        since=args.since, until=args.until,
        metadata=args.metadata, captions=args.captions,
        cookies=args.cookies, cookies_from_browser=args.cookies_from_browser,
        no_archive=args.no_archive, timeout=args.timeout, top_liked=args.top_liked,
        backfill=args.backfill,
    )
    fn = probe if args.probe else download

    if args.json:
        result = fn(opts)                       # silent capture → clean JSON
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.ok else 1

    # Human mode: announce, then stream live output, then summarize.
    verb = "Probing" if args.probe else "Downloading"
    plat = args.platform or "auto-detect from URL"
    print(f"{verb} {args.target}  [{plat}]", file=sys.stderr)
    print("(live output below — this can take a while on large accounts; "
          "Ctrl-C to stop)\n", file=sys.stderr)
    try:
        result = fn(opts, _stream)
    except KeyboardInterrupt:
        print("\ninterrupted.", file=sys.stderr)
        return 130

    print()
    _print_human(result, is_probe=args.probe, is_backfill=args.backfill)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
