# socialdl

Save **images and videos from public social accounts** — Instagram, TikTok, and
Facebook — into tidy, per-account folders. Built for **AI agents** as well as
humans: it ships as a **CLI** (with JSON output), an **MCP server**, an **HTTP
REST API**, and an importable **Python library**, all sharing one core that
returns structured, machine-readable results.

Under the hood it drives [gallery-dl](https://github.com/mikf/gallery-dl), the
actively-maintained downloader that handles each platform's quirks.

```
downloads/
├── instagram/natgeo/  photo.jpg  photo.jpg.json  photo.jpg.txt  ...
├── tiktok/nasa/        ...
└── facebook/NASA/      ...
```

> **Before you use this:** it downloads only what your own account can already
> see, but you are responsible for respecting each platform's Terms of Service,
> copyright, and privacy. Authenticating with your cookies can get that account
> banned. See [Legal & responsible use](#legal--responsible-use).

## Setup

```bash
./setup.sh     # venv + editable install + links socialdl/socialdl-mcp/socialdl-serve into ~/.local/bin
```

This installs three commands (from the venv): `socialdl`, `socialdl-mcp`,
`socialdl-serve`.

## Authentication (read this first)

As of 2026, these platforms block anonymous access and require login **even for
public accounts** — without credentials most fetches fail (`NotFoundError`,
`403 Forbidden`). Provide a **`cookies.txt`** exported from a browser where
you're logged in — this is the portable choice for headless/agent use:

- Export with a "cookies.txt" browser extension (Netscape format), or
  `yt-dlp --cookies-from-browser firefox --cookies cookies.txt` to generate one.
- Pass it as `--cookies cookies.txt` (CLI), the `cookies` field (MCP/HTTP), or
  set `cookies` in the config file.

For **interactive/local** use you can instead read cookies live from a browser
with `--cookies-from-browser firefox` (not available on headless servers).

> ⚠️ **Account-ban risk — use a throwaway account, not your main one.**
> Your cookies make every request run as *your* account. Instagram, TikTok, and
> Facebook actively detect automated access and may **rate-limit, temporarily
> "action-block", or permanently ban** the account whose cookies you use — this
> happens even at slow speeds, and people have had accounts flagged this way.
> To stay safe:
> - Use a **secondary "burner" account** you can afford to lose — never your
>   personal/main account.
> - Keep volume low: scope with `--limit`, `--since`, and `--top-liked` instead
>   of pulling entire histories.
> - If you hit `429 Too Many Requests` or an action-block, **stop and wait hours
>   or days** — retrying aggressively lengthens the ban.
> - A ban is a risk **you** accept by using cookies; this tool can't prevent it.

## The four interfaces

### 1. CLI (with `--json`)

```bash
socialdl natgeo --platform instagram --images-only --cookies cookies.txt
socialdl https://www.instagram.com/natgeo/ --json          # machine-readable
socialdl @nasa -p tiktok --probe --json                     # dry-run: what WOULD download
```

`--json` prints the structured result (below) to stdout; exit code is `0` on
success, `1` otherwise — ideal for agents that shell out.

### 2. MCP server

```bash
socialdl-mcp        # speaks MCP over stdio
```

Register it with an MCP client. Example Claude Desktop / Claude Code config:

```json
{ "mcpServers": { "socialdl": { "command": "/ABSOLUTE/PATH/TO/socialdl/.venv/bin/socialdl-mcp" } } }
```

Tools exposed: **`download_media`**, **`probe_media`**, **`supported_platforms`** —
each with typed parameters (`target`, `platform`, `limit`, `images_only`,
`videos_only`, `since`, `until`, `metadata`, `captions`, `cookies`, `out`, …).

### 3. HTTP REST API

```bash
socialdl-serve --host 127.0.0.1 --port 8000     # OpenAPI docs at /docs
```

| Method | Path | Body / Result |
|--------|------|---------------|
| `GET`  | `/health` | `{"status":"ok","version":...}` |
| `GET`  | `/platforms` | `{"platforms":[...]}` |
| `POST` | `/download` | `DownloadRequest` → `DownloadResult` |
| `POST` | `/probe` | `DownloadRequest` → `DownloadResult` (simulated) |

```bash
curl -X POST http://127.0.0.1:8000/download -H 'Content-Type: application/json' \
  -d '{"target":"natgeo","platform":"instagram","images_only":true,
       "limit":10,"cookies":"/path/cookies.txt"}'
```

Bind to `127.0.0.1` for local agents; only use `--host 0.0.0.0` on a trusted
network (there is no auth layer).

### 4. Python library

```python
from socialdl import download, probe, DownloadOptions

result = download(DownloadOptions(
    target="natgeo", platform="instagram",
    images_only=True, limit=10, cookies="cookies.txt",
))
print(result.to_dict())
for f in result.downloaded:
    print(f.type, f.path, f.size_bytes)
```

## Structured result

Every interface returns the same shape:

```jsonc
{
  "ok": true,
  "target": "natgeo",
  "platform": "instagram",
  "account": "natgeo",
  "source_url": "https://www.instagram.com/natgeo/",
  "output_dir": ".../downloads/instagram/natgeo",
  "downloaded": [
    {"path": ".../photo.jpg", "filename": "photo.jpg", "type": "image", "size_bytes": 161547}
  ],
  "downloaded_count": 1,
  "skipped_count": 0,     // already present (deduped via archive)
  "wrote_metadata": false,
  "wrote_captions": false,
  "simulated": false,     // true for probe
  "exit_code": 0,
  "errors": []
}
```

## Options reference

| Option | CLI flag | MCP/HTTP field | Meaning |
|--------|----------|----------------|---------|
| Platform | `-p, --platform` | `platform` | `instagram`/`tiktok`/`facebook`; required for bare usernames |
| Limit | `-n, --limit N` | `limit` | Most-recent N items |
| Images only | `--images-only` | `images_only` | Skip videos |
| Videos only | `--videos-only` | `videos_only` | Skip images |
| Since | `--since YYYY-MM-DD` | `since` | Posts on/after date |
| Until | `--until YYYY-MM-DD` | `until` | Posts on/before date |
| Top by likes | `--top-liked N` | `top_liked` | Rank posts by likes; take the top N (Instagram) |
| Metadata | `--metadata` | `metadata` | Write `<file>.json` sidecar |
| Captions | `--captions` | `captions` | Write `<file>.txt` caption |
| Cookies | `--cookies FILE` | `cookies` | Path to a `cookies.txt` |
| Output dir | `-o, --out DIR` | `out` | Base download folder |
| No archive | `--no-archive` | `no_archive` | Ignore dedup archive; re-fetch |
| Backfill sidecars | `--backfill` | `backfill` | Write captions/metadata for files already downloaded (no new media) |
| Timeout | `--timeout SEC` | `timeout` | Max seconds to run |
| Probe | `--probe` | (own endpoint/tool) | Dry-run; report without downloading |

### Filtering by date and type

Feeds are newest-first, so `--since` **stops early** once it reaches posts older
than the cutoff — it won't crawl a whole back-catalog.

**Caveat on dates + videos:** date filtering is reliable for *images*. Videos
(esp. reels) are fetched through a path that can ignore the date filter, so on
video-heavy/video-only accounts `since`/`until` may pull more than the window.
For precise date-bounded results, add `images_only`.

### Most-liked posts (`--top-liked`)

Instagram only serves posts newest-first — there's no "sort by popularity". So
`--top-liked N` **scans** a window of posts, reads each one's like count, ranks
them, and downloads the top N:

```bash
# the 5 most-liked videos since a date:
socialdl natgeo -p instagram --videos-only --since 2025-06-01 --top-liked 5

# preview the ranking first, without downloading:
socialdl natgeo -p instagram --videos-only --since 2025-06-01 --top-liked 5 --probe
```

- **Scope the scan** with `--since` (and it stops early past the cutoff) — an
  unbounded scan is slow, so a date or recent window is strongly recommended.
- `--videos-only` ranks video posts (reels/tv); `--images-only` ranks the rest.
- Instagram-only for now; scanning a large window can take minutes (you'll see
  live progress). The `probe` form is cheap — it ranks without downloading.
- Limitation: video posts inside regular feed carousels aren't classified as
  "video" during ranking (reels/tv are); the date boundary is also fuzzy for
  reels (same reason as the date caveat above).

### Captions & metadata

Next to `photo.jpg` you get `photo.jpg.txt` (the caption, via `captions`) and/or
`photo.jpg.json` (full metadata: `description`, `date`, `likes`, `tags`,
`post_url`, `username`, … via `metadata`). Carousels get one sidecar per image.

**Backfilling already-downloaded files.** A normal re-run skips posts already in
the archive, so it won't add sidecars to files you grabbed earlier. `--backfill`
writes captions+metadata for the media already on disk **without re-downloading
anything** (posts you never downloaded are left alone):

```bash
socialdl natgeo -p instagram --backfill
```

### Re-running (sync)

Re-running a target is cheap and safe: a `.archive.sqlite` in each account folder
records what's downloaded, so a rerun **only fetches new posts** and never
duplicates. `no_archive` forces a full re-fetch; deleting `downloads` resets it.

## Config file & env vars

Reusable defaults live in `~/.config/socialdl/config.toml` (see
[`config.example.toml`](config.example.toml)). Precedence is
**explicit value > env var > config file > built-in default**:

```toml
cookies = "/home/you/cookies.txt"     # or cookies_from_browser = "firefox"
# out = "/home/you/Pictures/socials"
# captions = true
# metadata = true
```

Env vars: `SOCIALDL_COOKIES`, `SOCIALDL_COOKIES_FROM_BROWSER`, `SOCIALDL_OUT`,
`SOCIALDL_METADATA`, `SOCIALDL_CAPTIONS`, `SOCIALDL_CONFIG`, and for the server
`SOCIALDL_HOST` / `SOCIALDL_PORT`.

## Notes & limitations

- Platforms change and rate-limit constantly. If a fetch fails or returns
  nothing, check credentials first, then update the engine:
  `.venv/bin/pip install -U gallery-dl yt-dlp`.
- The HTTP server has no built-in authentication — keep it on localhost.

## Legal & responsible use

This is a tool for saving media you have a legitimate right to access. By using
it you agree that **you** are solely responsible for how you use it.

- **Respect Terms of Service.** Automated downloading may be restricted by
  Instagram/TikTok/Facebook's terms. You are responsible for complying with the
  terms of any service you access.
- **Respect copyright and privacy.** Content belongs to its creators. Don't
  redistribute, republish, or use downloaded media without the rights to do so,
  and don't use this tool to harvest or target private individuals.
- **Don't hammer the sites.** Use reasonable limits (`--limit`, `--since`) and
  don't run aggressive, high-volume scraping.
- **Account-ban risk is on you.** Authenticating with your cookies can get that
  account rate-limited or banned (see the warning in *Authentication*). Use a
  disposable account; the maintainers are not liable for banned accounts.
- **No affiliation.** This project is not affiliated with, endorsed by, or
  sponsored by Instagram, TikTok, Facebook/Meta, or ByteDance. All trademarks
  belong to their respective owners.

The software is provided "as is", without warranty of any kind (see
[LICENSE](LICENSE)).

## Related projects

socialdl is far from the only tool in this space — it deliberately stands on the
shoulders of mature downloaders rather than reinventing them:

- **[gallery-dl](https://github.com/mikf/gallery-dl)** — the multi-site engine
  socialdl drives under the hood.
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — video downloader (used by
  gallery-dl for some video content).
- **[Instaloader](https://github.com/instaloader/instaloader)** —
  Instagram-specialised downloader (profiles, stories, hashtags).
- **[cobalt](https://github.com/imputnet/cobalt)** — privacy-first, no-account
  media downloader across many platforms.

**What socialdl adds:** a single, small, agent-friendly layer over gallery-dl
that exposes the *same* structured operation through a **CLI, an MCP server, and
an HTTP API** — plus conveniences like like-ranking (`--top-liked`), sidecar
backfill, and JSON output. If you just want a one-off download, the tools above
may serve you directly.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Run the tests
with `pytest` (they're offline). Please add tests for logic you change.

## License

[MIT](LICENSE) © socialdl contributors.
