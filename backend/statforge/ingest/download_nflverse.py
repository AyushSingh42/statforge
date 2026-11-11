"""Download a versioned local snapshot of nflverse player-season statistics."""

import argparse
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from statforge.config import SUPPORTED_SEASONS
from statforge.ingest.sources.nflverse import (
    FILE_NAME_TEMPLATE,
    MANIFEST_NAME,
    RELEASE_URL,
    SNAPSHOT_DIR,
)
from statforge.ingest.verify import parse_seasons

DOWNLOAD_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_reg_{season}.csv"
)
CHUNK_SIZE = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> str:
    """Download atomically and return the SHA-256 of the completed file."""
    digest = hashlib.sha256()
    with (
        urlopen(Request(url, headers={"User-Agent": "StatForge/0.1"}), timeout=60) as response,
        tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{destination.name}.", dir=destination.parent, delete=False
        ) as temporary,
    ):
        temporary_path = Path(temporary.name)
        try:
            for chunk in iter(lambda: response.read(CHUNK_SIZE), b""):
                temporary.write(chunk)
                digest.update(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path.replace(destination)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
    return digest.hexdigest()


def download_snapshot(
    seasons: Iterable[int], snapshot_dir: Path = SNAPSHOT_DIR, *, force: bool = False
) -> dict[str, object]:
    """Download the requested seasons and write an auditable manifest."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, str]] = {}
    for season in dict.fromkeys(seasons):
        filename = FILE_NAME_TEMPLATE.format(season=season)
        path = snapshot_dir / filename
        url = DOWNLOAD_URL.format(season=season)
        checksum = _download(url, path) if force or not path.exists() else _sha256(path)
        files[str(season)] = {"file": filename, "url": url, "sha256": checksum}

    manifest: dict[str, object] = {
        "schema_version": 1,
        "source": "nflverse player_stats regular-season release",
        "release_url": RELEASE_URL,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "files": files,
    }
    (snapshot_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        type=parse_seasons,
        default=SUPPORTED_SEASONS,
        help="e.g. 2016-2025 (default: supported range)",
    )
    parser.add_argument("--force", action="store_true", help="re-download existing snapshot files")
    args = parser.parse_args(argv)
    manifest = download_snapshot(args.seasons, force=args.force)
    print(f"Downloaded nflverse snapshot for {', '.join(manifest['files'])}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
