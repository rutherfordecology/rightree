"""Read a large remote zip over HTTP range requests, without downloading all of it.

    python scripts/remote_zip.py list <url>
    python scripts/remote_zip.py get <url> <outdir> <pattern> [<pattern> ...]

`get` extracts members whose path contains any of the patterns.
"""
import io
import sys
import zipfile
from pathlib import Path

import requests


class HttpFile(io.RawIOBase):
    def __init__(self, url):
        self.url, self.pos = url, 0
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "rightree-prototype"
        r = self.s.head(url, allow_redirects=True, timeout=60)
        self.url = r.url
        self.size = int(r.headers["Content-Length"])

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.pos + n, self.size) - 1
        for attempt in range(5):
            try:
                r = self.s.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=300)
                r.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 4:
                    raise
        self.pos += len(r.content)
        return r.content

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def main():
    cmd, url = sys.argv[1], sys.argv[2]
    # Large buffer so zipfile's small reads become few big range requests.
    z = zipfile.ZipFile(io.BufferedReader(HttpFile(url), buffer_size=8 << 20))
    if cmd == "list":
        for i in z.infolist():
            print(f"{i.file_size / 1e6:10.1f} MB  {i.filename}")
    elif cmd == "get":
        out, pats = Path(sys.argv[3]), sys.argv[4:]
        for i in z.infolist():
            if any(p in i.filename for p in pats) and not i.is_dir():
                print(f"extracting {i.filename} ({i.file_size / 1e6:.1f} MB)", flush=True)
                z.extract(i, out)


if __name__ == "__main__":
    main()
