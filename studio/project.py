"""Per-product project folders. Studio tool stays in studio/; assets live in the active project."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

MARKER = "herogame.json"
KIND_HEROGAME = "herogame"
KIND_DESKPET = "deskpet"
KIND = KIND_HEROGAME  # backward-compat alias
VALID_KINDS = (KIND_HEROGAME, KIND_DESKPET)

TOOL_ROOT = Path(__file__).resolve().parent
DEFAULT_ROOT = TOOL_ROOT.parent
REGISTRY_PATH = TOOL_ROOT / "projects.json"

LINE_LABELS = {
    KIND_HEROGAME: "对战游戏资产",
    KIND_DESKPET: "桌宠/立绘资产",
}


class ProjectPaths:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def set_root(self, root: Path) -> None:
        self.root = root.resolve()

    @property
    def assets(self) -> Path:
        return self.root / "assets"

    @property
    def studio(self) -> Path:
        return self.assets / "studio"

    @property
    def drafts(self) -> Path:
        return self.studio / "drafts"

    @property
    def game(self) -> Path:
        return self.assets / "game"

    @property
    def style_dir(self) -> Path:
        return self.studio / "_style"

    @property
    def stages_dir(self) -> Path:
        return self.studio / "stages"

    @property
    def marker_path(self) -> Path:
        return self.root / MARKER

    def ensure(self, kind: str | None = None) -> None:
        k = normalize_kind(kind) if kind else detect_kind(self.root)
        common = (
            self.studio,
            self.drafts / "style",
            self.style_dir,
        )
        if k == KIND_DESKPET:
            extra = (
                self.drafts / "portraits",
                self.studio / "portraits",
                self.studio / "exports" / "portraits",
            )
        else:
            extra = (
                self.drafts / "heroes",
                self.drafts / "stages",
                self.stages_dir,
                self.game / "heroes",
                self.game / "stages",
                self.game / "style",
            )
        for path in (*common, *extra):
            path.mkdir(parents=True, exist_ok=True)


paths = ProjectPaths(DEFAULT_ROOT)


def normalize_kind(kind: str | None) -> str:
    k = str(kind or "").strip().lower()
    if k in ("portrait", "portraits", "desk-pet", "desk_pet"):
        return KIND_DESKPET
    if k in ("game", "hero", "heroes", "fight"):
        return KIND_HEROGAME
    if k in VALID_KINDS:
        return k
    return KIND_HEROGAME


def detect_kind(root: Path) -> str:
    meta = read_marker(root)
    if meta.get("kind"):
        return normalize_kind(str(meta["kind"]))
    # Legacy unmarked projects are fighting-game assets
    return KIND_HEROGAME


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_folder(folder: str, *, must_exist: bool = True) -> Path:
    raw = (folder or "").strip()
    if not raw:
        raise ValueError("请选择一个文件夹。")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        root = (Path.home() / root).resolve()
    else:
        root = root.resolve()
    if root.exists() and not root.is_dir():
        raise ValueError(f"路径已存在但不是文件夹：{root}")
    if must_exist and not root.exists():
        raise FileNotFoundError(f"文件夹不存在：{root}")
    return root


def _forget(root: Path) -> None:
    root = root.resolve()
    data = _registry()
    data["projects"] = [
        p
        for p in data.get("projects") or []
        if Path(str(p.get("root") or "")).expanduser().resolve() != root
    ]
    active_map = data.get("active_by_kind") or {}
    for k in list(active_map.keys()):
        if Path(str(active_map.get(k) or "")).expanduser().resolve() == root:
            active_map[k] = ""
    data["active_by_kind"] = active_map
    if Path(str(data.get("active") or "")).expanduser().resolve() == root:
        data["active"] = ""
    _save_registry(data)


def _dir_is_empty(root: Path) -> bool:
    if not root.exists():
        return True
    if not root.is_dir():
        return False
    return not any(item.name not in {".DS_Store", "Thumbs.db"} for item in root.iterdir())


def read_marker(root: Path) -> dict:
    return _read_json(root / MARKER)


def write_marker(root: Path, name: str, *, kind: str | None = None, extra: dict | None = None) -> dict:
    prev = read_marker(root)
    k = normalize_kind(kind or prev.get("kind") or KIND_HEROGAME)
    data = {
        "kind": k,
        "name": name.strip() or prev.get("name") or root.name,
        "created": prev.get("created") or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "version": 1,
        **(extra or {}),
    }
    data["kind"] = k
    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _write_json(root / MARKER, data)
    return data


def looks_like_project(root: Path) -> bool:
    if not root.is_dir():
        return False
    if (root / MARKER).exists():
        return True
    if (root / "assets" / "game").is_dir() or (root / "assets" / "studio").is_dir():
        return True
    return False


def _registry() -> dict:
    data = _read_json(REGISTRY_PATH)
    projects = data.get("projects") or []
    if not isinstance(projects, list):
        projects = []
    active_map = data.get("active_by_kind")
    if not isinstance(active_map, dict):
        active_map = {}
    legacy_active = str(data.get("active") or "").strip()
    if legacy_active and not active_map.get(KIND_HEROGAME):
        active_map[KIND_HEROGAME] = legacy_active
    line = str(data.get("line") or "").strip().lower()
    if line and line not in VALID_KINDS:
        line = normalize_kind(line) if line else ""
        if line not in VALID_KINDS:
            line = ""
    # Backfill kinds on registry rows
    fixed = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        raw = str(row.get("root") or "").strip()
        if raw:
            root = Path(raw).expanduser().resolve()
            if not row.get("kind") and root.is_dir():
                row["kind"] = detect_kind(root)
            elif row.get("kind"):
                row["kind"] = normalize_kind(str(row["kind"]))
            else:
                row["kind"] = KIND_HEROGAME
        fixed.append(row)
    return {
        "line": line if line in VALID_KINDS else "",
        "active": legacy_active,
        "active_by_kind": {k: str(active_map.get(k) or "") for k in VALID_KINDS},
        "projects": fixed,
    }


def _save_registry(data: dict) -> None:
    line = str(data.get("line") or "")
    if line not in VALID_KINDS:
        line = ""
    active_map = data.get("active_by_kind") if isinstance(data.get("active_by_kind"), dict) else {}
    normalized = {
        "line": line,
        "active": str(active_map.get(line) or data.get("active") or ""),
        "active_by_kind": {k: str(active_map.get(k) or "") for k in VALID_KINDS},
        "projects": data.get("projects") or [],
    }
    _write_json(REGISTRY_PATH, normalized)


def remember(root: Path, name: str = "", *, kind: str | None = None) -> dict:
    root = root.resolve()
    k = normalize_kind(kind or detect_kind(root))
    meta = read_marker(root)
    display = name.strip() or meta.get("name") or root.name
    if not meta:
        meta = write_marker(root, display, kind=k)
    else:
        # Keep / repair kind on open
        if normalize_kind(meta.get("kind")) != k or (name.strip() and meta.get("name") != display):
            meta = write_marker(root, display, kind=k)
        elif name.strip() and meta.get("name") != display:
            meta = write_marker(root, display, kind=k)
    data = _registry()
    items = [
        p
        for p in data["projects"]
        if Path(str(p.get("root") or "")).expanduser().resolve() != root
    ]
    items.insert(
        0,
        {
            "root": str(root),
            "name": display,
            "kind": k,
            "openedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
    )
    data["projects"] = items[:40]
    data["line"] = k
    active_map = data.get("active_by_kind") or {}
    active_map[k] = str(root)
    data["active_by_kind"] = active_map
    data["active"] = str(root)
    _save_registry(data)
    return meta


def activate(root: Path, name: str = "", *, kind: str | None = None) -> dict:
    root = root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"文件夹不存在：{root}")
    if not root.is_dir():
        raise NotADirectoryError(f"不是文件夹：{root}")
    k = normalize_kind(kind or detect_kind(root))
    paths.set_root(root)
    paths.ensure(k)
    remember(root, name, kind=k)
    return current_payload()


def current_payload() -> dict:
    meta = read_marker(paths.root)
    if not meta:
        meta = write_marker(paths.root, paths.root.name, kind=KIND_HEROGAME)
    k = normalize_kind(meta.get("kind"))
    return {
        "root": str(paths.root),
        "name": meta.get("name") or paths.root.name,
        "kind": k,
        "line": k,
        "line_label": LINE_LABELS.get(k, k),
        "created": meta.get("created") or "",
        "game": str(paths.game),
        "studio": str(paths.studio),
    }


def current_line() -> str:
    return str(_registry().get("line") or "")


def set_line(kind: str) -> dict:
    """Select product line. Activates last project of that kind if any."""
    k = normalize_kind(kind)
    if k not in VALID_KINDS:
        raise ValueError("未知产品线。")
    data = _registry()
    data["line"] = k
    _save_registry(data)
    active_map = data.get("active_by_kind") or {}
    root_s = str(active_map.get(k) or "").strip()
    if root_s:
        root = Path(root_s).expanduser()
        if root.is_dir():
            try:
                if detect_kind(root) == k or not read_marker(root):
                    return {
                        "ok": True,
                        "line": k,
                        "line_label": LINE_LABELS[k],
                        "has_project": True,
                        **activate(root, kind=k),
                        **list_projects(kind=k),
                    }
            except Exception:
                pass
    # Soft-point paths at tool parent so file mounts still resolve, but flag no project
    if k == KIND_HEROGAME and DEFAULT_ROOT.is_dir():
        # Don't auto-claim DEFAULT_ROOT as deskpet
        paths.set_root(DEFAULT_ROOT)
    return {
        "ok": True,
        "line": k,
        "line_label": LINE_LABELS[k],
        "has_project": False,
        "root": "",
        "name": "",
        "kind": k,
        **list_projects(kind=k),
    }


def clear_line() -> dict:
    data = _registry()
    data["line"] = ""
    _save_registry(data)
    return {"ok": True, "line": "", "has_project": False, "projects": []}


def list_projects(kind: str | None = None) -> dict:
    data = _registry()
    want = normalize_kind(kind) if kind else (data.get("line") or "")
    if want and want not in VALID_KINDS:
        want = ""
    out = []
    seen: set[str] = set()
    for item in data.get("projects") or []:
        raw = str(item.get("root") or "").strip()
        if not raw:
            continue
        root = Path(raw).expanduser().resolve()
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        meta = read_marker(root) if root.is_dir() else {}
        row_kind = normalize_kind(meta.get("kind") or item.get("kind") or KIND_HEROGAME)
        if want and row_kind != want:
            continue
        out.append(
            {
                "root": key,
                "name": meta.get("name") or item.get("name") or root.name,
                "kind": row_kind,
                "exists": root.is_dir(),
                "active": want == row_kind and key == str(paths.root) and detect_kind(paths.root) == row_kind,
            }
        )
    line = want or str(data.get("line") or "")
    active = None
    if line in VALID_KINDS and detect_kind(paths.root) == line and (
        not want or want == line
    ):
        # Only expose active if it matches the filtered line
        if any(p["root"] == str(paths.root) for p in out) or (not want and looks_like_project(paths.root)):
            active = current_payload()
            if want and active.get("kind") != want:
                active = None
    if active is None and line in VALID_KINDS:
        active = {
            "root": "",
            "name": "",
            "kind": line,
            "line": line,
            "line_label": LINE_LABELS[line],
            "created": "",
            "game": "",
            "studio": "",
        }
    elif active is None:
        active = {
            "root": "",
            "name": "",
            "kind": "",
            "line": "",
            "line_label": "",
            "created": "",
            "game": "",
            "studio": "",
        }
    return {
        "active": active,
        "projects": out,
        "line": line,
        "line_label": LINE_LABELS.get(line, ""),
        "has_project": bool(active.get("root")),
    }


def pick_directory(prompt: str = "选择工程文件夹", default: str = "") -> str:
    """Open a native folder dialog and return the chosen path (empty if cancelled)."""
    text = (prompt or "选择工程文件夹").replace("\\", "\\\\").replace('"', '\\"')
    start = (default or "").strip().rstrip("/")
    if sys.platform == "darwin":
        loc = ""
        if start and Path(start).is_dir():
            loc_path = start.replace("\\", "\\\\").replace('"', '\\"')
            loc = f'set loc to POSIX file "{loc_path}"\n'
            choose = f'choose folder with prompt "{text}" default location loc'
        else:
            choose = f'choose folder with prompt "{text}"'
        script = (
            "try\n"
            f"{loc}"
            f"set p to POSIX path of ({choose})\n"
            "on error\n"
            'return ""\n'
            "end try\n"
            "return p"
        )
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=600,
        )
        path = (result.stdout or "").strip()
    else:
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory(title=text, initialdir=start or None) or ""
            root.destroy()
        except Exception:
            path = ""
    return path.rstrip("/")


def create_project(name: str, folder: str, *, kind: str = KIND_HEROGAME) -> dict:
    k = normalize_kind(kind)
    root = _resolve_folder(folder, must_exist=False)
    display = (name or "").strip() or root.name
    if root == paths.root.resolve() and looks_like_project(root):
        raise ValueError("这就是当前正在编辑的工程。请另选一个空文件夹。")
    if looks_like_project(root):
        meta = read_marker(root)
        other = LINE_LABELS.get(detect_kind(root), "工程")
        raise ValueError(f"「{meta.get('name') or root.name}」已经是{other}，请直接打开。")
    if root.exists() and not _dir_is_empty(root):
        raise ValueError(f"文件夹不是空的：{root}。新建请在访达里建一个空文件夹，文件夹名就是项目名。")
    root.mkdir(parents=True, exist_ok=True)
    write_marker(root, display, kind=k)
    return activate(root, display, kind=k)


def open_project(folder: str, name: str = "", *, kind: str | None = None) -> dict:
    root = _resolve_folder(folder, must_exist=True)
    k = normalize_kind(kind or detect_kind(root))
    display = (name or "").strip() or read_marker(root).get("name") or root.name
    write_marker(root, display, kind=k)
    return activate(root, display, kind=k)


def use_folder(folder: str, name: str = "", *, kind: str | None = None) -> dict:
    """Open an existing project, or init an empty folder for the current product line."""
    root = _resolve_folder(folder, must_exist=True)
    alias = (name or "").strip()
    line = normalize_kind(kind or current_line() or KIND_HEROGAME)
    if looks_like_project(root):
        existing = detect_kind(root)
        if existing != line:
            raise ValueError(
                f"这是「{LINE_LABELS.get(existing, existing)}」工程，"
                f"当前在「{LINE_LABELS.get(line, line)}」产品线。请换文件夹，或先切产品线。"
            )
        activate(root, kind=line)
        payload = current_payload()
        payload["created"] = False
        return payload
    if not _dir_is_empty(root):
        raise ValueError(
            "这个文件夹不是空的，也还不是本产品线工程。请选已有工程，或先建一个空文件夹。"
        )
    display = alias or root.name
    write_marker(root, display, kind=line)
    activate(root, display, kind=line)
    payload = current_payload()
    payload["created"] = True
    return payload


def rename_project(name: str) -> dict:
    alias = (name or "").strip()
    if not alias:
        raise ValueError("请填写别名。不填的话显示名就是文件夹名。")
    k = detect_kind(paths.root)
    write_marker(paths.root, alias, kind=k)
    remember(paths.root, alias, kind=k)
    return current_payload()


def wipe_project(folder: str) -> dict:
    """Delete assets under the folder, keep the folder itself."""
    raw = (folder or "").strip()
    if not raw:
        raise ValueError("请选择要清空的工程。")
    root = Path(raw).expanduser().resolve()
    if root == TOOL_ROOT:
        raise ValueError("不能清空作图工坊程序自己的目录。")
    if root == paths.root.resolve() and current_line() and detect_kind(root) == current_line():
        raise ValueError("不能删除当前正在使用的工程。请先切换到其他项目再清空。")
    if not root.exists():
        _forget(root)
        return {"wiped": True, "stayed": False, **list_projects(kind=current_line() or None)}
    if not root.is_dir():
        raise NotADirectoryError(f"不是文件夹：{root}")
    for rel in ("assets/game", "assets/studio"):
        target = root / rel
        if target.exists():
            shutil.rmtree(target)
    marker = root / MARKER
    if marker.exists():
        marker.unlink()
    assets = root / "assets"
    if assets.is_dir() and _dir_is_empty(assets):
        assets.rmdir()
    _forget(root)
    return {"wiped": True, "stayed": False, **list_projects(kind=current_line() or None)}


def boot() -> dict:
    """Restore last product-line project if any; otherwise leave paths on DEFAULT_ROOT."""
    data = _registry()
    line = str(data.get("line") or "").strip()
    active_map = data.get("active_by_kind") or {}
    if line in VALID_KINDS:
        root_s = str(active_map.get(line) or "").strip()
        if root_s:
            root = Path(root_s).expanduser()
            if root.is_dir():
                try:
                    return activate(root, kind=line)
                except Exception:
                    pass
    # Fallback: legacy single active as herogame
    legacy = str(data.get("active") or active_map.get(KIND_HEROGAME) or "").strip()
    if legacy:
        root = Path(legacy).expanduser()
        if root.is_dir():
            try:
                # Don't set line automatically — UI gate decides; still mount paths
                paths.set_root(root)
                paths.ensure(detect_kind(root))
                return current_payload()
            except Exception:
                pass
    paths.set_root(DEFAULT_ROOT)
    paths.ensure(KIND_HEROGAME)
    return {
        "root": str(paths.root),
        "name": read_marker(paths.root).get("name") or paths.root.name,
        "kind": detect_kind(paths.root) if looks_like_project(paths.root) else "",
        "line": "",
        "line_label": "",
        "created": "",
        "game": str(paths.game),
        "studio": str(paths.studio),
    }


def reveal_in_file_manager(target: str | Path) -> dict:
    """Open a folder (or parent of a file) in Finder / Explorer / file manager.

    Only paths under the current project root are allowed.
    """
    import platform
    import subprocess

    raw = Path(target).expanduser()
    try:
        path = raw.resolve()
    except OSError as exc:
        raise ValueError(f"路径无效：{exc}") from exc
    root = paths.root.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("只能打开当前工程内的路径。") from exc
    folder = path if path.is_dir() else path.parent
    if not folder.exists():
        raise FileNotFoundError(f"目录不存在：{folder}")
    system = platform.system()
    try:
        if system == "Darwin":
            if path.is_file():
                subprocess.run(["open", "-R", str(path)], check=False, timeout=30)
            else:
                subprocess.run(["open", str(folder)], check=False, timeout=30)
        elif system == "Windows":
            if path.is_file():
                subprocess.run(["explorer", f"/select,{path}"], check=False, timeout=30)
            else:
                subprocess.run(["explorer", str(folder)], check=False, timeout=30)
        else:
            subprocess.run(["xdg-open", str(folder)], check=False, timeout=30)
    except OSError as exc:
        raise RuntimeError(f"无法打开文件夹：{exc}") from exc
    return {"ok": True, "path": str(folder), "file": str(path) if path.is_file() else ""}
