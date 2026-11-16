"""API keys stay in server memory or an explicitly selected OS credential store."""

import hashlib
import os
import threading

LOCK = threading.RLock()
_session: dict[str, tuple[str, str]] = {}
SERVICE = "herogame-studio"


def slot_for(settings_path) -> str:
    return hashlib.sha256(str(settings_path.resolve()).encode()).hexdigest()


def _keyring():
    try:
        import keyring
        # Do not accept third-party plaintext/file backends as a credential store.
        backend = keyring.get_keyring()
        module = type(backend).__module__
        if not module.startswith(("keyring.backends.macOS", "keyring.backends.Windows", "keyring.backends.SecretService", "keyring.backends.kwallet")):
            raise RuntimeError("unsupported credential backend")
        return keyring
    except Exception:
        raise RuntimeError("系统凭据库不可用。请安装 requirements.txt 并解锁系统钥匙串，或取消「记住密钥」使用本次会话。") from None


def read_key(slot: str, persistent: bool = False) -> tuple[str, str]:
    with LOCK:
        if slot in _session:
            return _session[slot]
        if persistent:
            try:
                key = _keyring().get_password(SERVICE, slot)
            except Exception:
                raise RuntimeError("无法读取系统凭据库。请解锁钥匙串后重试；已记住的密钥尚未更改。") from None
            if key:
                return key, "system"
        key = os.environ.get("STUDIO_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or ""
        return (key.strip(), "environment") if key.strip() else ("", "missing")


def update_key(slot: str, key: str, persistent: bool, was_persistent: bool, commit) -> None:
    """Publish settings and key together, restoring the old OS secret on failure."""
    with LOCK:
        try:
            ring = _keyring() if persistent or was_persistent else None
        except RuntimeError:
            if was_persistent:
                raise RuntimeError("无法访问旧系统凭据，请先解锁凭据库后再替换或清除密钥。原设置尚未更改。") from None
            raise
        old_key = None
        if ring:
            try:
                old_key = ring.get_password(SERVICE, slot)
                if persistent and key:
                    ring.set_password(SERVICE, slot, key)
                elif old_key:
                    ring.delete_password(SERVICE, slot)
            except Exception:
                raise RuntimeError("系统凭据库写入失败，设置未保存。请解锁钥匙串后重试；原设置尚未更改。") from None
        try:
            commit()
        except Exception:
            if ring:
                try:
                    if old_key:
                        ring.set_password(SERVICE, slot, old_key)
                    elif persistent and key:
                        ring.delete_password(SERVICE, slot)
                except Exception:
                    raise RuntimeError("设置写入失败，系统凭据恢复也未完成。请重新设置 API Key。") from None
            raise RuntimeError("设置写入失败，原设置与密钥已保留。") from None
        _session[slot] = (key, "system" if persistent and key else "session" if key else "missing")
