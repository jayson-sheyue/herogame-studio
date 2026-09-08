"""Combat move schema shared by studio bible → fighter.json → Phaser."""

from __future__ import annotations

from copy import deepcopy

MOVE_IDS = (
    "attack",
    "air_attack",
    "attack_up",
    "attack_down",
    "skill",
    "combo_up",
    "combo_down",
    "super",
)

# Defaults mirror game/src/game.js REACH / LUNGE / HIT / DAMAGE.
DEFAULT_MOVES: dict[str, dict] = {
    "attack": {
        "reach": 56,
        "damage": 8,
        "lunge": 170,
        "hit": {"knock": 340, "lift": -36, "stun": 280, "knockdown": False, "stop": 28},
        "effect": "none",
        "effectStrength": 0,
        "projectile": None,
    },
    "air_attack": {
        "reach": 48,
        "damage": 8,
        "lunge": 90,
        "hit": {"knock": 300, "lift": -70, "stun": 260, "knockdown": False, "stop": 28},
        "effect": "none",
        "effectStrength": 0,
        "projectile": None,
    },
    "attack_up": {
        "reach": 52,
        "damage": 8,
        "lunge": 110,
        "hit": {"knock": 240, "lift": -110, "stun": 300, "knockdown": False, "stop": 32},
        "effect": "none",
        "effectStrength": 0,
        "projectile": None,
    },
    "attack_down": {
        "reach": 48,
        "damage": 10,
        "lunge": 40,
        "hit": {"knock": 280, "lift": -24, "stun": 300, "knockdown": False, "stop": 32},
        "effect": "none",
        "effectStrength": 0,
        "projectile": None,
    },
    "skill": {
        "reach": 72,
        "damage": 12,
        "lunge": 200,
        "hit": {"knock": 520, "lift": -160, "stun": 0, "knockdown": True, "stop": 64},
        "effect": "none",
        "effectStrength": 0,
        "projectile": None,
    },
    "combo_up": {
        "reach": 64,
        "damage": 12,
        "lunge": 130,
        "hit": {"knock": 360, "lift": -840, "stun": 0, "knockdown": True, "stop": 72},
        "effect": "launch",
        "effectStrength": 1,
        "projectile": None,
    },
    "combo_down": {
        "reach": 56,
        "damage": 14,
        "lunge": 50,
        "hit": {"knock": 220, "lift": -380, "stun": 0, "knockdown": True, "stop": 64},
        "effect": "none",
        "effectStrength": 0,
        "projectile": None,
    },
    "super": {
        "reach": 88,
        "damage": 22,
        "lunge": 240,
        "hit": {"knock": 680, "lift": -780, "stun": 0, "knockdown": True, "stop": 100},
        "effect": "launch",
        "effectStrength": 1,
        "projectile": None,
    },
}

EFFECTS = {"none", "pull", "launch", "root"}
AILMENTS = {"none", "burn", "freeze", "poison"}

FX_MOVE_IDS = ("skill", "combo_up", "combo_down", "super")
MECHANIC_TYPES = {"melee", "bolt", "beam", "zone", "drop", "homing", "barrage", "trap"}
PROJ_MOTIONS = {"forward", "up", "fall", "field", "hover"}
PROJ_ORIGINS = {"hand", "ahead", "sky", "feet", "air", "front_up", "front_down"}
PROJ_MOTION_DEFAULT = {
    "skill": "forward",
    "combo_up": "up",
    "combo_down": "forward",
    "super": "fall",
}
PROJ_ORIGIN_DEFAULT = {
    "skill": "hand",
    "combo_up": "front_up",
    "combo_down": "front_down",
    "super": "sky",
}

_FALL_MARKS = ("陨石", "炮", "轰炸", "空军", "空袭", "斯图卡", "天降", "覆盖", "闪电")
_FIELD_MARKS = ("阵地", "壁垒", "引力", "坍缩", "枪阵", "固守", "法阵", "领域", "反重力")
_FORWARD_MARKS = ("射击", "手枪", "铁炮", "射线", "光谱", "弹", "枪焰", "光束")

_BEAM_MARKS = ("射线", "光谱", "光束", "激光", "棱镜")
_BARRAGE_MARKS = ("炮火", "覆盖", "齐射", "空袭", "轰炸", "闪电战", "空军", "总动员", "无数", "三段")
_HOMING_MARKS = ("追踪", "导弹", "寻的", "斯图卡")
_TRAP_MARKS = ("阵地", "壁垒", "枪阵", "固守", "陷阱", "踩")
_ZONE_MARKS = ("引力", "法阵", "领域", "反重力", "坍缩", "气流")
_DROP_MARKS = ("陨石", "天降")
_BOLT_MARKS = ("射击", "手枪", "铁炮", "弹", "枪焰")
_BURN_MARKS = ("火", "燃烧", "焚", "炎", "炮火", "枪焰", "陨石", "轰炸", "爆")
_FREEZE_MARKS = ("冰", "冻", "霜", "寒")
_POISON_MARKS = ("毒", "鸩", "瘴", "蛊")


def guess_mechanic(move_id: str, kit_line: str = "", has_proj: bool = False) -> dict:
    """Pick a behavior plugin from the kit sentence. Art/skin is separate."""
    line = str(kit_line or "")
    if any(m in line for m in _BEAM_MARKS):
        return {"type": "beam", "count": 1, "pierce": True, "homing": 0, "delay": 0, "spread": 0, "ticks": 2}
    if any(m in line for m in _BARRAGE_MARKS):
        n = 4 if move_id == "super" else 3
        return {"type": "barrage", "count": n, "pierce": False, "homing": 0, "delay": 140, "spread": 72, "ticks": 1}
    if any(m in line for m in _HOMING_MARKS):
        return {"type": "homing", "count": 1, "pierce": False, "homing": 10, "delay": 0, "spread": 0, "ticks": 1}
    if any(m in line for m in _TRAP_MARKS):
        return {"type": "trap", "count": 1, "pierce": False, "homing": 0, "delay": 0, "spread": 0, "ticks": 1}
    if any(m in line for m in _ZONE_MARKS):
        return {"type": "zone", "count": 1, "pierce": False, "homing": 0, "delay": 0, "spread": 0, "ticks": 5}
    if any(m in line for m in _DROP_MARKS):
        return {"type": "drop", "count": 1, "pierce": False, "homing": 0, "delay": 0, "spread": 0, "ticks": 1}
    if any(m in line for m in _BOLT_MARKS) or (has_proj and move_id == "skill"):
        return {"type": "bolt", "count": 1, "pierce": False, "homing": 0, "delay": 0, "spread": 0, "ticks": 1}
    if has_proj:
        if move_id == "super":
            return {"type": "drop", "count": 1, "pierce": False, "homing": 0, "delay": 0, "spread": 0, "ticks": 1}
        if move_id in {"combo_up", "combo_down"}:
            return {"type": "zone", "count": 1, "pierce": False, "homing": 0, "delay": 0, "spread": 0, "ticks": 4}
        return {"type": "bolt", "count": 1, "pierce": False, "homing": 0, "delay": 0, "spread": 0, "ticks": 1}
    return {"type": "melee", "count": 1, "pierce": False, "homing": 0, "delay": 0, "spread": 0, "ticks": 1}


def guess_ailment(kit_line: str = "") -> str:
    """Status overlay is global (tint/shell/particles), not a per-hero sheet."""
    line = str(kit_line or "")
    if any(m in line for m in _BURN_MARKS):
        return "burn"
    if any(m in line for m in _FREEZE_MARKS):
        return "freeze"
    if any(m in line for m in _POISON_MARKS):
        return "poison"
    return "none"


def _normalize_ailment(raw, kit_line: str = "") -> str:
    src = str(raw).strip().lower() if raw is not None else ""
    if src in AILMENTS:
        return src
    return guess_ailment(kit_line)


def _normalize_mechanic(raw, move_id: str, kit_line: str = "", has_proj: bool = False) -> dict:
    guessed = guess_mechanic(move_id, kit_line, has_proj)
    src = raw if isinstance(raw, dict) else {}
    kind = str(src.get("type") or guessed["type"]).strip().lower()
    if kind not in MECHANIC_TYPES:
        kind = guessed["type"]
    if kind == "melee" and has_proj:
        kind = guessed["type"] if guessed["type"] != "melee" else "bolt"
    return {
        "type": kind,
        "count": int(_clamp_num(src.get("count"), 1, 8, guessed["count"])),
        "delay": int(_clamp_num(src.get("delay"), 0, 800, guessed["delay"])),
        "spread": int(_clamp_num(src.get("spread"), 0, 240, guessed["spread"])),
        "homing": float(_clamp_num(src.get("homing"), 0, 24, guessed["homing"])),
        "pierce": bool(src["pierce"]) if "pierce" in src else bool(guessed["pierce"] or kind == "beam"),
        "ticks": int(_clamp_num(src.get("ticks"), 1, 12, guessed["ticks"])),
    }


def _align_proj_to_mechanic(proj: dict | None, mechanic: dict, kit_line: str = "", move_id: str = "") -> dict | None:
    """Skin stays; motion/hitbox follow the plugin so a gunshot is not a meteor."""
    if not proj or not mechanic:
        return proj
    kind = mechanic.get("type") or "bolt"
    line = str(kit_line or "")
    if kind in {"bolt", "beam"}:
        if proj.get("motion") not in {"forward", "up"}:
            proj["motion"] = "forward"
            proj["origin"] = "hand"
        proj["gravity"] = 0
        if kind == "bolt":
            if float(proj.get("screen") or 0) > 0.16:
                proj["screen"] = 0.12
            if int(proj.get("hitW") or 0) > 72:
                proj["hitW"] = 44
            if int(proj.get("hitH") or 0) > 56:
                proj["hitH"] = 32
            proj["speed"] = int(_clamp_num(proj.get("speed"), 240, 480, 360))
        if kind == "beam":
            proj["speed"] = int(_clamp_num(proj.get("speed"), 0, 200, 40))
            proj["life"] = int(_clamp_num(proj.get("life"), 200, 700, 420))
            if int(proj.get("hitW") or 0) < 160:
                proj["hitW"] = 280
            if int(proj.get("hitH") or 0) > 80:
                proj["hitH"] = 48
    elif kind == "homing":
        if proj.get("motion") == "field":
            proj["motion"] = "forward"
            proj["origin"] = "hand"
        proj["speed"] = int(_clamp_num(proj.get("speed"), 220, 640, 420))
    elif kind == "drop":
        if move_id in {"combo_up", "combo_down"}:
            proj["origin"] = "front_up" if move_id == "combo_up" else "front_down"
            if proj.get("motion") == "fall":
                proj["motion"] = "up" if move_id == "combo_up" else "forward"
                proj["gravity"] = 0
        else:
            proj["motion"] = "fall"
            proj["origin"] = "sky"
    elif kind in {"zone", "trap"}:
        if move_id == "combo_up":
            proj["origin"] = "front_up"
            if proj.get("motion") not in {"up", "forward", "field"}:
                proj["motion"] = "up"
        elif move_id == "combo_down":
            proj["origin"] = "front_down"
            if proj.get("motion") not in {"forward", "field", "fall"}:
                proj["motion"] = "forward"
        else:
            proj["motion"] = "field"
            if proj.get("origin") not in {"ahead", "feet", "front_down"}:
                proj["origin"] = "ahead"
    elif kind == "barrage":
        aerial = any(m in line for m in ("空军", "空袭", "炮火", "轰炸", "陨石", "覆盖", "天降", "闪电战"))
        if move_id in {"combo_up", "combo_down"}:
            proj["origin"] = "front_up" if move_id == "combo_up" else "front_down"
            if proj.get("motion") == "fall":
                proj["motion"] = "up" if move_id == "combo_up" else "forward"
                proj["gravity"] = 0
        elif aerial:
            proj["motion"] = "fall"
            proj["origin"] = "sky"
        elif proj.get("motion") == "fall":
            proj["motion"] = "forward"
            proj["origin"] = "hand"
            proj["gravity"] = 0
            proj["speed"] = int(_clamp_num(proj.get("speed"), 280, 800, 560))
    return proj


def guess_proj_profile(move_id: str, kit_line: str = "") -> dict:
    """Motion defaults from move id + kit label (not Newton-specific)."""
    line = str(kit_line or "")
    motion = PROJ_MOTION_DEFAULT.get(move_id, "forward")
    origin = PROJ_ORIGIN_DEFAULT.get(move_id, "hand")
    if move_id == "combo_up":
        motion, origin = "up", "front_up"
    elif move_id == "combo_down":
        motion, origin = "forward", "front_down"
    elif any(m in line for m in _FALL_MARKS):
        motion, origin = "fall", "sky"
    elif any(m in line for m in _FIELD_MARKS):
        motion, origin = "field", "ahead"
    elif any(m in line for m in _FORWARD_MARKS):
        motion, origin = "forward", "hand"
    if motion == "fall":
        return {
            "motion": "fall",
            "origin": "sky",
            "speed": 240,
            "life": 1600,
            "screen": 0.34,
            "frameRate": 4,
            "gravity": 360,
            "hitW": 140,
            "hitH": 120,
            "spawnFrame": 0.22,
        }
    if motion == "field":
        return {
            "motion": "field",
            "origin": origin,
            "speed": 50,
            "life": 1800,
            "screen": 0.28,
            "frameRate": 4,
            "gravity": 0,
            "hitW": 320,
            "hitH": 220,
            "spawnFrame": 0.22,
        }
    return {
        "motion": "forward",
        "origin": "hand",
        "speed": 360,
        "life": 1200,
        "screen": 0.12,
        "frameRate": 7,
        "gravity": 0,
        "hitW": 44,
        "hitH": 32,
        "spawnFrame": 0.32,
    }


def fx_slot_id(move_id: str) -> str:
    return f"fx_{move_id}"


def move_id_from_fx_slot(slot_id: str) -> str | None:
    if not slot_id.startswith("fx_"):
        return None
    mid = slot_id[3:]
    return mid if mid in MOVE_IDS else None


def _clamp_num(value, lo: float, hi: float, default):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _normalize_hit(raw: dict | None, fallback: dict) -> dict:
    src = raw if isinstance(raw, dict) else {}
    return {
        "knock": int(_clamp_num(src.get("knock"), 0, 1200, fallback["knock"])),
        "lift": int(_clamp_num(src.get("lift"), -1200, 200, fallback["lift"])),
        "stun": int(_clamp_num(src.get("stun"), 0, 2000, fallback["stun"])),
        "knockdown": bool(src["knockdown"]) if "knockdown" in src else bool(fallback["knockdown"]),
        "stop": int(_clamp_num(src.get("stop"), 0, 200, fallback["stop"])),
    }


def _normalize_projectile(raw, move_id: str) -> dict | None:
    if raw is False or raw is None:
        return None
    if raw is True:
        raw = {}
    if not isinstance(raw, dict):
        return None
    hit_fb = {
        "knock": 360,
        "lift": -120,
        "stun": 0,
        "knockdown": True,
        "stop": 40,
    }
    motion = str(raw.get("motion") or PROJ_MOTION_DEFAULT.get(move_id) or "forward").strip().lower()
    if motion not in PROJ_MOTIONS:
        motion = "forward"
    origin = str(raw.get("origin") or PROJ_ORIGIN_DEFAULT.get(move_id) or "hand").strip().lower()
    if origin not in PROJ_ORIGINS:
        origin = "hand"
    blend = str(raw.get("blend") or "add").strip().lower()
    if blend not in {"add", "normal"}:
        blend = "add"
    return {
        "file": str(raw.get("file") or f"fx/{move_id}.png"),
        "frames": int(_clamp_num(raw.get("frames"), 1, 8, 4)),
        "frameWidth": int(_clamp_num(raw.get("frameWidth"), 8, 2048, 0)) or None,
        "frameHeight": int(_clamp_num(raw.get("frameHeight"), 8, 2048, 0)) or None,
        "speed": int(_clamp_num(raw.get("speed"), 40, 1200, 480)),
        "life": int(_clamp_num(raw.get("life"), 200, 4000, 900)),
        "damage": int(_clamp_num(raw.get("damage"), 1, 40, DEFAULT_MOVES[move_id]["damage"])),
        "hit": _normalize_hit(raw.get("hit") if isinstance(raw.get("hit"), dict) else None, hit_fb),
        "spawnFrame": float(_clamp_num(raw.get("spawnFrame"), 0.05, 0.9, 0.35)),
        "motion": motion,
        "origin": origin,
        "blend": blend,
        "screen": float(_clamp_num(raw.get("screen"), 0.08, 0.72, 0.18)),
        "gravity": int(_clamp_num(raw.get("gravity"), 0, 2400, 0)),
        "hitW": int(_clamp_num(raw.get("hitW"), 16, 720, 48)),
        "hitH": int(_clamp_num(raw.get("hitH"), 16, 720, 40)),
    }


def normalize_moves(raw_moves: dict | None, kit: dict | None = None) -> dict[str, dict]:
    """Merge model/user moves onto defaults. kit labels stay separate."""
    incoming = raw_moves if isinstance(raw_moves, dict) else {}
    out: dict[str, dict] = {}
    for move_id in MOVE_IDS:
        base = deepcopy(DEFAULT_MOVES[move_id])
        item = incoming.get(move_id)
        if isinstance(item, str):
            item = {"label": item}
        if not isinstance(item, dict):
            item = {}
        effect = str(item.get("effect") or base["effect"]).strip().lower()
        if effect not in EFFECTS:
            effect = "none"
        proj = item.get("projectile")
        # Ranged moves for skill-family default to wanting a projectile sheet.
        if proj is None and move_id in FX_MOVE_IDS and effect in {"none", "pull"}:
            # Keep None until studio commits FX; inference may set projectile:true.
            pass
        label = str(item.get("label") or (kit or {}).get(move_id) or "").strip()
        projectile = _normalize_projectile(proj, move_id)
        mechanic = _normalize_mechanic(item.get("mechanic"), move_id, label, bool(projectile))
        projectile = _align_proj_to_mechanic(projectile, mechanic, label, move_id)
        if mechanic["type"] == "trap" and effect == "none":
            effect = "root"
        move = {
            "label": label,
            "reach": int(_clamp_num(item.get("reach"), 24, 220, base["reach"])),
            "damage": int(_clamp_num(item.get("damage"), 1, 40, base["damage"])),
            "lunge": int(_clamp_num(item.get("lunge"), 0, 400, base["lunge"])),
            "hit": _normalize_hit(item.get("hit") if isinstance(item.get("hit"), dict) else None, base["hit"]),
            "effect": effect,
            "effectStrength": float(
                _clamp_num(
                    item.get("effectStrength"),
                    0,
                    2,
                    base["effectStrength"] or (1 if effect != "none" else 0),
                )
            ),
            "projectile": projectile,
            "mechanic": mechanic,
            "ailment": _normalize_ailment(item.get("ailment") if "ailment" in item else None, label),
        }
        # Launch implies knockdown-friendly hit if model forgot.
        if move["effect"] == "launch" and not move["hit"]["knockdown"]:
            move["hit"]["knockdown"] = True
            if move["hit"]["lift"] > -200:
                move["hit"]["lift"] = -520
        out[move_id] = move
    return out


def is_fx_slot(slot_id: str) -> bool:
    return move_id_from_fx_slot(slot_id) is not None


def sync_moves_into_fighter(data: dict, bible: dict | None = None) -> dict:
    """Write normalized moves onto fighter.json payload from bible + existing."""
    bible = bible if isinstance(bible, dict) else {}
    kit = bible.get("kit") or data.get("kit") or {}
    existing = data.get("moves") if isinstance(data.get("moves"), dict) else {}
    incoming = bible.get("moves") if isinstance(bible.get("moves"), dict) else existing
    merged = normalize_moves(incoming if isinstance(incoming, dict) else None, kit if isinstance(kit, dict) else None)
    for move_id, move in merged.items():
        old = existing.get(move_id) if isinstance(existing.get(move_id), dict) else {}
        oldp = old.get("projectile") if isinstance(old.get("projectile"), dict) else None
        if oldp and oldp.get("file") and (oldp.get("frameWidth") or oldp.get("frameHeight")):
            seed = {**(move.get("projectile") or {}), **oldp}
            move["projectile"] = _normalize_projectile(seed, move_id)
        oldm = old.get("mechanic") if isinstance(old.get("mechanic"), dict) else None
        if oldm and oldm.get("type") in MECHANIC_TYPES:
            move["mechanic"] = _normalize_mechanic(oldm, move_id, move.get("label") or "", bool(move.get("projectile")))
        move["projectile"] = _align_proj_to_mechanic(
            move.get("projectile"), move.get("mechanic") or {}, move.get("label") or "", move_id
        )
        olda = old.get("ailment")
        if olda in AILMENTS:
            move["ailment"] = olda
    data["moves"] = merged
    return data


def attach_fx_meta(moves: dict, move_id: str, meta: dict, kit: dict | None = None) -> dict:
    """When an FX sheet is committed, bind size fields onto moves[move].projectile."""
    moves = normalize_moves(moves, kit)
    if move_id not in moves:
        return moves
    proj = moves[move_id].get("projectile") or _normalize_projectile({}, move_id)
    assert proj is not None
    proj["file"] = meta.get("file") or f"fx/{move_id}.png"
    proj["frames"] = int(meta.get("frames") or proj["frames"] or 4)
    proj["frameWidth"] = int(meta.get("frameWidth") or proj.get("frameWidth") or 0) or None
    proj["frameHeight"] = int(meta.get("frameHeight") or proj.get("frameHeight") or 0) or None
    kit_line = str((kit or {}).get(move_id) or moves[move_id].get("label") or "")
    profile = guess_proj_profile(move_id, kit_line)
    weak = proj.get("hitW") in (None, 48) and float(proj.get("screen") or 0) <= 0.18
    if weak:
        for key, value in profile.items():
            proj[key] = value
    mec = moves[move_id].get("mechanic") or _normalize_mechanic(None, move_id, kit_line, True)
    moves[move_id]["mechanic"] = mec
    moves[move_id]["projectile"] = _align_proj_to_mechanic(proj, mec, kit_line, move_id)
    if moves[move_id]["reach"] > 64:
        moves[move_id]["reach"] = 48
    return moves
