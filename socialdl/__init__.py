"""socialdl — save images/videos from public social media accounts.

Public API for programmatic (Python) use:

    from socialdl import download, probe, DownloadOptions
    result = download(DownloadOptions(target="natgeo", platform="instagram",
                                      images_only=True, cookies="cookies.txt"))
    print(result.to_dict())
"""
from .core import (
    DownloadOptions,
    DownloadResult,
    MediaFile,
    InstaError,
    SUPPORTED_PLATFORMS,
    download,
    probe,
    list_platforms,
    detect_platform,
)

__version__ = "0.3.0"

__all__ = [
    "DownloadOptions",
    "DownloadResult",
    "MediaFile",
    "InstaError",
    "SUPPORTED_PLATFORMS",
    "download",
    "probe",
    "list_platforms",
    "detect_platform",
    "__version__",
]
