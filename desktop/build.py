#!/usr/bin/env python3
"""Build the arm64 review installer. Run with the studio virtualenv Python."""

from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "macos"
DIST = ROOT / "dist"
VERSION = json.loads((ROOT / "desktop/version.json").read_text())


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True, **kwargs)


def main():
    if sys.platform != "darwin" or platform.machine() != "arm64":
        raise SystemExit("此构建脚本仅支持 Apple Silicon Mac。")
    guard = Path.home() / ".agents/skills/vibe-coding/scripts/secret_guard.py"
    if guard.exists():
        run([sys.executable, guard, ROOT, "--include-build-dirs"])
    BUILD.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(exist_ok=True)
    app = BUILD / "作图工坊.app"
    if app.exists():
        shutil.rmtree(app)
    contents = app / "Contents"
    resources = contents / "Resources"
    binary = contents / "MacOS"
    resources.mkdir(parents=True); binary.mkdir()
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(BUILD / "pyinstaller-cache"))
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--name", "studio-service",
         "--target-architecture", "arm64", "--distpath", BUILD / "frozen", "--workpath", BUILD / "freeze-work", "--specpath", BUILD,
         "--paths", ROOT / "studio", "--add-data", f"{ROOT / 'studio/static'}:static",
         "--runtime-hook", ROOT / "desktop/certificates.py",
         "--hidden-import", "keyring.backends.macOS", "--copy-metadata", "keyring", "--copy-metadata", "google-genai",
         "--exclude-module", "tkinter", "--exclude-module", "unittest", "--exclude-module", "pip",
         ROOT / "desktop/backend.py"], env=env)
    # These are third-party public trust anchors, not private PEM credentials.
    # Validate their certificate-only contents, then use an explicit .crt name.
    # Keep all original bytes and normal TLS verification; never disable TLS.
    from cryptography.x509 import load_pem_x509_certificates
    frozen = BUILD / "frozen/studio-service"
    for relative in ["certifi/cacert.pem", "grpc/_cython/_credentials/roots.pem"]:
        source = frozen / "_internal" / relative
        data = source.read_bytes()
        if b"PRIVATE KEY" in data or not load_pem_x509_certificates(data):
            raise SystemExit("依赖证书包不是纯公共证书，停止打包。")
        source.rename(source.with_name("public-roots.crt"))
    shutil.copytree(BUILD / "frozen/studio-service", resources / "backend", symlinks=True)
    shutil.copy2(ROOT / "desktop/bridge.js", resources)
    run(["/usr/bin/swiftc", "-O", "-target", "arm64-apple-macos15.0", "-module-cache-path", BUILD / "swift-cache",
         "-framework", "AppKit", "-framework", "WebKit", ROOT / "desktop/Main.swift", "-o", binary / "HeroGameStudio"])
    run([sys.executable, ROOT / "desktop/make_icon.py", resources / "Studio.icns"])
    info = {"CFBundleIdentifier": VERSION["bundle_id"], "CFBundleExecutable":"HeroGameStudio", "CFBundleName":"作图工坊",
            "CFBundleDisplayName":"作图工坊", "CFBundlePackageType":"APPL", "CFBundleShortVersionString":VERSION["version"],
            "CFBundleVersion":VERSION["build"], "CFBundleIconFile":"Studio.icns", "LSMinimumSystemVersion":VERSION["minimum_macos"],
            "NSHighResolutionCapable":True, "NSPrincipalClass":"NSApplication", "CFBundleDevelopmentRegion":"zh_CN",
            "NSAppTransportSecurity":{"NSAllowsLocalNetworking":True}}
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    # Only public source identities and dependency versions. Never collect runtime data.
    source_files = sorted([*ROOT.glob("studio/*.py"), *ROOT.glob("studio/static/*"), *ROOT.glob("desktop/*")])
    hashes = {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
              for path in source_files if path.is_file() and not path.name.startswith("test_")}
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    manifest = {**VERSION, "architecture":"arm64", "built_utc":datetime.now(timezone.utc).isoformat(), "source_commit":commit,
                "working_tree_modified":dirty, "source_sha256":hashes, "python":platform.python_version(),
                "dependencies":{dist.metadata["Name"]:dist.version for dist in metadata.distributions()}}
    (resources / "build-info.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    notices = resources / "ThirdPartyNotices"; notices.mkdir()
    for dist in metadata.distributions():
        for file in dist.files or []:
            if any(part.lower().startswith(("license", "copying", "notice")) for part in file.parts):
                source = dist.locate_file(file)
                if source.is_file():
                    target = notices / dist.metadata["Name"] / file.name
                    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    run(["/usr/bin/codesign", "--force", "--sign", "-", app])
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", app])
    if guard.exists():
        run([sys.executable, guard, app, "--include-build-dirs"])
    stage = BUILD / "dmg-stage"
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir()
    shutil.copytree(app, stage / app.name, symlinks=True)
    (stage / "Applications").symlink_to("/Applications")
    shutil.copy2(ROOT / "desktop/安装说明.txt", stage)
    image = DIST / f"HeroGameStudio-{VERSION['version']}-macOS-arm64.dmg"
    if image.exists(): raise SystemExit(f"安装包已存在，先归档旧测试包或更新版本：{image}")
    run(["/usr/bin/hdiutil", "create", "-volname", f"作图工坊 {VERSION['version']}", "-srcfolder", stage,
         "-fs", "HFS+", "-format", "UDZO", image])
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    image.with_suffix(".dmg.sha256").write_text(f"{digest}  {image.name}\n")
    print(f"安装包：{image}\nSHA-256：{digest}\n本地测试版；未做 Developer ID 签名或 Apple 公证。")


if __name__ == "__main__":
    main()
