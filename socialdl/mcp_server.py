#!/usr/bin/env python3
"""socialdl MCP server — exposes the downloader as Model Context Protocol tools.

Run over stdio (the standard MCP transport):

    socialdl-mcp

Then register it with an MCP client (Claude Desktop, Cursor, etc.). Example
Claude Desktop config entry:

    "socialdl": { "command": "/abs/path/.venv/bin/socialdl-mcp" }

Tools exposed: download_media, probe_media, list_platforms.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .core import DownloadOptions, SUPPORTED_PLATFORMS, download, list_platforms, probe

mcp = FastMCP("socialdl")

_COMMON_DOC = """
    Args:
      target: A username/@handle (then set `platform`) or a full profile/post URL.
      platform: One of instagram, tiktok, facebook. Required for bare usernames;
                auto-detected from URLs.
      limit: Download at most N of the most recent items.
      images_only: Keep only images (skip videos).
      videos_only: Keep only videos (skip images).
      since: Only posts on/after this date, "YYYY-MM-DD".
      until: Only posts on/before this date, "YYYY-MM-DD".
      metadata: Also write a <file>.json sidecar of full post metadata.
      captions: Also write the caption to a <file>.txt sidecar.
      cookies: Path to a cookies.txt for authentication. These platforms almost
               always require login even for public accounts; without cookies most
               fetches fail. Export one from a logged-in browser.
      out: Base output directory (defaults to the configured location).
      timeout: Max seconds to run.
"""


def _opts(**kw) -> DownloadOptions:
    return DownloadOptions(**{k: v for k, v in kw.items() if v is not None})


@mcp.tool()
def download_media(
    target: str,
    platform: str | None = None,
    limit: int | None = None,
    images_only: bool = False,
    videos_only: bool = False,
    since: str | None = None,
    until: str | None = None,
    metadata: bool = False,
    captions: bool = False,
    cookies: str | None = None,
    out: str | None = None,
    no_archive: bool = False,
    timeout: float = 600.0,
    top_liked: int | None = None,
    backfill: bool = False,
) -> dict:
    """Download images/videos from a public social account into organized folders.

    Files are saved to <out>/<platform>/<account>/. Re-running is safe: an
    archive skips items already downloaded (unless no_archive=True). Returns a
    structured result with the list of downloaded files, counts, and any errors.

    top_liked: if set, rank posts by like count and download the top N instead
      of newest-first (Instagram only). Combine with videos_only/since to scope
      the scan. Ranking must enumerate the window first, so it can be slow.
    backfill: if true, write caption/metadata sidecars for files ALREADY on disk
      without downloading any new media (implies metadata+captions).
    """ + _COMMON_DOC
    return download(_opts(
        target=target, platform=platform, limit=limit,
        images_only=images_only, videos_only=videos_only,
        since=since, until=until, metadata=metadata, captions=captions,
        cookies=cookies, out=out, no_archive=no_archive, timeout=timeout,
        top_liked=top_liked, backfill=backfill,
    )).to_dict()


@mcp.tool()
def probe_media(
    target: str,
    platform: str | None = None,
    limit: int | None = None,
    images_only: bool = False,
    videos_only: bool = False,
    since: str | None = None,
    until: str | None = None,
    cookies: str | None = None,
    timeout: float = 600.0,
    top_liked: int | None = None,
) -> dict:
    """Dry-run: report what WOULD be downloaded for a target, without downloading.

    Use this to check counts/filters (and whether credentials work) before a real
    download_media call. Returns the same structured shape with simulated=true and
    the would-download files listed under `downloaded`. With top_liked set, returns
    the like-ranked posts under `selected_posts` (no media downloaded).
    """ + _COMMON_DOC
    return probe(_opts(
        target=target, platform=platform, limit=limit,
        images_only=images_only, videos_only=videos_only,
        since=since, until=until, cookies=cookies, timeout=timeout,
        top_liked=top_liked,
    )).to_dict()


@mcp.tool()
def supported_platforms() -> list[str]:
    """List the social platforms this tool can download from."""
    return list_platforms()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
