"""Download the pinned sources of the corpus test into the cache directory.

The cache is $FORMAT_CONVERTERS_CACHE (default ~/.cache/format-converters). Nothing here is stored in
the repository: the datasets have their own licences (see README.md). The two Zenodo zips are read
by HTTP range requests, so only the needed members are transferred.
"""
from __future__ import annotations

import fnmatch
import hashlib
import io
import json
import os
import shutil
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
SOURCES = json.loads((HERE / "sources.json").read_text())


def cache_dir() -> Path:
    return Path(os.environ.get("FORMAT_CONVERTERS_CACHE", "~/.cache/format-converters")).expanduser()


def names(source: str) -> list[str]:
    return [l for l in (HERE / SOURCES[source]["files"]).read_text().splitlines() if l.strip()]


def wir_fid(index: int) -> str:
    """Cache file name of the index-th When in Rome path (0-based)."""
    return f"f{index + 1:04d}.txt"


def _open(url: str, headers: dict | None = None, retries: int = 4):
    last = None
    for attempt in range(retries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=60)
        except Exception as exc:  # noqa: BLE001 network errors are retried
            last = exc
            time.sleep(2 ** attempt)
    raise last


def _have(path: Path) -> bool:
    """A cached file counts only if it has content: an interrupted or failed download can leave an empty one."""
    return path.exists() and path.stat().st_size > 0


def md5_of(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _write(path: Path, data: bytes) -> None:
    if not data:
        raise OSError(f"empty download for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


class HttpRangeFile(io.RawIOBase):
    """A remote file as a seekable stream, read by HTTP range requests."""

    def __init__(self, url: str):
        self.url = url
        with _open(url, {"Range": "bytes=0-0"}) as r:
            self.size = int(r.headers["Content-Range"].rpartition("/")[2])
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (offset, self.pos + offset, self.size + offset)[whence]
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        with _open(self.url, {"Range": f"bytes={self.pos}-{end}"}) as r:
            data = r.read()
        self.pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def fetch_zip_members(source: str, cache: Path, only: int | None = None) -> int:
    """Extract the members of a Zenodo zip that the corpus reads, as cache/<source>/<kind>/<name>.csv."""
    spec = SOURCES[source]
    zf = zipfile.ZipFile(io.BufferedReader(HttpRangeFile(spec["url"]), buffer_size=1 << 16))
    n = 0
    for kind, pattern in spec["members"].items():
        for info in zf.infolist():
            if info.is_dir() or not fnmatch.fnmatch(info.filename, pattern):
                continue
            target = cache / source / kind / info.filename.rsplit("/", 1)[1]
            if not _have(target):
                _write(target, zf.read(info))
            n += 1
            if only and n >= only:
                return n
    return n


def fetch_dcml(cache: Path, only: int | None = None) -> int:
    n = 0
    for name in names("dcml")[:only]:
        target = cache / "dcml" / name
        if not _have(target):
            with _open(SOURCES["dcml"]["url"] + urllib.parse.quote(name)) as r:
                _write(target, r.read())
        n += 1
    return n


def fetch_wir(cache: Path, only: int | None = None) -> int:
    n = 0
    for i, path in enumerate(names("wir")[:only]):
        target = cache / "wir" / wir_fid(i)
        if not _have(target):
            with _open(SOURCES["wir"]["url"] + urllib.parse.quote(path)) as r:
                _write(target, r.read())
        n += 1
    return n


def fetch_all(cache: Path | None = None) -> None:
    """Download whatever the cache lacks (everything, on a fresh cache)."""
    cache = cache or cache_dir()
    fetch_zip_members("bpsd", cache)
    fetch_zip_members("swd", cache)
    fetch_dcml(cache)
    fetch_wir(cache)


def seed_wir_parse(src: Path, cache: Path | None = None) -> None:
    """Split an earlier parse of the When in Rome files (data/wir_parsed.json) into the per-file cache."""
    import music21

    cache = cache or cache_dir()
    parsed = src / "wir_parsed.json"
    if not parsed.exists():
        return
    for fid, v in json.loads(parsed.read_text()).items():
        i = names("wir").index(v["path"])
        target = cache / "wir_parsed" / (wir_fid(i)[:-4] + ".json")
        text = cache / "wir" / wir_fid(i)
        if not target.exists() and v["status"] == "ok" and _have(text):
            _write(target, json.dumps({"music21": music21.__version__, "source_md5": md5_of(text),
                                       "chords": v["chords"]}).encode())


def seed(src: Path, cache: Path | None = None) -> None:
    """Copy files of an earlier download into the cache (never modifying the original)."""
    cache = cache or cache_dir()
    layout = {
        "bpsd/Beethoven_Piano_Sonata_Dataset_v2/2_Annotations/ann_score_chord": "bpsd/ann_score_chord",
        "swd/02_Annotations/ann_score_chord": "swd/ann_score_chord",
        "swd/02_Annotations/ann_audio_chord": "swd/ann_audio_chord",
    }
    for old, new in layout.items():
        for f in sorted((src / old).glob("*.csv")):
            if _have(f) and not _have(cache / new / f.name):
                (cache / new).mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, cache / new / f.name)
    for name in names("dcml"):
        if _have(src / "dcml" / name) and not _have(cache / "dcml" / name):
            (cache / "dcml").mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / "dcml" / name, cache / "dcml" / name)
    index = src / "wir" / "index.tsv"
    if index.exists():
        for line in index.read_text().splitlines():
            fid, path = line.split("\t")
            i = names("wir").index(path)
            if _have(src / "wir" / fid) and not _have(cache / "wir" / wir_fid(i)):
                (cache / "wir").mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / "wir" / fid, cache / "wir" / wir_fid(i))
    seed_wir_parse(src, cache)
