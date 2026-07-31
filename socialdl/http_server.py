#!/usr/bin/env python3
"""socialdl HTTP API — a small REST server around the downloader.

    socialdl-serve --host 127.0.0.1 --port 8000

Endpoints (interactive docs + OpenAPI schema at /docs and /openapi.json):
    GET  /health              -> {"status": "ok", "version": ...}
    GET  /platforms           -> {"platforms": [...]}
    POST /download            -> DownloadResult
    POST /probe               -> DownloadResult (simulated)

Bodies are JSON matching the DownloadRequest model. Bind to 127.0.0.1 (default)
for local agents; use --host 0.0.0.0 only on a trusted network.
"""
from __future__ import annotations

import argparse
import os

from fastapi import FastAPI
from pydantic import BaseModel, Field

from . import __version__
from .core import DownloadOptions, download, list_platforms, probe

app = FastAPI(
    title="socialdl",
    version=__version__,
    description="Download images/videos from public Instagram, TikTok, and Facebook accounts.",
)


class DownloadRequest(BaseModel):
    target: str = Field(..., description="username/@handle, or a full profile/post URL")
    platform: str | None = Field(None, description="instagram|tiktok|facebook (required for bare usernames)")
    limit: int | None = Field(None, description="max most-recent items to fetch")
    images_only: bool = False
    videos_only: bool = False
    since: str | None = Field(None, description="only posts on/after YYYY-MM-DD")
    until: str | None = Field(None, description="only posts on/before YYYY-MM-DD")
    metadata: bool = Field(False, description="write <file>.json sidecar of full metadata")
    captions: bool = Field(False, description="write <file>.txt caption sidecar")
    cookies: str | None = Field(None, description="path to a cookies.txt for authentication")
    out: str | None = Field(None, description="base output directory")
    no_archive: bool = Field(False, description="ignore dedup archive, re-fetch everything")
    timeout: float = Field(600.0, description="max seconds to run")
    top_liked: int | None = Field(None, description="rank posts by likes, take top N (Instagram)")
    backfill: bool = Field(False, description="write sidecars for already-downloaded files; no new media")

    def to_options(self) -> DownloadOptions:
        return DownloadOptions(**self.model_dump())


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/platforms")
def platforms() -> dict:
    return {"platforms": list_platforms()}


@app.post("/download")
def download_endpoint(req: DownloadRequest) -> dict:
    return download(req.to_options()).to_dict()


@app.post("/probe")
def probe_endpoint(req: DownloadRequest) -> dict:
    return probe(req.to_options()).to_dict()


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser(prog="socialdl-serve", description="Run the socialdl HTTP API.")
    p.add_argument("--host", default=os.environ.get("SOCIALDL_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("SOCIALDL_PORT", "8000")))
    args = p.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
