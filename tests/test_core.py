"""Offline unit tests for socialdl's pure logic (no network)."""
from pathlib import Path

import pytest

from socialdl import DownloadOptions, DownloadResult, InstaError, detect_platform
from socialdl import core


# --- platform detection -----------------------------------------------------
@pytest.mark.parametrize("url,expected", [
    ("https://www.instagram.com/natgeo/", "instagram"),
    ("https://instagram.com/p/ABC/", "instagram"),
    ("https://www.tiktok.com/@nasa", "tiktok"),
    ("https://fb.watch/xyz/", "facebook"),
    ("https://www.facebook.com/NASA", "facebook"),
    ("natgeo", None),
    ("@nasa", None),
    ("https://example.com/foo", None),
])
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


# --- URL building -----------------------------------------------------------
@pytest.mark.parametrize("handle,platform,expected", [
    ("natgeo", "instagram", "https://www.instagram.com/natgeo/"),
    ("@nasa", "tiktok", "https://www.tiktok.com/@nasa"),
    ("NASA", "facebook", "https://www.facebook.com/NASA"),
])
def test_build_url(handle, platform, expected):
    assert core.build_url(handle, platform) == expected


def test_build_url_bad_platform():
    with pytest.raises(InstaError):
        core.build_url("x", "myspace")


# --- account label ----------------------------------------------------------
@pytest.mark.parametrize("target,platform,expected", [
    ("natgeo", "instagram", "natgeo"),
    ("@nasa", "tiktok", "nasa"),
    ("https://www.instagram.com/natgeo/", "instagram", "natgeo"),
    ("https://www.tiktok.com/@nasa", "tiktok", "nasa"),
])
def test_account_label(target, platform, expected):
    assert core.account_label(target, platform) == expected


def test_account_label_sanitizes():
    assert "/" not in core.account_label("a/b c", "instagram")


# --- date validation --------------------------------------------------------
def test_valid_date_ok():
    assert core._valid_date("2025-06-01") == (2025, 6, 1)


@pytest.mark.parametrize("bad", ["2025-13-01", "2025-06-40", "20250601", "June 1"])
def test_valid_date_bad(bad):
    with pytest.raises(InstaError):
        core._valid_date(bad)


# --- filter building --------------------------------------------------------
def test_filter_none():
    assert core._build_filter(DownloadOptions(target="x")) is None


def test_filter_since_has_abort():
    f = core._build_filter(DownloadOptions(target="x", since="2025-06-01"))
    assert "date >= datetime(2025, 6, 1)" in f and "abort()" in f


def test_filter_until():
    f = core._build_filter(DownloadOptions(target="x", until="2025-06-30"))
    assert "date <= datetime(2025, 6, 30, 23, 59, 59)" in f


def test_filter_videos_only_excludes_images():
    f = core._build_filter(DownloadOptions(target="x", videos_only=True))
    assert "extension not in" in f and "'jpg'" in f


def test_filter_combined():
    f = core._build_filter(DownloadOptions(
        target="x", since="2025-01-01", until="2025-12-31", videos_only=True))
    assert " and " in f


# --- extension classification ----------------------------------------------
@pytest.mark.parametrize("ext,kind", [
    (".jpg", "image"), (".PNG", "image"), (".mp4", "video"),
    (".json", None), (".txt", None), (".bin", "other"),
])
def test_classify(ext, kind):
    assert core._classify(ext) == kind


# --- output parsing ---------------------------------------------------------
def test_parse_output_real_mode():
    out = "/data/a.jpg\n# /data/b.jpg\n/data/c.mp4\n/data/a.jpg.json\n"
    files, skipped = core._parse_output(out, Path("/data"), simulate=False)
    kinds = sorted(f.type for f in files)
    assert kinds == ["image", "video"]          # sidecar .json excluded
    assert skipped == 1                          # the "# " line


def test_parse_output_simulate_mode():
    # In simulate, "# name" means "would download", not skipped.
    out = "# a.jpg\n# b.mp4\n"
    files, skipped = core._parse_output(out, Path("/data"), simulate=True)
    assert skipped == 0
    assert sorted(f.type for f in files) == ["image", "video"]


# --- scan URL / platform gating --------------------------------------------
def test_posts_scan_url_instagram():
    assert core._posts_scan_url(
        "instagram", "https://www.instagram.com/natgeo/"
    ) == "https://www.instagram.com/natgeo/posts/"


@pytest.mark.parametrize("platform", ["tiktok", "facebook"])
def test_posts_scan_url_other_platforms_raise(platform):
    with pytest.raises(InstaError):
        core._posts_scan_url(platform, "https://example.com/x")


# --- result serialization ---------------------------------------------------
def test_result_to_dict_is_json_serializable():
    import json
    r = DownloadResult(ok=True, target="natgeo", platform="instagram")
    json.dumps(r.to_dict())      # must not raise
    assert r.to_dict()["ok"] is True
