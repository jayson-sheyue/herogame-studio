"""Slot catalog and prompt-inference instructions for the art studio."""

from __future__ import annotations

import re

SPRITE_LOCK = """
HD pixel-art 2D fighting game sprite, Bleach vs Naruto arena-fighter scale
(readable silhouette, not chibi, not King of Fighters close-up).
Crisp pixels, limited palette, 1px dark outline, no anti-aliasing, no blur,
no photorealism, no 3D, no anime screenshot.
BACKGROUND (mandatory): solid flat exact hex #00FFFF cyan only.
No checkerboard, no fake transparency, no texture, no gradient, no shadow, no noise.
Do not paint #00FFFF / aqua / teal / turquoise on the character, weapon, FX, hair, or outline.
FX and particles attached to the body (blade slash, fist glow) must be red, orange, gold, white, or magenta — never cyan-family.
Do NOT paint independent VFX in the character strip: no flying projectiles crossing cells, no summons, no beasts, no afterimage clones, no giant beams.
Those are separate sprites later. This sheet is the fighter's body only, locked to the same slot in every cell.
""".strip()

PORTRAIT_SPRITE_LOCK = """
HD pixel-art desk pet / standing character sprite for desktop companion and portrait action strips.
Readable silhouette at small size — cute and approachable but NOT chibi big-head; face, ears, tail, limbs all readable.
Crisp pixels, limited palette, 1px dark outline, no anti-aliasing, no blur,
no photorealism, no 3D, no anime screenshot.
BACKGROUND (mandatory): solid flat exact hex #00FFFF cyan only.
No checkerboard, no fake transparency, no texture, no gradient, no shadow, no noise.
CHROMA-KEY SAFETY (mandatory): do NOT paint #00FFFF / aqua / teal / turquoise / cyan-green /
mint / sea-green on the character body, hair, clothes, bag, scarf, cloud, props, or outline.
Those colors are the key screen and will be deleted. Remap any teal/cyan clothing to emerald,
navy, magenta, coral, cream, warm orange, or soft pink instead.
No anti-aliased cyan fringe on the silhouette edge.
This sheet is ONE character body only in every cell — no combat VFX, no projectiles, no summons, no weapons slash FX.
No fighting-game arena scale, no battle stances, no stage floor.
""".strip()

PORTRAIT_CHROMA_SAFE = (
    "CHROMA-KEY SAFETY: background is pure #00FFFF only. "
    "Character + props MUST NOT use cyan / aqua / teal / turquoise / mint / cyan-green. "
    "Remap those to emerald, navy, magenta, coral, cream, or warm orange. "
    "Costume fill must be SOLID opaque paint — never leave chroma holes inside dresses, "
    "sleeves, bags, or hair (no #00FFFF showing through the body). "
    "No soft cyan fringe around the silhouette."
)

PORTRAIT_REF_LABEL_TURNAROUND = (
    "This image IS the locked turnaround of THIS desk-pet / portrait character. "
    "Copy THIS exact face, hair, ears, costume, bag/scarf/props, color palette, outline, "
    "and body proportions into EVERY frame. Same identity — not a redesign, not a cousin, "
    "not a new outfit, not a palette swap. Acting changes pose only."
)

PORTRAIT_REF_LABEL_STYLE = (
    "HOUSE STYLE sample only (pixel language). These sample mascots are NOT this character. "
    "Copy outline hardness, pixel density, and silhouette readability only. "
    "Do NOT copy their faces, costumes, or colors onto this character."
)

DESKPET_STYLE_SHEET_NOTE = (
    "This is the DESK-PET / PORTRAIT HOUSE-STYLE sheet — NOT a fighting game style sheet. "
    "Three original sample desk pets or standing mascot characters on cyan showing the shared pixel language. "
    "Follow the developer brief and STYLE LOCK aesthetics. "
    "Sample characters also avoid cyan/teal clothing (chroma-key safety). "
    "No arena fighters, no combat poses, no historical celebrities. No stage. No floor."
)

GAME_STYLE_SHEET_NOTE = (
    "This is the GAME HOUSE-STYLE sheet, not a playable fighter. "
    "Three original dummy fighters on cyan. Same pixel language. "
    "No historical celebrities. No stage. No floor."
)

FX_SUBJECT_MODES = frozenset({"projectile", "figure", "clone"})


def fx_subject_for(bible: dict | None, slot_id: str) -> str:
    """Per fx_* slot: projectile (default) | figure (body/mount skill) | clone (afterimages)."""
    if not str(slot_id).startswith("fx_"):
        return "projectile"
    raw = (bible or {}).get("fx_subjects")
    if not isinstance(raw, dict):
        return "projectile"
    mode = str(raw.get(slot_id) or "projectile").strip().lower()
    return mode if mode in FX_SUBJECT_MODES else "projectile"


FX_LOCK = """
HD pixel-art 2D fighting-game PROJECTILE / VFX strip only.
Crisp pixels, limited palette, no anti-aliasing, no blur,
no photorealism, no 3D, no anime screenshot.
BACKGROUND (mandatory): solid flat exact hex #00FFFF cyan only — continuous field, no panels.
ABSOLUTE SUBJECT: this hero's projectile or impact core ONLY — invent from THIS move's kit, not a generic catalog.
The effect may use a 1px dark outline ON THE PROJECTILE ONLY.
FORBIDDEN SUBJECTS: any human, fighter, face, wig, legs, hands, costume, props held by a person,
full-body silhouette, turnaround pose, idle stance.
FORBIDDEN GENERIC SCIENCE VFX unless THIS hero's kit is about them: prism rainbows, falling apples,
gravity wells, meteors, calculus glyphs, Newton's apple, spectral refraction.
FORBIDDEN LAYOUT ART: black/gray frames, comic panel borders, cell gutters, vertical divider bars,
horizontal rule lines, drop shadows under cells, white/black rectangles around each frame,
storyboard boxes, UI chrome. Cells are separated ONLY by empty #00FFFF — never by drawn lines.
Colors for the effect: red / orange / gold / white / magenta / rainbow spectrum — never cyan-family on the FX itself.
This sheet is NOT a character animation. Zero people in every frame.
""".strip()

FX_FIGURE_LOCK = """
HD pixel-art 2D fighting-game BODY-TECHNIQUE / MOUNTED-CHARGE VFX strip.
Crisp pixels, limited palette, no anti-aliasing, no blur,
no photorealism, no 3D, no anime screenshot.
BACKGROUND (mandatory): solid flat exact hex #00FFFF cyan only — continuous field, no panels.
ABSOLUTE SUBJECT: THIS hero from CHARACTER LOCK performing the special move across frames —
full body (and mount / steed if the kit describes riding). Side-view profile facing RIGHT.
This strip IS the visible skill animation (charge, dash, trample, grapple arc), not a detached projectile.
VFX sparks / dust / impact rings may wrap the body but the fighter (and mount) must stay readable every frame.
FORBIDDEN: stage floor, scenery, UI, unrelated floating orbs with no body, black panel borders.
FORBIDDEN GENERIC SCIENCE VFX unless THIS hero's kit is about them: prism rainbows, falling apples,
gravity wells, meteors, calculus glyphs, Newton's apple, spectral refraction.
FORBIDDEN LAYOUT ART: black/gray frames, comic panel borders, cell gutters, vertical divider bars,
horizontal rule lines, drop shadows under cells, white/black rectangles around each frame,
storyboard boxes, UI chrome. Cells are separated ONLY by empty #00FFFF — never by drawn lines.
""".strip()

FX_CLONE_LOCK = """
HD pixel-art 2D fighting-game CLONE / AFTERIMAGE VFX strip.
Crisp pixels, limited palette, no anti-aliasing, no blur,
no photorealism, no 3D, no anime screenshot.
BACKGROUND (mandatory): solid flat exact hex #00FFFF cyan only — continuous field, no panels.
ABSOLUTE SUBJECT: THIS hero from CHARACTER LOCK as shadow clones, mirror copies, or motion afterimages.
Each frame shows a distinct copy or ghost trail of the SAME fighter — side-view profile facing RIGHT.
Copies may be semi-transparent or tinted but must match costume / weapons from CHARACTER LOCK.
FORBIDDEN: stage floor, scenery, unrelated projectiles with no clone body, black panel borders.
FORBIDDEN GENERIC SCIENCE VFX unless THIS hero's kit is about them: prism rainbows, falling apples,
gravity wells, meteors, calculus glyphs, Newton's apple, spectral refraction.
FORBIDDEN LAYOUT ART: black/gray frames, comic panel borders, cell gutters, vertical divider bars,
horizontal rule lines, drop shadows under cells, white/black rectangles around each frame,
storyboard boxes, UI chrome. Cells are separated ONLY by empty #00FFFF — never by drawn lines.
""".strip()

FX_STRIP_SEPARATION = (
    "CELL SEPARATION: each projectile frame lives in its own region of ONE unbroken #00FFFF field. "
    "Leave empty cyan between neighbors — DO NOT draw black bars, gray gutters, or panel borders. "
    "FX silhouettes must NOT touch or overlap. "
    "Draw the SAME object traveling / spinning / pulsing across the four cells — "
    "not four unrelated doodles, and not a person posing."
)

FX_FIGURE_STRIP_SEPARATION = (
    "CELL SEPARATION: each FULL-BODY figure (and mount if any) lives in its own region of ONE unbroken #00FFFF field. "
    "Leave empty cyan between neighbors — DO NOT draw black bars, gray gutters, or panel borders. "
    "Adjacent silhouettes must differ at thumbnail size — this is ONE skill arc across frames, not four identical poses. "
    "Limbs, mount legs, and weapons travel on arcs. No stage floor."
)

FX_CLONE_STRIP_SEPARATION = (
    "CELL SEPARATION: each clone / afterimage lives in its own region of ONE unbroken #00FFFF field. "
    "Leave empty cyan between neighbors — DO NOT draw black bars, gray gutters, or panel borders. "
    "Each frame shifts the clone trail along the attack path — same costume, distinct positions. "
    "Copies must NOT fuse into one blob; keep readable separation."
)

SCENE_LOCK = """
HD pixel-art 2D fighting game STAGE / MAP, ultra-wide 21:9 panoramic arena
like Bleach vs Naruto / King of Fighters side-scrolling stages with premium pixel detail.
NOT a sprite sheet. NOT a character portrait. Paint the actual place.
No people, no fighters, no faces, no cyan screen, no checkerboard.
Horizontally scrollable battlefield: design as a native wide arena, not a tall 16:9 poster stretched sideways.
Keep the hero landmark readable near center; extend midground and sky to both far left and far right.

FIGHTING PLANE (mandatory): this is a SIDE-VIEW 2D stage, not a 3/4 diorama.
All WALKABLE surfaces — main floor AND high ledges — share ONE depth / one Z-plane.
Fighters are side-view sprites; they stand ON the painted tops as if those tops are the same layer.
High ground is a raised section of that same plane: a vertical SIDE FACE (cliff, step, terrace wall)
capped by a thin walkable top at the same depth as the main floor.
Background (sky, distant monuments, sea) may recede. Playable terrain must NOT.

FORBIDDEN for playable terrain:
- 3/4 view looking down onto pillar/roof tops sitting further BACK than the floor
- platforms as 3D clusters the camera could walk in FRONT of
- a foreground floor strip with high ground parked in the midground behind it
- isometric / bird's-eye tabletops
HUD rectangles, debug overlay blocks, green/blue/red color fills, checkerboard, UI, text, watermark.
Crisp pixels, limited palette, no photorealism.
""".strip()

CG_LOCK = """
HD pixel-art fighting-game cinematic KEYFRAME STRIP, 16:9 overall.
Exactly 4 DIFFERENT acting beats in one horizontal strip, like a storyboard of the same shot.
Still pixel art. NOT photoreal, NOT 3D, NOT live action. No cyan screen. No checkerboard.
No UI, no text, no watermark, no logos. Same costume as the turnaround in every frame.
""".strip()

STYLE_SLOT = {
    "id": "style",
    "title": "游戏风格锚点",
    "group": "style",
    "kind": "sprite",
    "aspect": "16:9",
    "size": "1K",
    "auto_refs": [],
    "global_refs": [],
    "uses_home_stage": False,
    "hint": "全作共用。青屏上的示范格斗角色，锁描边、像素密度、身形占屏。人和地图都吃这张。",
}

STAGE_SLOT = {
    "id": "stage",
    "title": "对战地图",
    "group": "stage",
    "kind": "scene",
    "aspect": "21:9",
    "size": "2K",
    "auto_refs": [],
    "global_refs": ["style"],
    "uses_home_stage": False,
    "hint": "21:9 侧视格斗场。可站立的平地和高台必须画在同一图层（侧视台阶/断面），禁止 3/4 透视把高台画到背景里。禁止画角色。",
}

HERO_SLOTS: list[dict] = [
    {
        "id": "turnaround",
        "title": "人物三视图",
        "group": "lock",
        "kind": "sprite",
        "aspect": "16:9",
        "size": "1K",
        "auto_refs": [],
        "global_refs": ["style"],
        "uses_home_stage": False,
        "hint": "4 帧三视图，原地供人检视。正、3/4、侧、背，同一待战站姿。单行全身，不要第二行头像。",
    },
    {
        "id": "idle",
        "title": "原地呼吸",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧原地待战。脚钉住，呼吸微动。不是走路、不是出招。",
    },
    {
        "id": "walk",
        "title": "地面走动",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧地面前走。左右脚交替、抬腿看得见。不是冲刺、不是原地踏步。",
    },
    {
        "id": "dash",
        "title": "地面冲刺",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧地面前冲。前倾、步幅大。不是走路。",
    },
    {
        "id": "guard",
        "title": "防守状态",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧原地格挡。武器或手臂架住。不是出招、不是受击。",
    },
    {
        "id": "hurt",
        "title": "地面受击",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧地面挨打直到倒地。1 中弹 → 5 躺倒。不要空中，不要循环站起来。",
    },
    {
        "id": "air_hurt",
        "title": "空中受击",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧空中挨打直到落地。脚离地，最后倒地。不要站着挨打。",
    },
    {
        "id": "jump",
        "title": "跳跃",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧原地跳起并自然落地。蹲→起跳→顶点→下落→落地。",
    },
    {
        "id": "attack",
        "title": "地面普攻",
        "group": "combat",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧地面朝前普攻。蓄力→出招→收回。不是技能。",
    },
    {
        "id": "air_attack",
        "title": "空中普攻",
        "group": "combat",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧空中朝前普攻。全程脚离地。不是落地砸。",
    },
    {
        "id": "attack_up",
        "title": "上+普攻（对空）",
        "group": "combat",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧站在地面向空中普攻。武器朝上。是普攻，不是小技能。",
    },
    {
        "id": "attack_down",
        "title": "下+普攻（对地）",
        "group": "combat",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧半空中向地面普攻。俯冲/下劈。是普攻，不是蹲在地上。",
    },
    {
        "id": "skill",
        "title": "地面小技能",
        "group": "combat",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧地面朝前小技能：起手式到结束式。只演施法身体，不画飞出的弹体或召唤兽。",
    },
    {
        "id": "combo_up",
        "title": "上+小技能（对空）",
        "group": "combat",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧站在地面对空小技能：起手到结束。施法朝上。不画独立召唤兽。",
    },
    {
        "id": "combo_down",
        "title": "下+小技能（对地）",
        "group": "combat",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧空中对地小技能：起手到结束。脚离地，施法朝下。不是蹲在地上。",
    },
    {
        "id": "super",
        "title": "大招奥义",
        "group": "combat",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "5 帧奥义起手式到结束式。定格要强。不画出场/胜负，不画独立召唤兽。",
    },
    {
        "id": "opening_cg",
        "title": "出场动作",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "uses_home_stage": False,
        "hint": "5 帧出场挑衅。入场→嘲讽→待战。青屏，不要地图。",
    },
    {
        "id": "defeat_cg",
        "title": "战败动作",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "uses_home_stage": False,
        "hint": "5 帧败者动作。被击败后失衡到倒地定格。青屏，不要地图。",
    },
    {
        "id": "win_cg",
        "title": "战胜动作",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "uses_home_stage": False,
        "hint": "5 帧胜利动作。收招→得意→定格。青屏，不要地图。",
    },
]

FX_SLOTS: list[dict] = [
    {
        "id": "fx_skill",
        "title": "弹道·地面小技能",
        "group": "fx",
        "kind": "sprite",
        "aspect": "16:9",
        "size": "1K",
        "auto_refs": [],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "4 帧飞行弹道/特效条，默认纯弹体（主体选「纯弹道」）。体术/骑乘/冲锋类技能可改「含人物」；分身类选「分身/残影」。",
        "frames": 4,
        "move_id": "skill",
    },
    {
        "id": "fx_combo_up",
        "title": "弹道·上+小技能",
        "group": "fx",
        "kind": "sprite",
        "aspect": "16:9",
        "size": "1K",
        "auto_refs": [],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "4 帧对空弹道/法阵光柱头。默认纯弹体；对空体术可改「含人物」。青底。",
        "frames": 4,
        "move_id": "combo_up",
    },
    {
        "id": "fx_combo_down",
        "title": "弹道·下+小技能",
        "group": "fx",
        "kind": "sprite",
        "aspect": "16:9",
        "size": "1K",
        "auto_refs": [],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "4 帧对地弹道/坠击特效。默认纯弹体；对地体术可改「含人物」。青底。",
        "frames": 4,
        "move_id": "combo_down",
    },
    {
        "id": "fx_super",
        "title": "弹道·奥义",
        "group": "fx",
        "kind": "sprite",
        "aspect": "16:9",
        "size": "1K",
        "auto_refs": [],
        "global_refs": [],
        "uses_home_stage": False,
        "hint": "4 帧奥义特效条。默认纯飞行物；骑乘冲锋/体术奥义/分身奥义请改「含人物」或「分身/残影」。青底。",
        "frames": 4,
        "move_id": "super",
    },
]

HERO_SLOTS = HERO_SLOTS + FX_SLOTS

for _slot in HERO_SLOTS:
    _slot["uses_home_stage"] = False
    if _slot["id"] == "turnaround":
        _slot["global_refs"] = []
        _slot["auto_refs"] = []
        _slot["frames"] = 4
    elif _slot["id"].startswith("fx_"):
        _slot["global_refs"] = []
        _slot["auto_refs"] = []
        _slot["frames"] = 4
    elif _slot["id"] in {"hurt", "air_hurt", "defeat_cg"}:
        _slot["global_refs"] = ["style"]
        _slot["auto_refs"] = ["turnaround"]
        _slot["frames"] = 5
    else:
        _slot["global_refs"] = ["style"]
        _slot["auto_refs"] = ["turnaround"]
        # 新生成统一 5 帧（更宽道具/光波更友好）；已入库的 6 帧人物靠 fighter.json 兼容
        _slot["frames"] = 5

STRIP_SEPARATION = (
    "CELL SEPARATION: each figure lives in its own cell. "
    "Leave a CLEAR empty #00FFFF column between neighbors, at least as wide as the head. "
    "Silhouettes must NOT touch or overlap. "
    "CELL WIDTH IS NOT UNIFORM. A physically wider pose (lying down, full weapon extension, "
    "long sleeves, horizontal slash) MUST occupy a WIDER cell. Standing poses keep extra empty cyan. "
    "NEVER crop, squash, or hide part of a body to fit a 1/N column. "
    "Head-to-toe must be fully visible — when lying down, the WHOLE horizontal body "
    "(head, torso, legs, feet) stays inside that one cell. "
    "If arms, weapons, hair, cloaks, or kicks need room, widen the cell; do not enter the next person."
)

STRIP_RETRY = (
    "CRITICAL RETRY — previous sheet FAILED layout or acting. "
    "ONE horizontal ROW only. EXACTLY {n} FULL-BODY figures. Count the people. "
    "FORBIDDEN: 2 rows, 2x5 contact sheet, bust/head row, 8 or 10 clones, extra copies. "
    "If the count is not {n}, redraw. "
    "CONTINUITY: this is ONE clip, not five similar photos. "
    "Frame N+1 is the in-between of N and N+2. Limbs travel on arcs. "
    "Loop clips (idle/walk/dash/guard): frame {n} blends into frame 1. "
    "Fall clips (hurt/air_hurt/defeat): frame {n} is DOWN/still — do not stand back up. "
    "Walk/dash: opposite legs, passing pose with free foot HIGH. "
    "Attack: wind-up → strike → follow-through → recover. "
    "Down+attack and down+skill: MID-AIR striking toward the ground — NOT a crouch. "
    "Five copies of the same mid-stride / mid-swing = fail. "
    "Onion-skin: same hip X. Ground clips keep the same feet Y. "
    f"{STRIP_SEPARATION} "
    "No cyan FX."
)

FX_STRIP_RETRY = (
    "CRITICAL RETRY — previous sheet drew a PERSON, panel borders, or wrong layout. "
    "ONE horizontal ROW, EXACTLY {n} projectile/VFX frames only. "
    "FORBIDDEN: any human body, face, wig, robe, hands, legs, fighter pose. "
    "FORBIDDEN: black/gray cell frames, vertical divider bars, comic panels, storyboard boxes. "
    "Separate frames with empty #00FFFF only. "
    "Draw only the flying bolt / beam / orb / impact core traveling across cells. "
    "If you see a person or black gutters in the previous attempt, delete them completely."
)

FX_FIGURE_STRIP_RETRY = (
    "CRITICAL RETRY — previous sheet was NOT this hero performing the body skill. "
    "ONE horizontal ROW, EXACTLY {n} FULL-BODY figures of THE SAME hero (mount included if kit says so). "
    "Side profile facing RIGHT. Match the attached turnaround. "
    "FORBIDDEN: detached projectile-only doodles with no fighter, black/gray panel borders, wrong person. "
    "Separate frames with empty #00FFFF only. "
    "Adjacent frames must show different phases of ONE charge / strike / trample arc."
)

FX_CLONE_STRIP_RETRY = (
    "CRITICAL RETRY — previous sheet did not show clone / afterimage copies of this hero. "
    "ONE horizontal ROW, EXACTLY {n} figures — shadow clones or motion ghosts of THE SAME hero. "
    "Side profile facing RIGHT. Match the attached turnaround. "
    "FORBIDDEN: unrelated projectiles, black/gray panel borders, three different people. "
    "Separate frames with empty #00FFFF only. "
    "Each cell is a distinct clone position along the attack path."
)

TURNAROUND_RETRY = (
    "CRITICAL RETRY — previous sheet was NOT a 4-view of this hero. "
    "It copied house-style dummy fighters or drew the wrong person. "
    "Draw FOUR full-body views of ONE fighter from CHARACTER LOCK only: "
    "1 front, 2 three-quarter, 3 right-side, 4 back. Same costume, same scale. "
    "FORBIDDEN: the dummy plate-armor warrior, the white-hair mage, the green archer, "
    "three different people, a 2-row sheet, busts. No style-sheet characters."
)

REF_LABEL_TURNAROUND = (
    "This image IS the playable fighter. Copy this person's face, costume, weapons, "
    "and body. Do not replace them with anyone else."
)
REF_LABEL_PHOTO = (
    "LIKENESS REFERENCE of the real person this fighter must resemble. "
    "Match face structure, age cues, hair shape, and overall build. "
    "TRANSLATE into pixel-art fighting-game turnaround — do NOT paste or output a photograph, "
    "do NOT keep camera noise or photoreal skin. Costume / weapons follow CHARACTER LOCK."
)
REF_LABEL_STYLE = (
    "HOUSE STYLE sample only. These dummy people are NOT the hero. "
    "Copy pixel outline, pixel density, and body scale vs the frame. "
    "Do NOT copy their faces, costumes, weapons, or how many of them there are."
)

LOOP_SLOTS = {"idle", "walk", "dash", "guard", "happy", "sad", "sleep", "wave"}
FALL_SLOTS = {"hurt", "air_hurt", "defeat_cg"}
AIR_ACTING_SLOTS = {"jump", "air_hurt", "air_attack", "attack_down", "combo_down"}

SLOT_BEATS: dict[str, str] = {
    "turnaround": (
        "TURNAROUND / INSPECTION SHEET, STANDING READY for inspection. "
        "Exactly 4 FULL-BODY figures, ONE ROW, same fighting-ready stance, same scale, each centered: "
        "1 front, 2 three-quarter, 3 right-side profile, 4 back. "
        "Not attacking, not walking, no second row of busts, no 5th clone."
    ),
    "idle": (
        "IDLE FIGHT-READY facing RIGHT, IN PLACE, feet planted on one baseline. "
        "LOOP (frame 5 returns to 1). Fighting stance the whole time — weapon/hands up, knees soft. "
        "1 ready rest, 2 chest/shoulders rise (inhale), 3 peak breath (weapon inches up), "
        "4 exhale (shoulders drop), 5 settle still in stance. "
        "NOT walking, NOT attacking. Do not paste one drawing five times."
    ),
    "walk": (
        "GROUND WALK FORWARD facing RIGHT, IN PLACE (hip stays in cell center; do not pan). "
        "LOOP. Opposite legs, passing foot HIGH and obvious. "
        "1 RIGHT heel contact, LEFT leg back extended; "
        "2 RIGHT foot flat, LEFT knee lifting; "
        "3 passing — LEFT foot HIGH, legs cross; "
        "4 LEFT heel contact, RIGHT knee lifting; "
        "5 passing — RIGHT foot HIGH, legs cross, loops to 1. "
        "Not a dash. Not idle. Five similar mid-stride copies = fail."
    ),
    "dash": (
        "GROUND DASH / SPRINT FORWARD facing RIGHT, IN PLACE. LOOP. Lean forward, long stride, faster than walk. "
        "1 plant, 2 push-off, 3 full extend (rear leg straight), 4 landing stride, "
        "5 recover into next plant (loops to 1). Not a walk. Not attacking."
    ),
    "guard": (
        "GROUND GUARD / BLOCK facing RIGHT, IN PLACE, feet planted. LOOP. "
        "Weapon or arms RAISED as a shield the whole time. "
        "1 raise guard, 2 brace (knees bend), 3 absorb hit (torso lean, guard tighter), "
        "4 hold, 5 ready-block looping to 1. NOT attacking, NOT hurt."
    ),
    "hurt": (
        "GROUND HIT until KNOCKDOWN facing RIGHT. ONE-SHOT, do NOT loop back to standing. "
        "Starts on the ground, ends DOWN on the ground. FIVE poses only — do not invent a sixth. "
        "1 impact still standing (body snap), 2 stagger, 3 falling, "
        "4 hits the ground, 5 fully DOWN and still. "
        "Frame 5 is a COMPLETE horizontal body on the ground: head, torso, legs, and feet all visible. "
        "Give frame 5 a WIDER cell. Do not crop a standing-width box out of a lying pose. "
        "Not airborne. Not attacking."
    ),
    "air_hurt": (
        "AIR HIT until FALLING DOWN facing RIGHT. ONE-SHOT. Feet OFF the ground until the last frames. "
        "FIVE poses only — do not invent a sixth. "
        "1 airborne impact, 2 tumble, 3 falling, 4 near the ground, 5 crash/down. "
        "Frame 5 is a COMPLETE body on the ground, not a cropped torso. Wider cell if lying. "
        "Not a standing hurt. Do not loop to a flying idle."
    ),
    "jump": (
        "JUMP IN PLACE facing RIGHT, then NATURAL LANDING. Hip X stays in the cell; only height changes. "
        "1 crouch, 2 takeoff, 3 apex (feet OFF), 4 falling, 5 landing (feet on baseline). "
        "Do not draw five standing poses."
    ),
    "attack": (
        "GROUND NORMAL ATTACK FORWARD facing RIGHT. ONE complete swing on one baseline. "
        "Adapt to this hero (slash / punch / thrust / bow-shot pose) but keep the beats: "
        "1 wind-up (weapon/hands BACK), 2 step-in, 3 strike FORWARD fully extended, "
        "4 follow-through, 5 return to fight-ready. "
        "Weapon MUST travel a visible arc. Not a skill. Not anti-air. Not a crouch."
    ),
    "air_attack": (
        "AIR NORMAL ATTACK FORWARD facing RIGHT. Feet OFF the ground in EVERY frame. "
        "1 hang, 2 wind-up, 3 strike FORWARD, 4 follow-through, 5 recover hang. "
        "Not a dive toward the ground (that's attack_down). Not landing."
    ),
    "attack_up": (
        "UP + NORMAL ATTACK: STANDING ON THE GROUND, striking INTO THE AIR. Facing RIGHT. "
        "Feet on the baseline (may leave slightly at the hit). Weapon/body aim UP. "
        "1 coil on ground, 2 aim up, 3 anti-air strike, 4 peak, 5 land/ready. "
        "This is a NORMAL, not a skill. Not a horizontal standing slash."
    ),
    "attack_down": (
        "DOWN + NORMAL ATTACK: IN MID-AIR, striking TOWARD THE GROUND. Facing RIGHT. "
        "Feet OFF until landing. Dive / stomp / downward slash. "
        "1 airborne, 2 tuck and aim DOWN, 3 falling strike, 4 near ground, 5 land/recover. "
        "NOT a crouch on the ground. NOT a forward air-slash (that's air_attack). NORMAL, not a skill."
    ),
    "skill": (
        "GROUND SPECIAL toward the FRONT: startup through end-lag. Facing RIGHT, feet on baseline. "
        "Show THIS hero casting their kit (magic, particles, summoning GESTURE). "
        "1 gather, 2 charge (hands/weapon glow), 3 CAST toward the front, "
        "4 end-lag, 5 recover to ready. "
        "Small attached sparks on hands/weapon only (red/gold/white/magenta). "
        "Do NOT draw a flying projectile traveling across cells, a second summoned creature, or a screen-wide beam. "
        "The BODY must read as start pose then end pose of a special."
    ),
    "combo_up": (
        "UP + SPECIAL from the GROUND toward the AIR. Facing RIGHT, feet on baseline. "
        "Startup through end-lag of an anti-air cast/strike. "
        "1 plant, 2 aim UP, 3 CAST/strike upward, 4 hold, 5 recover. "
        "Small attached sparks only. No independent summon, no flying missile across the strip."
    ),
    "combo_down": (
        "DOWN + SPECIAL: IN THE AIR, casting/striking TOWARD THE GROUND. Facing RIGHT. "
        "Feet OFF until landing. Startup through end-lag. "
        "1 airborne, 2 aim DOWN, 3 CAST/strike downward, 4 falling end-lag, 5 land/recover. "
        "NOT crouched on the ground. Small attached sparks only. No second creature."
    ),
    "super": (
        "SUPER / ASTRAL: startup through end-lag. Facing RIGHT. Huge readable silhouette change. "
        "1 pose-up, 2 charge, 3 climax (cast or finishing blow), 4 hold power, 5 recover/lock. "
        "Body plus small attached sparks only. No extra fighter, no summoned beast as a second character, "
        "no projectile flying from cell 1 to cell 5."
    ),
    "opening_cg": (
        "INTRO TAUNT facing RIGHT, 5 poses on one baseline, solid #00FFFF only. No stage. "
        "1 enter, 2 plant, 3 taunt the opponent, 4 flourish, 5 fight-ready. "
        "Not a cinematic CG. One-shot, not a walk cycle."
    ),
    "defeat_cg": (
        "LOSER ANIMATION after being beaten, facing RIGHT. ONE-SHOT. FIVE poses only. "
        "1 last hit, 2 stagger, 3 collapse, 4 hit dirt, 5 still/defeated. "
        "Frame 5 is a COMPLETE horizontal body on the ground — head to feet, not a cropped slice. "
        "Give the down pose a WIDER cell. No stage. Do not loop to standing."
    ),
    "win_cg": (
        "VICTORY ANIMATION facing RIGHT, 5 poses on one baseline. "
        "1 finish the fight, 2 recover, 3 victory pose, 4 flourish/taunt, 5 lock. "
        "No stage. Not a skill sheet."
    ),
    "happy": (
        "DESK-PET / STANDING SPRITE HAPPY LOOP facing RIGHT, feet on one baseline. "
        "1 soft smile rest, 2 bounce up / arms lift, 3 peak joy (eyes bright), "
        "4 settle, 5 back toward 1. LOOP. No combat, no weapons swinging, no stage."
    ),
    "sad": (
        "DESK-PET / STANDING SPRITE SAD LOOP facing RIGHT, feet on one baseline. "
        "1 slumped rest, 2 shoulders drop, 3 deepest sigh, 4 small wipe/gesture, "
        "5 settle toward 1. LOOP. Readable emotion. No combat. No stage."
    ),
    "sleep": (
        "DESK-PET / STANDING SPRITE SLEEP LOOP. May sit or lie COMPLETE in a wider cell. "
        "1 doze, 2 deeper sleep (Z cue optional as tiny magenta pixels, never cyan), "
        "3 breathe, 4 stir slightly, 5 back to doze. LOOP. Whole body visible. No stage."
    ),
    "wave": (
        "DESK-PET / STANDING SPRITE WAVE facing RIGHT, feet on one baseline. "
        "1 ready, 2 arm rise, 3 wave peak, 4 wave again / follow-through, 5 recover. "
        "Friendly greeting. LOOP-friendly. No combat. No stage."
    ),
}

SLOT_FRAMEWORK = """
套图框架（职责不许改；演法必须按这个英雄的武器/身法改写：刀客挥砍、枪兵扎刺、弓手开弓、术士结印、拳师出拳等）：
- turnaround 人物三视图：4 帧原地供人检视。正 / 3/4 / 侧 / 背，同一待战站姿。
- idle 原地呼吸：5 帧原地待战架势，脚钉住，只有呼吸和重心。循环。
- walk 地面走动：5 帧在地面向前走。左右脚交替，抬腿高。原地循环，人不要在条上平移。
- dash 地面冲刺：5 帧在地面向前冲。前倾、大步。循环。
- guard 防守状态：5 帧原地格挡。武器/手臂架住。循环。
- hurt 地面受击：5 帧在地面挨打直到倒地。1 中弹站着 → 5 躺倒。禁止循环站起来。
- air_hurt 空中受击：5 帧在空中挨打直到落地。脚离地，最后倒地。
- jump 跳跃：5 帧原地跳起并自然落地。蹲→起→顶→落→落地。人水平不要平移。
- attack 地面普攻：5 帧在地面向前打。蓄力→出招→收回。
- air_attack 空中普攻：5 帧在空中向前打。全程脚离地。不是下砸。
- attack_up 上+普攻：5 帧站在地面向空中打。武器朝上。是普攻。
- attack_down 下+普攻：5 帧半空中向地面打（俯冲/下劈）。禁止蹲在地上。是普攻。
- skill 地面小技能：5 帧在地面朝前施法/特效/召唤的起手式到结束式。只画身体+贴手火花，不画飞弹和召唤兽本体。
- combo_up 上+小技能：5 帧站在地面对空施法起手到结束。
- combo_down 下+小技能：5 帧在空中对地施法起手到结束。脚离地。禁止蹲地。
- super 大招奥义：5 帧奥义起手式到结束式。
- opening_cg 出场动作：5 帧出场挑衅对手。
- defeat_cg 战败动作：5 帧被击败后的败者动作，倒地定格。
- win_cg 战胜动作：5 帧胜利动作。
每个 slots[id] 必须用英文写出编号分镜（三视图 1-4，其余动作一律 1-5）。每一帧写清：脚在地还是离地、双腿、躯干、武器/手。相邻帧是中间帧。禁止只写 "5 frames of walking"。
""".strip()

ALL_SLOTS = [STYLE_SLOT, STAGE_SLOT, *HERO_SLOTS]
SLOT_BY_ID = {s["id"]: s for s in ALL_SLOTS}

# 立绘/桌宠分区槽位（与战斗英雄管线并行；共用 turnaround/idle/walk 语义）
PORTRAIT_SLOTS: list[dict] = [
    {
        "id": "turnaround",
        "title": "人物三视图",
        "group": "lock",
        "kind": "sprite",
        "aspect": "16:9",
        "size": "1K",
        "auto_refs": [],
        "global_refs": [],
        "frames": 4,
        "hint": "4 帧三视图，锁外形。正、3/4、侧、背。",
    },
    {
        "id": "idle",
        "title": "待机呼吸",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "frames": 5,
        "hint": "5 帧待机呼吸循环。",
    },
    {
        "id": "walk",
        "title": "走动",
        "group": "motion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "frames": 5,
        "hint": "5 帧地面走动循环。",
    },
    {
        "id": "happy",
        "title": "开心",
        "group": "emotion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "frames": 5,
        "hint": "5 帧开心/欢呼循环。",
    },
    {
        "id": "sad",
        "title": "沮丧",
        "group": "emotion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "frames": 5,
        "hint": "5 帧沮丧循环。",
    },
    {
        "id": "sleep",
        "title": "睡觉",
        "group": "emotion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "frames": 5,
        "hint": "5 帧睡觉循环；躺姿画完整。",
    },
    {
        "id": "wave",
        "title": "挥手",
        "group": "emotion",
        "kind": "sprite",
        "aspect": "21:9",
        "size": "1K",
        "auto_refs": ["turnaround"],
        "global_refs": ["style"],
        "frames": 5,
        "hint": "5 帧挥手打招呼。",
    },
]
PORTRAIT_SLOT_IDS = {s["id"] for s in PORTRAIT_SLOTS}
for _ps in PORTRAIT_SLOTS:
    if _ps["id"] not in SLOT_BY_ID:
        SLOT_BY_ID[_ps["id"]] = _ps

PORTRAIT_DEFAULT_PLAN_IDS = ("turnaround", "idle", "walk")


def normalize_portrait_slot(raw: dict | str) -> dict:
    """User/preset slot → full slot meta (id, title, frames, refs…)."""
    if isinstance(raw, str):
        raw = {"id": raw}
    sid = str(raw.get("id") or "").strip()
    if not sid:
        raise ValueError("槽位缺少 id")
    sid = re.sub(r"[^a-zA-Z0-9_]+", "_", sid).strip("_").lower() or "custom"
    if sid[0].isdigit():
        sid = f"act_{sid}"
    preset = next((dict(s) for s in PORTRAIT_SLOTS if s["id"] == sid), None)
    base = preset or {
        "id": sid,
        "title": str(raw.get("title") or sid),
        "group": "custom",
        "kind": "sprite",
        "aspect": "16:9" if sid == "turnaround" else "21:9",
        "size": "1K",
        "auto_refs": [] if sid == "turnaround" else ["turnaround"],
        "global_refs": [] if sid == "turnaround" else ["style"],
        "frames": 4 if sid == "turnaround" else 5,
        "hint": "",
    }
    title = str(raw.get("title") or base.get("title") or sid).strip() or sid
    frames = int(raw.get("frames") or base.get("frames") or (4 if sid == "turnaround" else 5))
    frames = 4 if sid == "turnaround" else max(2, min(frames, 8))
    out = {**base, "id": sid, "title": title, "frames": frames}
    if raw.get("hint"):
        out["hint"] = str(raw["hint"])
    else:
        out["hint"] = f"{frames} 帧「{title}」动作条。" if sid != "turnaround" else base.get("hint") or "4 帧三视图，锁外形。"
    # Keep SLOT_BY_ID in sync so wrap_prompt works for custom ids
    SLOT_BY_ID[sid] = {**SLOT_BY_ID.get(sid, {}), **out}
    return out


def normalize_portrait_slot_list(raw_slots: list | None, *, fallback_all: bool = True) -> list[dict]:
    if not raw_slots:
        if fallback_all:
            return [normalize_portrait_slot(s) for s in PORTRAIT_SLOTS]
        return [normalize_portrait_slot(s) for s in PORTRAIT_SLOTS if s["id"] in PORTRAIT_DEFAULT_PLAN_IDS]
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw_slots:
        try:
            slot = normalize_portrait_slot(item)
        except ValueError:
            continue
        if slot["id"] in seen:
            continue
        seen.add(slot["id"])
        out.append(slot)
    return out


def portrait_infer_system_for(slots: list[dict]) -> str:
    keys = ", ".join(f'"{s["id"]}"' for s in slots)
    lines = "\n".join(
        f'- {s["id"]}（{s["title"]}）：exactly {s["frames"]} frames'
        + ("；三视图：正/3/4/侧/背" if s["id"] == "turnaround" else "；侧视全身动作条")
        for s in slots
    )
    return f"""
你是桌宠/立绘小人的分镜师。输出可生图的英文动作条提示词。
开发者只给人物形象与可选配饰，并已指定要做的套图清单。不要技能机制、不要战斗数值、不要地图。

硬性要求：
- 青屏 #00FFFF；1px 描边高清像素；跟风格锚点同一像素语言。
- 身形可读，可略偏可爱桌宠，但禁止 Q 版大头到认不出四肢。
- 禁止战斗招式、武器连斩、弹道、舞台地面材质。
- 人物主体（发/衣/配饰/描边）禁止使用接近青底的颜色：青/青绿/水色/teal/turquoise；若形象里有这类色，英文提示词里必须改写成翠绿/藏蓝/品红/珊瑚/奶油色等，方便去青抠图。
- 动作条：exactly N DIFFERENT full-body figures，ONE horizontal ROW，right-facing SIDE PROFILE（三视图除外）。
- 除三视图外，所有动作条必须与 turnaround 同一人：同一张脸、发型、耳朵、服装、配饰与色盘，只改姿势。
- 格间留空青缝；循环槽最后一帧接回第 1 帧。
- 只为下列套图写 prompts，不要自创额外槽位：
{lines}

只输出 JSON，不要 Markdown：
{{
  "portrait_id": "ascii_snake_id",
  "display_name": "中文名",
  "one_liner": "一句话定位",
  "visual_lock": "中文，冻结外形+配饰",
  "prompts": {{ {keys} }}
}}
每个 prompts[id] 必须编号写清每一帧可见差别；帧数必须与上表一致。
""".strip()


PORTRAIT_INFER_SYSTEM = portrait_infer_system_for(PORTRAIT_SLOTS)

PORTRAIT_SLOT_INFER_SYSTEM = """
你是桌宠/立绘小人的分镜师。开发者对某一套动作条不满意，要你只重写这一槽的英文生图提示词。
不要改其他槽，不要输出台词，不要输出 portrait_id。

必须遵守：
- 同一套 visual_lock（脸、服装、配饰、剪影）。
- 桌宠/立绘小人：可读全身、可略可爱，禁止 Q 版大头到认不出四肢；禁止战斗招式、弹道、武器连斩、舞台地面。
- 动作条：exactly N DIFFERENT full-body figures（三视图 exactly 4），ONE horizontal ROW。
  动作槽一律 right-facing SIDE PROFILE；三视图：front / 3/4 / side / back。
- 除三视图外，必须写成「与已锁定三视图同一人」：同一脸/发型/耳朵/服装/配饰/色盘，只改姿势。
- 人物主体禁止青/青绿/水色/teal/turquoise（与 #00FFFF 青底冲突，去青会抠穿）；改用翠绿/藏蓝/品红/珊瑚/奶油色等。
- 格间留空青缝；循环槽最后一帧接回第 1 帧。
- 英文 prompt 必须含编号分镜，每帧写清脚、腿、躯干、配饰的可见差别。
- 若开发者写了「哪里不满意」，这是最高优先级，禁止复读旧稿。prompt_zh 说明按意见改了什么。
- 不要写 transparent。纯色 #00FFFF 青底。

只输出 JSON：
{ "prompt": "english image prompt with numbered per-frame acting that APPLIES the developer's note", "prompt_zh": "中文对照：这一槽画什么、几帧、每帧动作、以及如何改掉开发者指出的问题" }
""".strip()


def normalize_product_line(line: str | None) -> str:
    k = str(line or "").strip().lower()
    if k in ("portrait", "portraits", "desk-pet", "desk_pet", "deskpet"):
        return "deskpet"
    return "herogame"


def lock_for(kind: str, product_line: str | None = None) -> str:
    if kind == "scene":
        return SCENE_LOCK
    if kind == "cg":
        return CG_LOCK
    if normalize_product_line(product_line) == "deskpet":
        return PORTRAIT_SPRITE_LOCK
    return SPRITE_LOCK


STYLE_INFER_SYSTEM = """
你是「英灵大乱斗」的美术总监。先锁全作像素语言，再画英雄和地图。
输出一张风格锚点图的英文提示词：青屏上站 3 个原创示范格斗角色（不是历史名人），
用来冻结描边、像素密度、身形占屏、有限色盘。

硬性要求：
- 3 个剪影明显不同的示范角色并排：壮硕近战、纤长施法、敏捷远程。
- 原创设计，禁止秦始皇、宙斯、或任何真实历史/神话名人。
- 同一套像素语言：1px 深色描边、高清像素、有限色盘、对战身形约占屏高 30%。
- 纯色 #00FFFF 底，不要地面、舞台、棋盘格、文字、UI。
- 不要 transparent。

只输出 JSON：
{
  "visual_lock": "中文，冻结的像素语言（描边、色温、身形比例、禁止项）",
  "prompt": "english image prompt..."
}
""".strip()


DESKPET_STYLE_INFER_SYSTEM = """
你是桌宠/立绘项目的像素美术总监。开发者会给出风格意向备注（美学气质、比例、参考作品、色盘偏好）——这是主输入，必须优先落实，不要默认套对战格斗模板。

输出一张「风格锚点图」的英文生图提示词：青屏上 3 个原创示范小人/桌宠（不是格斗角色），用来冻结描边、像素密度、身形比例、色盘。

硬性要求：
- 3 个剪影明显不同的原创示范并排；可以是不同物种/发型/配饰的桌宠小人，都是「可站立、可做成动作条」的全身侧视可读剪影。
- 禁止默认写成「壮硕近战 + 纤长法师 + 敏捷弓手」格斗三元组，除非用户备注明确要求。
- 禁止：对战、擂台、格斗架势、武器对砍、Bleach/Naruto/KOF 等对战游戏套话、历史/神话名人。
- 用户备注中的美学（例如宫崎骏奇幻色彩、苹果 UI 圆润饱满质感等）必须写进 visual_lock 和 prompt，不要忽略。
- 1px 深色描边、高清像素、有限且饱和的色盘；身形约占屏高 25–35%（桌宠可读，可略可爱但非 Q 版大头）。
- 纯色 #00FFFF 底，不要 ground/floor/stage/checkerboard/text/UI/transparent。
- 示范角色衣服/配饰禁止青/青绿/水色/teal/turquoise（与抠图青底冲突，请改成翠绿/藏蓝/品红/珊瑚等）。

只输出 JSON：
{
  "visual_lock": "中文，冻结像素语言（按用户备注定制，勿抄对战游戏套话）",
  "prompt": "english image prompt..."
}
""".strip()


def style_infer_system(product_line: str | None = None) -> str:
    if normalize_product_line(product_line) == "deskpet":
        return DESKPET_STYLE_INFER_SYSTEM
    return STYLE_INFER_SYSTEM


STAGE_INFER_SYSTEM = """
你是「英灵大乱斗」的关卡美术。地图是可复用的对战舞台，不属于某一个英雄。
用户给地点描述，以及地形意向。你写出一张 21:9 超宽横版格斗场地的英文提示词，
并给出与画面一致的 collision 矩形。游戏用这些矩形做物理，画面必须把对应地形画出来。

硬性要求：
- 画地方，不画人。禁止任何角色、脸、剪影人、兵马俑士兵特写当主角。
- 按「可左右卷轴的宽战场」构图：主地标放中间，两侧仍有可战斗空间。
- 格斗主站立面按地点自定（常见约 y≈0.62–0.70）。高台更靠上。若有壕沟：必须在画面里画出约一人物身高的落差与沟底，让玩家一眼能读；collision 的 floors 对齐画面上的主地面顶边与沟底顶边，禁止画看不见的空气墙。
- 可站立面必须同一侧视图层：平地、凹地和高台是同一格斗平面上的高低差，不是「前景地板 + 中景石台」。
- 高台画成侧视断面：竖直的台阶墙面朝向镜头所在的格斗平面，顶面是一条窄的可站立边，禁止 3/4 俯看柱顶/屋顶。
- 远景（天空、远处金字塔、海）可以有纵深。能站人的石头/地板不能往后缩。
- 高台、断桥、凹地必须写成这个地点的真实建筑/地貌，禁止写成色块、HUD、调试矩形。
- 地面必须能当格斗地板读：有厚度的前景站立平面、中景层次、远处天空。
- 高清像素、有限色盘，对标死神 vs 火影 / 拳皇宽舞台，不是写实照片，不是沙盘模型。
- 禁止青屏、棋盘格、UI、文字、watermark。不要写 transparent。
- prompt 里必须用英文写清：哪一段是主地面、哪一段是可跳上的高台、哪一段是更深的可站立壕沟（约 fighter-tall，有底）；并写 SIDE-VIEW SAME PLANE。禁止 death pit / instant-kill abyss。
- collision 与 prompt/画面必须同一套布局。坐标系：原点左上，x/y/w/h 都是 0–1。凹地写成更低的 floors，pits=[]。不要为了「数值一人深」而偏离画面。

地形意向：
- flat：只有一条通铺地面。platforms=[] pits=[] floors=[{x:0,y:0.84,w:1,h:0.06}]
- platforms：同一图层上的侧视台阶/高台（不是往后缩的 3D 石堆）。
- pits：画面里画出约一人深、有底的壕沟；collision 用更低 floors 对齐沟底，pits=[]。
- mixed：同时有高台和凹地，全部在同一格斗平面，且碰撞贴合所画地形。
- auto：宫廷/广场用 flat；桥、悬崖、陵墓坑道、屋顶战用 platforms / pits / mixed。仍须侧视同一平面。

示例（mixed：画面中央有约一人深可站立壕沟 + 桥上石台；数字仅示例，以实际画面为准）：
floors: [{x:0,y:0.65,w:0.38,h:0.06},{x:0.38,y:0.96,w:0.24,h:0.05},{x:0.62,y:0.65,w:0.38,h:0.06}]
platforms: [{x:0.41,y:0.42,w:0.18,h:0.04}]
pits: []

只输出 JSON：
{
  "stage_id": "ascii_snake_id",
  "display_name": "中文地图名",
  "visual": "中文场景要点，写清哪段是主地面/高台/可站立凹地（约一人深、有底）",
  "prompt": "english image prompt that paints those ledges and walkable trenches as real scenery...",
  "collision": {
    "floors": [{"x":0,"y":0.84,"w":1,"h":0.06}],
    "platforms": [],
    "pits": []
  }
}
""".strip()

INFER_SYSTEM = """
你是「英灵大乱斗」的首席角色设计师兼分镜师。游戏是网页 2D 横版双人格斗，像素风，对标死神 vs 火影。
技能键低门槛：地面普攻、上键+普攻对空、下键+普攻对地；地面小技能、上键+小技能对空、下键+小技能对地；大招另出。

开发者只给三件事：人物形象、武器配饰、技能机制短述。你必须把它们冻成可生图的分镜提示词。
不要发明变身槽。不要设计地图。不要给任何槽位画舞台背景。

设计原则：
- 剪影必须一眼能认出这个人；服装和武器必须锁死，以后所有关键帧遵守 visual_lock。
- 技能要像「这个人的传说/发明被做成了招式」，招式读法必须贴开发者给的机制短述，不要另起一套。
- 像素规格：高清像素、1px 深色描边、有限色盘、对战身形约占屏高 30%。
- 精灵：exactly 5 DIFFERENT full-body figures（三视图 exactly 4），ONE horizontal ROW，right-facing SIDE PROFILE（三视图除外）。
  禁止 2 行、2x5、头像条、8/10 个克隆。游戏会切开在同一位置播放：身体中轴同一 X、身形同一尺寸。
  相邻帧是中间帧。腿、躯干、武器沿弧线变。禁止五张同一姿势。
  格间必须留出至少「头宽」的空青缝，人物剪影禁止相碰或叠进下一格；兵器/头发/披风/踢腿不准伸进邻帧。
  solid #00FFFF。贴身火花用红/橙/金/白/品红，禁止青/青绿。不要画舞台和地面材质。
- 三视图必须画开发者给的这个历史人物，禁止画成风格锚点上的示范战士/法师/弓手。四格是同一人的正/3/4/侧/背。
- 循环槽（idle/walk/dash/guard）第 5 帧接回第 1 帧。受击/战败第 5 帧是倒地定格，禁止站起来循环。
  出招/跳跃/出场胜负是一条完整动作，第 5 帧收到待战或落地，不必把出招本身循环。

""" + SLOT_FRAMEWORK + """

- 提示词用英文，必须按上面框架逐帧编号写可见差别。不要写 transparent。
- 同时写可进游戏的台词（仅 select/intro/hurt/super/win/defeat 六槽；不要写普攻、小技能、组合技）。每句必须短到能在游戏里完整念完。

只输出 JSON，不要 Markdown。结构：
{
  "hero_id": "ascii_snake_id",
  "display_name": "中文名",
  "one_liner": "一句话定位，中文",
  "visual_lock": "中文，冻结的外形+武器配饰，以后所有图必须遵守",
  "kit": {
    "attack": "中文地面普攻名称",
    "air_attack": "中文空中普攻名称",
    "attack_up": "中文上+普攻名称",
    "attack_down": "中文下+普攻名称",
    "skill": "中文地面小技能名称",
    "combo_up": "中文上+小技能名称",
    "combo_down": "中文下+小技能名称",
    "super": "中文奥义名称"
  },
  "moves": {
    "attack": {
      "reach": 56,
      "damage": 8,
      "lunge": 170,
      "hit": {"knock": 340, "lift": -36, "stun": 280, "knockdown": false, "stop": 28},
      "effect": "none",
      "effectStrength": 0,
      "projectile": null,
      "mechanic": {"type": "melee", "count": 1, "delay": 0, "spread": 0, "homing": 0, "pierce": false, "ticks": 1},
      "ailment": "none"
    },
    "air_attack": { "...同上字段..." },
    "attack_up": { "...同上字段..." },
    "attack_down": { "...同上字段..." },
    "skill": {
      "reach": 48,
      "damage": 12,
      "lunge": 80,
      "hit": {"knock": 200, "lift": -40, "stun": 120, "knockdown": false, "stop": 32},
      "effect": "none",
      "effectStrength": 0,
      "projectile": true,
      "mechanic": {"type": "bolt", "count": 1, "delay": 0, "spread": 0, "homing": 0, "pierce": false, "ticks": 1},
      "ailment": "none"
    },
    "combo_up": {
      "reach": 64,
      "damage": 12,
      "lunge": 100,
      "hit": {"knock": 360, "lift": -840, "stun": 0, "knockdown": true, "stop": 72},
      "effect": "launch",
      "effectStrength": 1,
      "projectile": true,
      "mechanic": {"type": "zone", "count": 1, "delay": 0, "spread": 0, "homing": 0, "pierce": false, "ticks": 5},
      "ailment": "none"
    },
    "combo_down": {
      "reach": 56,
      "damage": 14,
      "lunge": 50,
      "hit": {"knock": 220, "lift": -380, "stun": 0, "knockdown": true, "stop": 64},
      "effect": "pull",
      "effectStrength": 1,
      "projectile": true,
      "mechanic": {"type": "trap", "count": 1, "delay": 0, "spread": 0, "homing": 0, "pierce": false, "ticks": 1},
      "ailment": "poison"
    },
    "super": {
      "reach": 48,
      "damage": 22,
      "lunge": 120,
      "hit": {"knock": 680, "lift": -780, "stun": 0, "knockdown": true, "stop": 100},
      "effect": "launch",
      "effectStrength": 1,
      "projectile": true,
      "mechanic": {"type": "drop", "count": 1, "delay": 0, "spread": 0, "homing": 0, "pierce": false, "ticks": 1},
      "ailment": "burn"
    }
  },
  "voice": {
    "persona": "中文，说话方式",
    "gender": "male 或 female 或 neutral",
    "lines": {
      "select": {"text": "选人浏览时临时选中，须能完整念完", "emotion": "怎么演", "tag": "[determination]"},
      "intro": {"text": "刚出场亮身份，须能完整念完", "emotion": "怎么演", "tag": "[awe]"},
      "hurt": {"text": "受击痛呼，极短，1–4 字", "emotion": "怎么演", "tag": "[agitation]"},
      "super": {"text": "奥义，须能完整念完", "emotion": "怎么演", "tag": "[anger]"},
      "win": {"text": "胜利，须能完整念完", "emotion": "怎么演", "tag": "[amusement]"},
      "defeat": {"text": "战败，须能完整念完", "emotion": "怎么演", "tag": "[frustration]"}
    }
  },
  "home_stage_hint": "",
  "slots": {
    "turnaround": "...",
    "idle": "...",
    "walk": "...",
    "dash": "...",
    "guard": "...",
    "hurt": "...",
    "air_hurt": "...",
    "jump": "...",
    "attack": "...",
    "air_attack": "...",
    "attack_up": "...",
    "attack_down": "...",
    "skill": "...",
    "combo_up": "...",
    "combo_down": "...",
    "super": "...",
    "opening_cg": "...",
    "defeat_cg": "...",
    "win_cg": "...",
    "fx_skill": "...",
    "fx_combo_up": "...",
    "fx_combo_down": "...",
    "fx_super": "..."
  },
  "slots_zh": {
    "turnaround": "...",
    "idle": "...",
    "walk": "...",
    "dash": "...",
    "guard": "...",
    "hurt": "...",
    "air_hurt": "...",
    "jump": "...",
    "attack": "...",
    "air_attack": "...",
    "attack_up": "...",
    "attack_down": "...",
    "skill": "...",
    "combo_up": "...",
    "combo_down": "...",
    "super": "...",
    "opening_cg": "...",
    "defeat_cg": "...",
    "win_cg": "...",
    "fx_skill": "...",
    "fx_combo_up": "...",
    "fx_combo_down": "...",
    "fx_super": "..."
  }
}
slots 里角色动作 19 键 + 4 个 fx_* 弹道槽必须齐全。角色动作按套图框架逐帧编号写英文分镜（三视图 4 帧，其余动作一律 5 帧）。禁止空泛的 "5 frames of X"。出场/战胜/战败都是 5 帧青屏动作（战败倒地定格），不是 CG。
fx_* 槽：exactly 4 帧特效条，ONE ROW，solid #00FFFF。默认 fx_subjects=projectile：只画弹体/光束，禁止画人。
若 bible.fx_subjects 某槽为 figure：画英雄本人（或骑乘）完成体术/冲锋类技能，需全身、侧视朝右，可附三视图参考。
若为 clone：画同一英雄的分身/残影/重影，仍需全身、侧视朝右。
fx_* 必须按这个英雄自己的 kit 写题材。禁止套用其他英雄的标志物。
slots_zh 与 slots 同键齐全：给中文开发者的对照说明（构图、帧数、每帧动作、禁止项）。不要逐字翻译画风锁套话。
moves 8 键必须齐全：数值供游戏读取。effect 只能是 none / pull / launch / root。
mechanic.type 只能是 melee / bolt / beam / zone / drop / homing / barrage / trap。这是行为插件，和贴图无关：同一张 fx PNG 可以挂到不同 mechanic 上换手感。
- melee：近战，不飞弹。
- bolt：一发直线弹。
- beam：从手上伸出短时光束，可穿透。
- zone：贴地持续法阵，ticks 次伤害（pull/launch 靠 effect）。
- drop：从天砸下。
- homing：追踪（可与 fall 运动组合，如俯冲）。
- barrage：同一张贴图连发 count 发，delay/spread 控制间隔和落点。
- trap：贴地一次命中后停留（适合壁垒/踩踏/枪阵），effect 常用 root。
projectile: true 表示该招需要远程弹道（稍后再出 fx_* 图）；false/null 表示纯近战。远程招 reach 宜短（身体挥击框），伤害主要靠弹。
同一英雄的 4 个技能 mechanic 必须互不相同，禁止四个都是 bolt。按 kit 句子选插件，不要按画风选。
pull=把敌人吸向自己；launch=打飞；root=短暂禁锢（禁移动）。
ailment 只能是 none / burn / freeze / poison。这是打中后挂在敌人身上的状态，和 effect 分开：effect 管击退，ailment 管燃烧/冰冻/中毒。不要为 ailment 设计新贴图槽。kit 里写了火/炮火/陨石→burn，冰/霜→freeze，毒/鸩→poison，否则 none。
voice.lines 每个键是对象 {text, emotion, tag}。
""".strip()

SLOT_INFER_SYSTEM = """
你是「英灵大乱斗」的分镜师。开发者对某一张关键帧不满意，要你只重写这一槽的英文生图提示词。
不要改其他槽，不要输出台词，不要输出 hero_id。

必须遵守：
- 同一套 visual_lock（脸、服装、武器）。
- 演法按这个英雄的武器改（刀/枪/弓/术/拳），但槽位职责必须符合套图框架。
- 精灵：动作条 exactly 5 DIFFERENT full-body figures（三视图 exactly 4），ONE ROW, right-facing SIDE PROFILE, #00FFFF only.
  禁止 2 行/8 人/10 人/头像条。相邻帧是中间帧。人钉在每格同一中心、同一尺寸。
  格间留出至少头宽的空青缝，剪影禁止相碰，兵器/头发/披风不准伸进邻帧。
- 三视图：exactly 4 FULL-BODY figures, ONE ROW: front / 3/4 / side / back。
- idle/walk/dash/guard 循环（第 5 帧接回第 1）。hurt/air_hurt/defeat 倒地定格，禁止站起来循环。
- attack_down 是半空中对地，combo_down 是空中对地技能，禁止画成蹲地。
- 技能/奥义只画起手式到结束式的身体，贴手火花可以，禁止飞弹穿越格子、禁止第二只召唤兽。
- 若槽是 fx_*：看 fx_subjects — projectile 只画弹道/特效禁止画人；figure 画英雄本人完成体术/骑乘/冲锋；clone 画分身/残影。禁止套用其他英雄标志物。
- 英文 prompt 必须含编号分镜，每帧写脚、腿、躯干、武器。
- 若开发者写了「哪里不满意」，这是最高优先级，禁止复读旧稿。prompt_zh 说明按意见改了什么。
- 不要写 transparent。

""" + SLOT_FRAMEWORK + """

只输出 JSON：
{ "prompt": "english image prompt with numbered per-frame acting that APPLIES the developer's note", "prompt_zh": "中文对照：这一槽画什么、几帧、每帧动作、以及如何改掉开发者指出的问题" }
""".strip()

VOICE_LINES: list[dict] = [
    {"id": "select", "title": "选人", "hint": "浏览时临时选中（不用确认），须能完整念完"},
    {"id": "intro", "title": "出场", "hint": "对战刚出场，须能完整念完"},
    {"id": "hurt", "title": "受击", "hint": "被打中的短促痛呼，1–4 字"},
    {"id": "super", "title": "奥义", "hint": "须有气势，须能完整念完"},
    {"id": "win", "title": "胜利", "hint": "须能完整念完"},
    {"id": "defeat", "title": "战败", "hint": "须能完整念完"},
]

DEFAULT_TTS_VOICE = {
    "male": "Charon",
    "female": "Kore",
    "neutral": "Puck",
}

LINE_PERFORMANCE = {
    "select": {"emotion": "沉稳短促，像浏览时顺口点到自己", "tag": "[determination]"},
    "intro": {"emotion": "开场亮相，先压后抬，有身份感", "tag": "[awe]"},
    "hurt": {"emotion": "被打中，痛、短、真的挨了打", "tag": "[agitation]"},
    "super": {"emotion": "奥义，先憋再爆，把字砸出去", "tag": "[anger]"},
    "win": {"emotion": "胜负已分，轻蔑或从容", "tag": "[amusement]"},
    "defeat": {"emotion": "不甘，气短，不要播音腔", "tag": "[frustration]"},
    "transform": {"emotion": "变身升格，声音拉开", "tag": "[awe]"},
}

VOICE_INFER_SYSTEM = """
你是「英灵大乱斗」的台词导演兼配音指导。给格斗角色写战斗台词，并写清怎么演。
像角色自己在喊，不要解说、旁白、舞台提示、引号。
口吻必须贴合这个历史/神话人物的身份，并呼应已有技能名。
游戏里只播这六句，不要写普攻、小技能、组合技或其他槽。
每句必须短到能在游戏里完整念完，禁止写到一半会被动作切掉的长句。
select（浏览时临时选中）、intro（刚出场）、super（奥义）、win、defeat：相对可稍长，仍须一口气念完。
hurt（受击）：极短促，1–4 字，像痛呼不是句子。
emotion 写给 Gemini-TTS 的表演提示：语气、气口、力度，不要写解释。
tag 只能是一个方括号标签，例如 [aggression] [anger] [determination] [excitement] [tension] [agitation] [amusement] [frustration] [awe] [whispers] [fast] [slow]。
用户会指定台词语言与说话人年龄段；lines 里的 text 必须用该语言书写（不要混用其他语言）。

只输出 JSON：
{
  "persona": "中文，说话方式与声音气质",
  "gender": "male 或 female 或 neutral",
  "lines": {
    "select": {"text": "...", "emotion": "...", "tag": "[determination]"},
    "intro": {"text": "...", "emotion": "...", "tag": "[awe]"},
    "hurt": {"text": "...", "emotion": "...", "tag": "[agitation]"},
    "super": {"text": "...", "emotion": "...", "tag": "[anger]"},
    "win": {"text": "...", "emotion": "...", "tag": "[amusement]"},
    "defeat": {"text": "...", "emotion": "...", "tag": "[frustration]"}
  }
}
""".strip()

VOICE_LANGUAGES = {
    # 常用（置顶）
    "cmn-CN": "普通话（简体）",
    "cmn-TW": "台湾国语",
    "yue-HK": "粤语",
    "en-US": "英语（美国）",
    "en-GB": "英语（英国）",
    "en-IN": "英语（印度）",
    "en-AU": "英语（澳大利亚）",
    "ja-JP": "日语",
    "ko-KR": "韩语",
    "es-ES": "西班牙语（西班牙）",
    "es-MX": "西班牙语（墨西哥）",
    "es-419": "西班牙语（拉丁美洲）",
    "fr-FR": "法语（法国）",
    "fr-CA": "法语（加拿大）",
    "de-DE": "德语",
    "pl-PL": "波兰语",
    "fil-PH": "他加禄语 / 菲律宾语",
    "pt-BR": "葡萄牙语（巴西）",
    "pt-PT": "葡萄牙语（葡萄牙）",
    "ru-RU": "俄语",
    "it-IT": "意大利语",
    "th-TH": "泰语",
    "vi-VN": "越南语",
    "id-ID": "印尼语",
    "hi-IN": "印地语",
    "ar-EG": "阿拉伯语（埃及）",
    "ar-001": "阿拉伯语（世界）",
    "tr-TR": "土耳其语",
    "uk-UA": "乌克兰语",
    "nl-NL": "荷兰语",
    "sv-SE": "瑞典语",
    "da-DK": "丹麦语",
    "nb-NO": "挪威语（书面）",
    "nn-NO": "挪威语（新挪威）",
    "fi-FI": "芬兰语",
    "cs-CZ": "捷克语",
    "sk-SK": "斯洛伐克语",
    "ro-RO": "罗马尼亚语",
    "hu-HU": "匈牙利语",
    "el-GR": "希腊语",
    "he-IL": "希伯来语",
    "fa-IR": "波斯语",
    "ur-PK": "乌尔都语",
    "bn-BD": "孟加拉语",
    "ta-IN": "泰米尔语",
    "te-IN": "泰卢固语",
    "mr-IN": "马拉地语",
    "gu-IN": "古吉拉特语",
    "kn-IN": "卡纳达语",
    "ml-IN": "马拉雅拉姆语",
    "pa-IN": "旁遮普语",
    "or-IN": "奥里亚语",
    "mai-IN": "迈蒂利语",
    "kok-IN": "孔卡尼语",
    "sd-IN": "信德语",
    "ms-MY": "马来语",
    "jv-JV": "爪哇语",
    "ceb-PH": "宿务语",
    "my-MM": "缅甸语",
    "lo-LA": "老挝语",
    "km-KH": "高棉语 / 柬埔寨语",
    "sw-KE": "斯瓦希里语",
    "af-ZA": "南非荷兰语",
    "sq-AL": "阿尔巴尼亚语",
    "am-ET": "阿姆哈拉语",
    "hy-AM": "亚美尼亚语",
    "az-AZ": "阿塞拜疆语",
    "eu-ES": "巴斯克语",
    "be-BY": "白俄罗斯语",
    "bg-BG": "保加利亚语",
    "ca-ES": "加泰罗尼亚语",
    "hr-HR": "克罗地亚语",
    "et-EE": "爱沙尼亚语",
    "gl-ES": "加利西亚语",
    "ka-GE": "格鲁吉亚语",
    "ht-HT": "海地克里奥尔语",
    "is-IS": "冰岛语",
    "la-VA": "拉丁语",
    "lv-LV": "拉脱维亚语",
    "lt-LT": "立陶宛语",
    "lb-LU": "卢森堡语",
    "mk-MK": "马其顿语",
    "mg-MG": "马达加斯加语",
    "mn-MN": "蒙古语",
    "ne-NP": "尼泊尔语",
    "ps-AF": "普什图语",
    "sr-RS": "塞尔维亚语",
    "si-LK": "僧伽罗语",
    "sl-SI": "斯洛文尼亚语",
}

VOICE_AGES = {
    "young": "青年（清亮、冲劲、偏快）",
    "adult": "壮年（沉稳、有压迫感）",
    "elder": "老年（低哑、阅历、字句更短）",
}


def parse_line(raw) -> dict:
    if isinstance(raw, dict):
        text = str(raw.get("text") or "").strip()
        emotion = str(raw.get("emotion") or "").strip()
        tag = str(raw.get("tag") or "").strip()
    else:
        text = str(raw or "").strip()
        emotion, tag = "", ""
    return {"text": text, "emotion": emotion, "tag": tag}


def line_text(lines: dict | None, line_id: str) -> str:
    return parse_line((lines or {}).get(line_id)).get("text") or ""


def normalize_voice(raw: dict | None, *, has_transform: bool = False) -> dict:
    data = raw or {}
    if "lines" not in data and isinstance(data.get("voice"), dict):
        data = data["voice"]
    gender = str(data.get("gender") or "male").strip().lower()
    if gender not in DEFAULT_TTS_VOICE:
        gender = "male"
    lines_in = data.get("lines") or {}
    if not lines_in.get("combo_up") and lines_in.get("combo"):
        lines_in = {**lines_in, "combo_up": lines_in.get("combo")}
    lines = {}
    for slot in VOICE_LINES:
        item = parse_line(lines_in.get(slot["id"]))
        if slot["id"] == "transform" and not has_transform:
            item = {"text": "", "emotion": "", "tag": ""}
        else:
            perf = LINE_PERFORMANCE.get(slot["id"]) or {}
            if item["text"] and not item["emotion"]:
                item["emotion"] = perf.get("emotion") or ""
            if item["text"] and not item["tag"]:
                item["tag"] = perf.get("tag") or ""
        lines[slot["id"]] = item
    try:
        rate = min(1.25, max(0.7, float(data.get("speaking_rate", 1.0))))
    except (TypeError, ValueError):
        rate = 1.0
    try:
        pitch = min(8.0, max(-8.0, float(data.get("pitch", 0.0))))
    except (TypeError, ValueError):
        pitch = 0.0
    tts_voice = str(data.get("tts_voice") or DEFAULT_TTS_VOICE[gender]).strip()
    engine = str(data.get("tts_engine") or "").strip() or (
        "cloud" if tts_voice.startswith("cmn-") or tts_voice.startswith("yue-") else "gemini"
    )
    if engine == "gemini" and (tts_voice.startswith("cmn-") or tts_voice.startswith("yue-")):
        tts_voice = DEFAULT_TTS_VOICE[gender]
    model = str(data.get("tts_model") or "gemini-2.5-flash-tts").strip() or "gemini-2.5-flash-tts"
    clone_key = str(data.get("clone_key") or "").strip()
    clone_language = str(data.get("clone_language") or "cmn-CN").strip() or "cmn-CN"
    tts_language = str(data.get("tts_language") or "cmn-CN").strip() or "cmn-CN"
    if tts_language not in VOICE_LANGUAGES:
        tts_language = "cmn-CN"
    voice_age = str(data.get("voice_age") or "adult").strip() or "adult"
    if voice_age not in VOICE_AGES:
        voice_age = "adult"
    if engine == "clone" and not clone_key:
        engine = "gemini"
        tts_voice = DEFAULT_TTS_VOICE[gender]
    return {
        "persona": str(data.get("persona") or "").strip(),
        "gender": gender,
        "tts_engine": engine,
        "tts_model": model,
        "tts_voice": tts_voice,
        "tts_language": tts_language,
        "voice_age": voice_age,
        "speaking_rate": rate,
        "pitch": pitch,
        "clone_key": clone_key,
        "clone_language": clone_language,
        "clone_ready": bool(clone_key),
        "lines": lines,
    }


def slot_zh_fallback(slot: dict, note: str = "", fx_subject: str = "projectile") -> str:
    n = int(slot.get("frames") or 1)
    bits = [str(slot.get("title") or slot.get("id") or "")]
    if slot.get("hint"):
        bits.append(str(slot["hint"]))
    if n > 1:
        sid = str(slot.get("id") or "")
        if sid.startswith("fx_"):
            if fx_subject == "figure":
                bits.append(f"单行正好 {n} 个全身（含骑乘/体术），青屏，画英雄本人完成技能。")
            elif fx_subject == "clone":
                bits.append(f"单行正好 {n} 个分身/残影，青屏，同一英雄。")
            else:
                bits.append(f"单行正好 {n} 个弹道/特效帧，青屏，不要画人。")
        else:
            bits.append(f"单行正好 {n} 个全身，青屏，动作条朝右。")
    if note.strip():
        bits.append(f"已按意见修改：{note.strip()}")
    return "".join(bits) if len(bits) == 1 else " ".join(bits)


def fx_default_body(
    slot_id: str,
    kit: dict | None = None,
    display_name: str = "",
    fx_subject: str = "projectile",
) -> str:
    """Starter English body for re-wrapping an fx_* prompt when subject mode changes."""
    slot = SLOT_BY_ID.get(slot_id) or {}
    move_id = slot.get("move_id") or slot_id[3:]
    kit_line = str((kit or {}).get(move_id) or "").strip()
    who = (display_name or "").strip() or "this fighter"
    mode = fx_subject if fx_subject in FX_SUBJECT_MODES else "projectile"
    if mode == "figure":
        if kit_line:
            return (
                f"Four frames of {who} performing `{move_id}` — full body side profile facing RIGHT. "
                f"{kit_line}. Wind-up → peak → impact → follow-through."
            )
        return (
            f"Four frames of {who} performing a body-based special — full body side profile facing RIGHT."
        )
    if mode == "clone":
        if kit_line:
            return (
                f"Four frames of {who}'s `{move_id}` — shadow clones or afterimages, side profile facing RIGHT. "
                f"{kit_line}. Each frame shows a distinct clone position along the attack."
            )
        return f"Four frames of shadow clones / afterimages of {who}, side profile facing RIGHT."
    if kit_line:
        return f"Four frames of the projectile / VFX for: {kit_line}. Only the flying effect or impact core. No hero body."
    return "Four frames of one flying projectile or impact core. No hero body."


def enforce_strip_frame_count(text: str, n: int) -> str:
    """Rewrite stale 6-frame (or other wrong counts) leftovers so the model sees one number only."""
    t = (text or "").strip()
    n = max(1, int(n or 1))
    if not t or n < 2:
        return t
    # Old era default was 6; also scrub nearby wrong counts that conflict with HARD LAYOUT.
    wrong = [k for k in (6, 8, 10, 7) if k != n]
    for k in wrong:
        t = re.sub(rf"(?i)\b{k}\s+frames?\b", f"{n} frames", t)
        t = re.sub(rf"(?i)\bEXACTLY\s+{k}\b", f"EXACTLY {n}", t)
        t = re.sub(rf"(?i)\bexactly\s+{k}\b", f"exactly {n}", t)
        t = re.sub(rf"(?i)\b{k}\s+FULL-BODY\b", f"{n} FULL-BODY", t)
        t = re.sub(rf"(?i)\b{k}\s+poses?\b", f"{n} poses", t)
        t = re.sub(rf"(?i)\b{k}\s+figures?\b", f"{n} figures", t)
        t = re.sub(rf"(?i)\b{k}\s+keyframes?\b", f"{n} keyframes", t)
        t = re.sub(rf"{k}\s*帧", f"{n} 帧", t)
        t = re.sub(rf"1\s*[-–—]\s*{k}\b", f"1-{n}", t)
        t = re.sub(rf"(?i)\bframe\s*{k}\b", f"frame {n}", t)
        t = re.sub(rf"第\s*{k}\s*帧", f"第 {n} 帧", t)
    if n == 5:
        # Drop a leftover sixth beat: "6: returns to idle..."
        t = re.sub(r"(?i)(?:^|[.;\n])\s*6\s*[:：.]\s*[^.;\n]+", "", t)
        t = re.sub(r"(?i),\s*6\s*[:：.]\s*[^.;\n]+", "", t)
        t = re.sub(r"(?i)\band\s+6\s*[:：.]\s*[^.;\n]+", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def wrap_prompt(
    slot_id: str,
    body: str,
    visual_lock: str = "",
    developer_fix: str = "",
    kit: dict | None = None,
    display_name: str = "",
    has_ref_photo: bool = False,
    product_line: str | None = None,
    fx_subject: str = "projectile",
) -> str:
    line = normalize_product_line(product_line)
    slot = SLOT_BY_ID[slot_id]
    fx_mode = fx_subject if fx_subject in FX_SUBJECT_MODES else "projectile"
    if slot_id.startswith("fx_"):
        if fx_mode == "figure":
            parts = [FX_FIGURE_LOCK]
        elif fx_mode == "clone":
            parts = [FX_CLONE_LOCK]
        else:
            parts = [FX_LOCK]
    else:
        parts = [lock_for(slot["kind"], line)]
    if visual_lock and slot_id == "style":
        parts.append(f"STYLE LOCK (must match): {visual_lock}")
    elif visual_lock and slot_id.startswith("fx_"):
        move_id = slot.get("move_id") or slot_id[3:]
        kit_line = str((kit or {}).get(move_id) or "").strip()
        who = (display_name or "").strip() or "this fighter"
        if fx_mode == "projectile":
            theme = kit_line or "this hero's unique legendary attack, not a science prism or meteor"
            parts.append(
                f"THIS HERO ONLY: {who}. VFX must read as `{theme}`. "
                "Use THIS kit's weapons, faction, era, and motifs. "
                "FORBIDDEN unless the kit itself is about them: prism rainbows, apples, gravity wells, "
                "meteors, calculus, Newton's laws. NEVER draw the person. "
                f"Palette / silhouette cues (do not draw the body): {visual_lock}"
            )
        else:
            parts.append(f"CHARACTER LOCK (must match): {visual_lock}")
    elif visual_lock and slot_id != "stage":
        parts.append(f"CHARACTER LOCK (must match): {visual_lock}")
    if slot_id == "style":
        parts.append(DESKPET_STYLE_SHEET_NOTE if line == "deskpet" else GAME_STYLE_SHEET_NOTE)
    if slot_id.startswith("fx_"):
        n = int(slot.get("frames") or 4)
        move_id = slot.get("move_id") or slot_id[3:]
        if fx_mode == "figure":
            parts.append(
                f"BODY / MOUNTED VFX STRIP for move `{move_id}`. "
                f"ONE horizontal ROW, EXACTLY {n} DIFFERENT full-body figures of THIS hero performing the skill. "
                "Side-view profile facing RIGHT. Include mount/steed if the kit describes riding. "
                "Match the attached turnaround exactly: same face, costume, palette, outline, props, body size. "
                "FORBIDDEN: stage, floor, detached projectile-only frames with no body. "
                f"{FX_FIGURE_STRIP_SEPARATION} "
                "Frame-to-frame is wind-up → peak → impact → recover — readable at thumbnail size."
            )
        elif fx_mode == "clone":
            parts.append(
                f"CLONE / AFTERIMAGE STRIP for move `{move_id}`. "
                f"ONE horizontal ROW, EXACTLY {n} DIFFERENT clone or afterimage copies of THIS hero. "
                "Side-view profile facing RIGHT. Same costume as turnaround; copies may be semi-transparent or tinted. "
                "Match the attached turnaround exactly. "
                "FORBIDDEN: stage, floor, unrelated projectiles with no clone body. "
                f"{FX_CLONE_STRIP_SEPARATION} "
                "Frame-to-frame shifts the clone trail along the attack path."
            )
        else:
            parts.append(
                f"PROJECTILE / VFX STRIP for move `{move_id}`. "
                f"ONE horizontal ROW, EXACTLY {n} DIFFERENT frames of the SAME flying effect. "
                "Draw only the projectile or impact core. "
                "FORBIDDEN: fighter silhouette, face, wig, robe, legs, hands holding props, stage, floor. "
                f"{FX_STRIP_SEPARATION} "
                "Frame-to-frame is travel / spin / pulse — readable at thumbnail size."
            )
    if slot_id == "turnaround":
        stance = "Same neutral standing pose" if line == "deskpet" else "Same fight-ready stance"
        subject = "character" if line == "deskpet" else "hero"
        dummy_forbid = (
            "Dummy plate-armor / white-hair mage / green archer style-sheet characters are FORBIDDEN. "
            if line != "deskpet"
            else "Dummy fighting-game style-sheet characters (armor brawler / white-hair mage / green archer) are FORBIDDEN. "
        )
        if has_ref_photo:
            parts.append(
                "A likeness REFERENCE PHOTO is attached FIRST. "
                f"This {subject} must be recognizable as that person (face, age, hair, build). "
                "Still invent a PIXEL-ART turnaround — never paste the photo. "
                "Costume and silhouette follow CHARACTER LOCK / the brief. "
                f"There is NO house-style sheet to copy. {dummy_forbid}"
                "Exactly 4 equal-width cells in ONE ROW: 1 front, 2 three-quarter, 3 right-side, 4 back. "
                f"Same body scale; each view centered. {stance}. "
                f"{STRIP_SEPARATION} "
                "FORBIDDEN: photoreal output, three different people, dummy style-sheet characters, "
                "a second row of busts, 5 views, 2x5 contact sheet. "
                f"Count: exactly 4 FULL-BODY figures of the SAME {subject}. "
                "No stage, no floor, no scenery. Solid #00FFFF only."
            )
        else:
            invent = (
                "Invent this desk pet / standing character from CHARACTER LOCK only. "
                if line == "deskpet"
                else "NO character photo is attached. Invent this fighter from CHARACTER LOCK only. "
            )
            parts.append(
                f"{invent}"
                "There is NO house-style image to copy. "
                + (
                    "If you remember a cyan sheet of fighting-game dummies — those are FORBIDDEN. "
                    if line == "deskpet"
                    else "If you remember a cyan sheet of a plate-armor dummy, a white-hair mage, and a green archer — those are FORBIDDEN. "
                )
                + f"This sheet is FOUR VIEWS OF ONE NEW PERSON matching CHARACTER LOCK. "
                "Exactly 4 equal-width cells in ONE ROW: 1 front, 2 three-quarter, 3 right-side, 4 back. "
                f"Same body scale; each view centered. {stance}. "
                f"{STRIP_SEPARATION} "
                "FORBIDDEN: three different people, dummy style-sheet characters, a second row of busts, "
                "5 views, 2x5 contact sheet. "
                f"Count: exactly 4 FULL-BODY figures of the SAME {subject}. "
                "No stage, no floor, no scenery. Solid #00FFFF only."
            )
        parts.append(SLOT_BEATS["turnaround"])
        if line == "deskpet":
            parts.append(PORTRAIT_CHROMA_SAFE)
    if slot["kind"] == "sprite" and slot_id not in {"turnaround", "style"} and not slot_id.startswith("fx_"):
        if line == "deskpet":
            parts.append(
                "IDENTITY LOCK: Match the attached turnaround EXACTLY — same face, hair, ears, "
                "costume, bag/scarf/props, outline, palette, and body proportions. "
                "Only the pose changes. FORBIDDEN: redesign, new outfit, palette swap, cousin lookalike. "
                "Side-view profile facing RIGHT in every frame. Nose to the RIGHT. Not left. Not 3/4. Not front."
            )
            parts.append(PORTRAIT_CHROMA_SAFE)
        else:
            parts.append(
                "Match the attached turnaround exactly: same face, costume, palette, "
                "outline, props, and body size. Side-view profile facing RIGHT in every frame. "
                "Nose points to the RIGHT edge. Not left. Not 3/4. Not front. Do not rotate the camera."
            )
        n = int(slot.get("frames") or 5)
        style_note = (
            "If a house-style sheet is attached AFTER the turnaround, it is PIXEL LANGUAGE only — "
            "do not copy those sample mascots, and do not change this character's face or costume."
            if line == "deskpet"
            else "If a house-style sheet is attached AFTER the turnaround, it is PIXEL LANGUAGE only — "
            "do not copy those dummy fighters, and do not change this hero's face or costume."
        )
        parts.append(
            f"HARD LAYOUT: ONE horizontal ROW, EXACTLY {n} FULL-BODY figures, no more no less. "
            f"FORBIDDEN: 2 rows, 2x4, 2x5, 8 figures, 10 figures, bust/head row, extra clones, contact sheet. "
            f"If you count the people and it is not {n}, the image is unusable. "
            f"FLIPBOOK: those {n} cells will be cropped onto ONE equal canvas sized to the WIDEST pose. "
            "A lying / fully-extended pose must be drawn COMPLETE — extra cell width is required, "
            "not a cropped slice of a standing-width box. "
            "Onion-skin: same body-center X on standing poses. Do not pan the figure across the strip. "
            "Looping ground clips keep the same feet Y and body scale. "
            "Air and knockdown clips may change feet Y / body height. "
            "CONTINUITY: adjacent frames are in-betweens of ONE action. Limbs travel on ARCS. "
            "Never five copies of the same mid-pose. "
            "ACTING: each silhouette must be obviously different at thumbnail size — "
            "change BOTH legs, torso lean, AND hands/props. Frozen body + tiny wiggle = fail. "
            "The flipbook canvas will be sized to the WIDEST pose; draw complete silhouettes. "
            f"{STRIP_SEPARATION} "
            f"{style_note} "
            "No stage, no map, no floor texture."
        )
        if slot_id in LOOP_SLOTS:
            parts.append(f"LOOP: frame {n} must blend back into frame 1.")
        elif slot_id in FALL_SLOTS:
            parts.append(
                f"ONE-SHOT FALL: frame {n} is DOWN/still. Do NOT loop back to a standing or flying idle."
            )
        else:
            parts.append(
                f"ONE complete action: frame {n} recovers toward ready or landing — "
                "do not loop the attack itself."
            )
        if slot_id in AIR_ACTING_SLOTS:
            parts.append(
                "AIRBORNE ACTING: feet OFF the ground except the landing frame if any. "
                "Feet Y may change. Do not pan the body across the strip. "
                "No floor, no shadow, no stage. Solid #00FFFF only."
            )
        elif slot_id in FALL_SLOTS:
            parts.append(
                f"KNOCKDOWN ACTING: the body DROPS. Frame 1 is hit, frame {n} is down. "
                "Hip stays in the cell on standing frames; the down pose may lie fully horizontal "
                "and MUST be drawn complete in a wider cell. Do not stand back up."
            )
        else:
            parts.append(
                "GROUND ACTING: feet on one shared baseline. Same feet Y, same hip X, same body scale."
            )
        beat = SLOT_BEATS.get(slot_id)
        if beat:
            parts.append(beat)
        else:
            parts.append(
                "Numbered poses. Each frame is the in-between of the previous and next. "
                "Do not draw six copies of one pose."
            )
        if slot_id in {
            "skill",
            "combo_up",
            "combo_down",
            "super",
            "attack",
            "air_attack",
            "attack_up",
            "attack_down",
        }:
            parts.append(
                "FX / particles: opaque pixel clumps in red, orange, gold, white, or magenta only. "
                "NEVER cyan, aqua, teal, or turquoise — that is the chroma-key screen and will be deleted. "
                "Each spark has a 1px dark outline. NO glow halo, NO mist filling the cell, "
                "NO anti-alias blending into #00FFFF. Leave solid cyan gaps between sparks."
            )
    if slot_id == "stage":
        parts.append(
            "Empty ultra-wide 21:9 SIDE-VIEW arena: zero characters. "
            "Landmark near center, playable space on both left and right. "
            "Walkable floor and walkable ledges share ONE fighting plane — like KoF / Bleach vs Naruto. "
            "Raised terrain is a SIDE FACE + thin top cap at the same depth as the floor, "
            "not a 3/4 cluster of pillars sitting further back. "
            "Never draw solid color overlay blocks. "
            "If a style sheet is attached, match pixel density and outline language of the game, "
            "not the dummy fighters. If another stage is attached, match craft quality and horizon language, "
            "but this must be a DIFFERENT location."
        )
    if slot["kind"] == "cg":
        extra = {
            "opening_cg": "INTRO: 4 keyframes of the fighter entering battle, identity first.",
            "defeat_cg": "DEFEAT: 4 keyframes of losing — hit, break, collapse, still.",
            "win_cg": "VICTORY: 4 keyframes of winning — finish, pose, dominance, hold.",
        }.get(slot_id, "")
        parts.append(
            "Exactly 4 DIFFERENT cinematic keyframes in one horizontal strip. "
            "Keep the attached character design exactly. " + extra
        )
    n_expect = int(slot.get("frames") or (4 if slot_id == "turnaround" else 5))
    if slot["kind"] == "sprite" and slot_id != "style" and n_expect > 1:
        body = enforce_strip_frame_count(body, n_expect)
    parts.append((body or "").strip())
    if slot["kind"] == "sprite" and slot_id != "style":
        n = n_expect
        if slot_id.startswith("fx_"):
            if fx_mode == "figure":
                parts.append(
                    f"FINAL CHECK: EXACTLY {n} FULL-BODY figures of THIS hero performing the skill in ONE row on unbroken #00FFFF. "
                    "Side profile facing RIGHT. No black panel borders. Adjacent frames show different phases of ONE action."
                )
            elif fx_mode == "clone":
                parts.append(
                    f"FINAL CHECK: EXACTLY {n} clone/afterimage copies of THIS hero in ONE row on unbroken #00FFFF. "
                    "Side profile facing RIGHT. No black panel borders. Each frame shifts the clone trail."
                )
            else:
                parts.append(
                    f"FINAL CHECK: EXACTLY {n} projectile/VFX frames in ONE row on unbroken #00FFFF. "
                    "No fighter body. No black panel borders or divider bars. "
                    "Adjacent frames show travel of the same effect."
                )
        else:
            if slot_id in LOOP_SLOTS:
                end_note = f"Play it as a looping flipbook: frame {n} blends into frame 1."
            elif slot_id in FALL_SLOTS:
                end_note = f"Play it as a one-shot fall: frame {n} stays down. Do not loop to standing."
            elif slot_id == "turnaround":
                end_note = "Four inspection views of the same ready stance, not an attack cycle."
            else:
                end_note = (
                    f"Play it as ONE complete action: frame {n} recovers to ready or landing. "
                    "Do not loop the strike itself."
                )
            parts.append(
                f"FINAL CHECK before drawing: count the FULL-BODY people. There must be EXACTLY {n} "
                f"in ONE horizontal row. Do NOT invent an extra person beyond {n}. "
                f"If you would draw a 2x5 contact sheet, a bust row, or extra clones, "
                f"stop and draw {n} instead. Adjacent silhouettes must differ at thumbnail size. "
                f"{STRIP_SEPARATION} "
                f"{end_note} Limbs move on arcs, not teleport."
            )
    if developer_fix.strip():
        parts.append(
            "DEVELOPER FIX — MANDATORY, higher priority than the draft above. "
            f"The previous sheet failed because: {developer_fix.strip()}. "
            "Change the posing and layout to fix THIS. Do not repeat the old prompt."
        )
    return "\n\n".join(p for p in parts if p)


STAGE_TERRAIN_HINTS = {
    "flat": "通铺平地：格斗地板从左到右连续，不要画缺口，不要画可站立高台。collision 只有一条地面。",
    "platforms": "必须画出同一侧视图层上的台阶/高台（竖直墙面+顶边），禁止 3/4 透视把高台画到背景里。collision.platforms 对齐顶边。",
    "pits": "画面必须画出约一人物身高、有底的壕沟（干涸河床/塌陷庭院），玩家一眼能读；collision 用更低 floors 对齐沟底，pits=[]。禁止只改碰撞、画面仍是平地。",
    "mixed": "必须同时画出高台和可站立深凹地，都在同一格斗平面上；碰撞贴合所画地形，不是空气墙。",
    "auto": "按地点自己决定：宫廷广场类用平地；桥、悬崖、陵墓、屋顶战用高台/凹地。决定后 prompt、画面、collision 三者一致。禁止地形杀深渊。",
}


def _pct_label(value: float) -> str:
    return f"{int(round(max(0.0, min(1.0, value)) * 100))}%"


def collision_paint_hint(collision: dict | None) -> str:
    spec = collision if isinstance(collision, dict) else {}
    floors = spec.get("floors") or []
    platforms = spec.get("platforms") or []
    pits = spec.get("pits") or []
    lines = [
        "PAINT THIS TERRAIN INTO THE PIXEL SCENE as real architecture of this place.",
        "SIDE-VIEW SAME PLANE: every walkable top (floor and ledges) is on the fighting Z-plane.",
        "High ground = vertical side wall facing the fighting plane + a thin top the fighters stand on.",
        "FORBIDDEN: 3/4 bird's-eye tabletops, pillar clusters receding into the midground, "
        "a foreground floor with platforms parked behind it, solid color overlay slabs, HUD rectangles.",
    ]
    for i, box in enumerate(floors, 1):
        x = float(box.get("x") or 0)
        w = float(box.get("w") or 0)
        y = float(box.get("y") or 0.84)
        lines.append(
            f"Floor {i}: solid standing plane from {_pct_label(x)} to {_pct_label(x + w)} of image width, "
            f"top of the walkable surface about {_pct_label(y)} down from the top of the image."
        )
    for i, box in enumerate(platforms, 1):
        x = float(box.get("x") or 0)
        w = float(box.get("w") or 0)
        y = float(box.get("y") or 0.6)
        lines.append(
            f"High platform {i}: jumpable ledge from {_pct_label(x)} to {_pct_label(x + w)}, "
            f"top about {_pct_label(y)} down. Paint a SIDE-VIEW step/terrace in the SAME plane as the floor: "
            "a vertical cliff/wall in front, thin walkable cap on top, matching materials. "
            "Do NOT draw it as a 3D rock pile further back that fighters would walk in front of."
        )
    for i, box in enumerate(pits, 1):
        x = float(box.get("x") or 0)
        w = float(box.get("w") or 0)
        y = float(box.get("y") or 0.92)
        lines.append(
            f"Walkable ditch {i}: a DEEP LOWER trench from {_pct_label(x)} to {_pct_label(x + w)}, "
            f"floor top about {_pct_label(y)} down — roughly ONE FIGHTER TALL below the main ground. "
            "Paint a real sunken path/courtyard/dry riverbed with a solid bottom and tall side walls. "
            "Fighters drop in to duck horizontal fireballs, then jump back out. "
            "NOT a death pit, lava kill-zone, or bottomless abyss."
        )
    if not platforms and not pits:
        # also mention when only floors with height variety? keep simple
        lines.append(
            "This arena is a continuous courtyard: fighting floor runs edge-to-edge "
            "with NO gaps and NO raised ledges — unless multiple floors at different heights "
            "already listed above (main ground + lower ditch floors)."
        )
    return "\n".join(lines)


def with_stage_terrain_prompt(prompt: str, collision: dict | None) -> str:
    text = (prompt or "").strip()
    hint = collision_paint_hint(collision)
    marker = "PAINT THIS TERRAIN INTO THE PIXEL SCENE"
    if marker in text:
        start = text.find(marker)
        return (text[:start].rstrip() + "\n\n" + hint).strip()
    return f"{text}\n\n{hint}".strip() if text else hint


def _stage_bgm_palette(visual: str) -> str:
    """Map stage description to combat-leaning instrumentation; never cheerful pop."""
    text = (visual or "").lower()
    cn = visual or ""
    hints: list[str] = []

    def has(*keys: str) -> bool:
        return any(k.lower() in text or k in cn for k in keys)

    if has("neon", "cyber", "夜", "霓虹", "赛博", "未来", "都市", "city"):
        hints.append("dark synth bass, industrial percussion, cold arpeggios, distant sirens")
    if has("ruin", "废墟", "崩", "破败", "荒", "末日", "战争", "战场", "war"):
        hints.append("low brass drones, distorted war drums, grit and dust in the mix")
    if has("temple", "庙", "殿", "寺", "神社", "祭", "东方", "武侠", "江湖"):
        hints.append("deep taiko / ritual drums, sparse bamboo flute in minor mode, tense silence between hits")
    if has("castle", "宫", "殿堂", "皇", "中世纪", "castle", "fortress", "堡"):
        hints.append("ominous choir-free strings, pipe-organ stabs, heavy timpani")
    if has("lava", "火", "熔岩", "火山", "地狱", "炎"):
        hints.append("seething low drones, metallic hits, heat-haze pulse, no bright major fanfares")
    if has("ice", "雪", "冰", "寒", "冬"):
        hints.append("brittle high pads, sparse piano in minor, cold percussion, hollow space")
    if has("海", "水", "港", "船", "雨", "night", "暗", "阴"):
        hints.append("sub-bass pressure, muffled pulse, wet ambience under a stern rhythm")
    if has("sci-fi", "科幻", "机甲", "太空", "space", "实验室"):
        hints.append("mechanical ostinato, analog grit, tension risers without celebratory drops")
    if not hints:
        hints.append(
            "hybrid orchestra + dark electronic pulse: low strings, muted brass, tight combat drums"
        )
    return "; ".join(hints[:3])


def stage_bgm_prompt(display_name: str, visual: str, *, bpm: int = 118) -> str:
    name = (display_name or "对战舞台").strip()
    scene = (visual or name).strip()
    tempo = max(90, min(160, int(bpm or 118)))
    palette = _stage_bgm_palette(scene)
    return (
        f"Instrumental only. No vocals, no lyrics, no choir singing words, no spoken voice.\n"
        f"30-second seamless VERSUS fighting-game stage loop for 「{name}」 — "
        f"the music of an active duel, not a victory parade or adventure overworld.\n"
        f"Stage description (color the arrangement, do NOT make it cheerful): {scene}\n"
        f"Instrumentation palette: {palette}.\n"
        f"Genre: dark cinematic fighter / arena combat underscore "
        f"(Street Fighter / Tekken / Guilty Gear vibe: pressure, grit, immersion).\n"
        f"Harmony: prefer minor / modal / tense intervals; sustained low drones under a driving mid-tempo groove.\n"
        f"Melody: short motif or rhythmic hook only — no catchy cheerful lead, no playful whistle, no bright pop earworm.\n"
        f"Tempo around {tempo} BPM. Heavy and focused; intro locks in within 1–2 bars; "
        f"end on a loop-friendly downbeat with no fade-out cliff.\n"
        f"Mood keywords: tense, confrontational, immersive, weighty, determined.\n"
        f"Hard avoid: upbeat pop, happy major fanfare, cute chiptune bounce, festival EDM, "
        f"comedy/cartoon scoring, soft lo-fi chill, triumphant victory theme, long ambient silence.\n"
        f"Production: 44.1kHz stereo, game-ready mid-forward mix, controlled low end, "
        f"moderate compression, no dead air at start or end."
    )
