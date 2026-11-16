"""Use validated, byte-for-byte public CA bundles shipped as .crt resources."""
import os
from pathlib import Path
import sys

import certifi
import certifi.core

root = Path(sys._MEIPASS)
bundle = root / "certifi/public-roots.crt"
certifi.where = certifi.core.where = lambda: str(bundle)
certifi.contents = certifi.core.contents = lambda: bundle.read_text(encoding="ascii")
os.environ["GRPC_DEFAULT_SSL_ROOTS_FILE_PATH"] = str(root / "grpc/_cython/_credentials/public-roots.crt")
