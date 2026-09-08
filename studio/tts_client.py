"""Google Cloud Text-to-Speech via Application Default Credentials."""

from __future__ import annotations

import base64
import html
import json
import re
import urllib.error
import urllib.request
from functools import lru_cache

from google.cloud import texttospeech

from prompts import LINE_PERFORMANCE, VOICE_AGES, VOICE_LANGUAGES, VOICE_LINES, parse_line

# Gemini-TTS 官方支持的语言主标签（BCP-47 一级）。高棉语 km 不在列。
# 见 https://docs.cloud.google.com/text-to-speech/docs/gemini-tts
GEMINI_TTS_LANG_TAGS = frozenset(
    {
        "af",
        "sq",
        "am",
        "ar",
        "hy",
        "az",
        "eu",
        "be",
        "bn",
        "bg",
        "my",
        "ca",
        "ceb",
        "zh",
        "cmn",
        "hr",
        "cs",
        "da",
        "nl",
        "en",
        "et",
        "fil",
        "fi",
        "fr",
        "gl",
        "ka",
        "de",
        "el",
        "gu",
        "ht",
        "he",
        "hi",
        "hu",
        "is",
        "id",
        "it",
        "ja",
        "jv",
        "kn",
        "ko",
        "kok",
        "lo",
        "la",
        "lv",
        "lt",
        "lb",
        "mk",
        "mg",
        "ms",
        "ml",
        "mr",
        "mn",
        "ne",
        "nb",
        "nn",
        "or",
        "ps",
        "fa",
        "pl",
        "pt",
        "pa",
        "ro",
        "ru",
        "sr",
        "sd",
        "si",
        "sk",
        "sl",
        "es",
        "sw",
        "sv",
        "ta",
        "te",
        "th",
        "tr",
        "uk",
        "ur",
        "vi",
        "yue",
    }
)

# Google Cloud TTS 目前没有合成音色的语言（选了会直接失败，需录音克隆或换语种）
TTS_UNSUPPORTED_LANGS = frozenset({"km-KH", "km"})

FALLBACK_VOICES = [
    {"name": "cmn-CN-Wavenet-A", "gender": "FEMALE", "ssml_gender": "FEMALE"},
    {"name": "cmn-CN-Wavenet-B", "gender": "MALE", "ssml_gender": "MALE"},
    {"name": "cmn-CN-Wavenet-C", "gender": "MALE", "ssml_gender": "MALE"},
    {"name": "cmn-CN-Wavenet-D", "gender": "FEMALE", "ssml_gender": "FEMALE"},
    {"name": "cmn-CN-Neural2-A", "gender": "FEMALE", "ssml_gender": "FEMALE"},
    {"name": "cmn-CN-Neural2-B", "gender": "MALE", "ssml_gender": "MALE"},
    {"name": "cmn-CN-Neural2-C", "gender": "MALE", "ssml_gender": "MALE"},
    {"name": "cmn-TW-Wavenet-A", "gender": "FEMALE", "ssml_gender": "FEMALE"},
    {"name": "cmn-TW-Wavenet-B", "gender": "MALE", "ssml_gender": "MALE"},
    {"name": "cmn-TW-Wavenet-C", "gender": "FEMALE", "ssml_gender": "FEMALE"},
]

GEMINI_VOICES = [
    # 官方 30 个预置声线（Cloud / Gemini TTS 文档）
    {"name": "Achernar", "gender": "female", "label": "Gemini · Achernar 女（柔）"},
    {"name": "Achird", "gender": "male", "label": "Gemini · Achird 男（友）"},
    {"name": "Algenib", "gender": "male", "label": "Gemini · Algenib 男（沙哑）"},
    {"name": "Algieba", "gender": "male", "label": "Gemini · Algieba 男（滑）"},
    {"name": "Alnilam", "gender": "male", "label": "Gemini · Alnilam 男（硬）"},
    {"name": "Aoede", "gender": "female", "label": "Gemini · Aoede 女（亮）"},
    {"name": "Autonoe", "gender": "female", "label": "Gemini · Autonoe 女（亮）"},
    {"name": "Callirrhoe", "gender": "female", "label": "Gemini · Callirrhoe 女（轻松）"},
    {"name": "Charon", "gender": "male", "label": "Gemini · Charon 男（沉、能压）"},
    {"name": "Despina", "gender": "female", "label": "Gemini · Despina 女（滑）"},
    {"name": "Enceladus", "gender": "male", "label": "Gemini · Enceladus 男（气声）"},
    {"name": "Erinome", "gender": "female", "label": "Gemini · Erinome 女（清）"},
    {"name": "Fenrir", "gender": "male", "label": "Gemini · Fenrir 男（狠）"},
    {"name": "Gacrux", "gender": "female", "label": "Gemini · Gacrux 女（成熟）"},
    {"name": "Iapetus", "gender": "male", "label": "Gemini · Iapetus 男（清）"},
    {"name": "Kore", "gender": "female", "label": "Gemini · Kore 女（硬）"},
    {"name": "Laomedeia", "gender": "female", "label": "Gemini · Laomedeia 女（跳）"},
    {"name": "Leda", "gender": "female", "label": "Gemini · Leda 女（年轻）"},
    {"name": "Orus", "gender": "male", "label": "Gemini · Orus 男（硬）"},
    {"name": "Pulcherrima", "gender": "female", "label": "Gemini · Pulcherrima 女（前倾）"},
    {"name": "Puck", "gender": "male", "label": "Gemini · Puck 男（跳）"},
    {"name": "Rasalgethi", "gender": "male", "label": "Gemini · Rasalgethi 男（陈述）"},
    {"name": "Sadachbia", "gender": "male", "label": "Gemini · Sadachbia 男（活）"},
    {"name": "Sadaltager", "gender": "male", "label": "Gemini · Sadaltager 男（知性）"},
    {"name": "Schedar", "gender": "male", "label": "Gemini · Schedar 男（稳）"},
    {"name": "Sulafat", "gender": "female", "label": "Gemini · Sulafat 女（暖）"},
    {"name": "Umbriel", "gender": "male", "label": "Gemini · Umbriel 男（轻松）"},
    {"name": "Vindemiatrix", "gender": "female", "label": "Gemini · Vindemiatrix 女（柔）"},
    {"name": "Zephyr", "gender": "female", "label": "Gemini · Zephyr 女（亮）"},
    {"name": "Zubenelgenubi", "gender": "male", "label": "Gemini · Zubenelgenubi 男（随意）"},
]

GEMINI_MODELS = [
    {"id": "gemini-2.5-flash-tts", "label": "Gemini 2.5 Flash TTS"},
    {"id": "gemini-3.1-flash-tts-preview", "label": "Gemini 3.1 Flash TTS（情绪标签更强）"},
    {"id": "gemini-2.5-pro-tts", "label": "Gemini 2.5 Pro TTS"},
]

GEMINI_VOICE_NAMES = {v["name"] for v in GEMINI_VOICES}
_GENDER_ZH = {"MALE": "男", "FEMALE": "女", "NEUTRAL": "中性", "male": "男", "female": "女", "neutral": "中性"}


def _label(name: str, gender: str) -> str:
    if name.startswith("cmn-CN"):
        lang = "普通话"
    elif name.startswith("cmn-TW"):
        lang = "台湾国语"
    elif name.startswith("yue"):
        lang = "粤语"
    else:
        lang = name.split("-")[0]
    if "Chirp3" in name:
        tier = "Chirp3 HD"
    elif "Studio" in name:
        tier = "Studio"
    elif "Neural2" in name:
        tier = "Neural2"
    elif "Wavenet" in name:
        tier = "WaveNet"
    elif "Standard" in name:
        tier = "Standard"
    else:
        tier = "TTS"
    short = name.split("-")[-1]
    sex = _GENDER_ZH.get(gender.upper(), _GENDER_ZH.get(gender, ""))
    return " · ".join(part for part in (lang, f"{tier} {short}", sex) if part) + "（朗读）"


def _lang_tag(code: str) -> str:
    return (code or "").strip().split("-", 1)[0].lower()


def gemini_supports_language(code: str) -> bool:
    if not code:
        return False
    if code in TTS_UNSUPPORTED_LANGS or _lang_tag(code) in TTS_UNSUPPORTED_LANGS:
        return False
    tag = _lang_tag(code)
    # yue-HK / cmn-CN：Gemini 文档写 cmn / 部分预览；按主标签判断
    if tag in {"cmn", "zh", "yue"}:
        return "cmn" in GEMINI_TTS_LANG_TAGS or "yue" in GEMINI_TTS_LANG_TAGS
    return tag in GEMINI_TTS_LANG_TAGS


@lru_cache(maxsize=8)
def cloud_language_codes(project: str = "") -> frozenset[str]:
    try:
        client = _client(project)
        resp = client.list_voices()
    except Exception:
        return frozenset()
    codes: set[str] = set()
    for voice in resp.voices:
        for code in voice.language_codes or []:
            if code:
                codes.add(code)
    return frozenset(codes)


def _cloud_has_language(code: str, project: str = "") -> bool:
    catalog = cloud_language_codes(project)
    if not catalog:
        return False
    if code in catalog:
        return True
    tag = _lang_tag(code)
    return any(_lang_tag(c) == tag for c in catalog)


def tts_language_supported(code: str, *, project: str = "") -> dict:
    """Return {gemini, cloud, ok, detail} for UI / synthesize guards."""
    code = (code or "cmn-CN").strip() or "cmn-CN"
    label = VOICE_LANGUAGES.get(code, code)
    if code in TTS_UNSUPPORTED_LANGS or _lang_tag(code) == "km":
        return {
            "gemini": False,
            "cloud": False,
            "ok": False,
            "detail": (
                f"Google TTS 暂不支持「{label}」（{code}）合成："
                "Gemini-TTS 与 Cloud 朗读均无此语言音色。"
                "可用「录音克隆」上传高棉语样本，或先用泰语 th-TH / 越南语 vi-VN 试听邻近语种。"
            ),
        }
    gemini_ok = gemini_supports_language(code)
    cloud_ok = _cloud_has_language(code, project)
    if gemini_ok or cloud_ok:
        return {"gemini": gemini_ok, "cloud": cloud_ok, "ok": True, "detail": ""}
    return {
        "gemini": False,
        "cloud": False,
        "ok": False,
        "detail": f"当前项目下列不出「{label}」（{code}）的可用音色。可换语种或用录音克隆。",
    }


@lru_cache(maxsize=64)
def cloud_voices_for_language(language_code: str, project: str = "") -> tuple[dict, ...]:
    language_code = (language_code or "").strip()
    if not language_code:
        return ()
    if not _cloud_has_language(language_code, project):
        return ()
    try:
        client = _client(project)
        resp = client.list_voices(language_code=language_code)
    except Exception:
        return ()
    out: list[dict] = []
    seen: set[str] = set()
    for voice in resp.voices:
        name = voice.name or ""
        if not name or name in seen:
            continue
        if "-" not in name:
            continue
        seen.add(name)
        gender = getattr(voice.ssml_gender, "name", None) or str(voice.ssml_gender or "NEUTRAL")
        out.append(_voice_dict(name, gender))
    rank = {"Chirp3": 0, "Studio": 1, "Neural2": 2, "Wavenet": 3, "Standard": 4}
    out.sort(key=lambda v: (min((r for k, r in rank.items() if k in v["name"]), default=5), v["name"]))
    return tuple(out)


def pick_cloud_voice(language_code: str, gender: str = "", project: str = "") -> str:
    voices = cloud_voices_for_language(language_code, project=project)
    if not voices:
        tag = _lang_tag(language_code)
        for code in sorted(cloud_language_codes(project)):
            if _lang_tag(code) == tag:
                voices = cloud_voices_for_language(code, project=project)
                if voices:
                    break
    if not voices:
        return ""
    want = (gender or "").lower()
    if want in {"male", "female"}:
        for v in voices:
            if v.get("gender") == want:
                return v["name"]
    return voices[0]["name"]


def _language_code(voice_name: str) -> str:
    if voice_name in GEMINI_VOICE_NAMES:
        return "cmn-CN"
    parts = voice_name.split("-")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return "cmn-CN"


def _client(project: str = "") -> texttospeech.TextToSpeechClient:
    # REST avoids gRPC's local sidecar (127.0.0.1) which fails with
    # "Operation not permitted" under some process sandboxes.
    options = {"quota_project_id": project} if project else None
    kwargs: dict = {"transport": "rest"}
    if options:
        kwargs["client_options"] = options
    return texttospeech.TextToSpeechClient(**kwargs)


def _voice_dict(name: str, gender: str, *, engine: str = "cloud", label: str = "") -> dict:
    gender_key = (gender or "NEUTRAL").upper()
    return {
        "name": name,
        "gender": gender_key.lower(),
        "language": _language_code(name),
        "engine": engine,
        "label": label or _label(name, gender_key),
    }


@lru_cache(maxsize=8)
def list_voices(project: str = "") -> list[dict]:
    client = _client(project)
    voices: list[dict] = []
    seen: set[str] = set()
    # Cloud 朗读声线：中文系 + 常用外语（Gemini 声线另列）
    for lang in (
        "cmn-CN",
        "cmn-TW",
        "yue-HK",
        "en-US",
        "en-GB",
        "ja-JP",
        "ko-KR",
        "es-ES",
        "fr-FR",
        "de-DE",
        "pl-PL",
        "fil-PH",
        "pt-BR",
        "ru-RU",
        "it-IT",
        "th-TH",
        "vi-VN",
        "id-ID",
        "hi-IN",
        "ar-EG",
    ):
        try:
            resp = client.list_voices(language_code=lang)
        except Exception:
            continue
        for voice in resp.voices:
            name = voice.name or ""
            if not name or name in seen:
                continue
            seen.add(name)
            gender = getattr(voice.ssml_gender, "name", None) or str(voice.ssml_gender or "NEUTRAL")
            voices.append(_voice_dict(name, gender))
    rank = {"Chirp3": 0, "Studio": 1, "Neural2": 2, "Wavenet": 3, "Standard": 4}
    voices.sort(key=lambda v: (min((r for k, r in rank.items() if k in v["name"]), default=5), v["name"]))
    return voices


# Common search aliases (CJK / English / native) beyond id + Chinese label.
_LANGUAGE_ALIASES: dict[str, list[str]] = {
    "cmn-CN": ["mandarin", "chinese", "中文", "国语", "普通话", "简体"],
    "cmn-TW": ["mandarin", "taiwan", "台语", "繁体", "国语"],
    "yue-HK": ["cantonese", "广东话", "廣東話", "粤语", "粵語", "hongkong"],
    "en-US": ["english", "美式", "american"],
    "en-GB": ["english", "英式", "british", "uk"],
    "en-IN": ["english", "india", "印度英语"],
    "en-AU": ["english", "australia", "澳式"],
    "ja-JP": ["japanese", "日文", "にほんご"],
    "ko-KR": ["korean", "韩文", "韓文", "한국어"],
    "es-ES": ["spanish", "español", "西班牙"],
    "es-MX": ["spanish", "mexico", "墨西哥"],
    "es-419": ["spanish", "latin", "拉美"],
    "fr-FR": ["french", "français", "法文"],
    "fr-CA": ["french", "canada", "魁北克"],
    "de-DE": ["german", "deutsch", "德文"],
    "pl-PL": ["polish", "polski", "波兰"],
    "fil-PH": ["tagalog", "filipino", "他加禄", "菲律宾"],
    "pt-BR": ["portuguese", "brazil", "巴西", "葡萄牙"],
    "pt-PT": ["portuguese", "portugal", "葡萄牙"],
    "ru-RU": ["russian", "русский", "俄文"],
    "it-IT": ["italian", "italiano", "意大利"],
    "th-TH": ["thai", "ไทย", "泰文"],
    "vi-VN": ["vietnamese", "tiếng việt", "越南"],
    "id-ID": ["indonesian", "bahasa", "印尼"],
    "hi-IN": ["hindi", "हिन्दी", "印地"],
    "ar-EG": ["arabic", "العربية", "阿拉伯", "埃及"],
    "ar-001": ["arabic", "العربية", "阿拉伯"],
    "tr-TR": ["turkish", "türkçe", "土耳其"],
    "uk-UA": ["ukrainian", "українська", "乌克兰"],
    "nl-NL": ["dutch", "nederlands", "荷兰"],
    "km-KH": ["khmer", "cambodian", "cambodia", "高棉", "柬埔寨", "ខ្មែរ", "km"],
    "my-MM": ["burmese", "myanmar", "缅甸", "မြန်မာ"],
    "lo-LA": ["lao", "老挝", "寮", "ລາວ"],
    "ms-MY": ["malay", "马来"],
    "bn-BD": ["bengali", "bangla", "孟加拉"],
    "he-IL": ["hebrew", "希伯来", "עברית"],
    "fa-IR": ["persian", "farsi", "波斯", "فارسی"],
    "ur-PK": ["urdu", "乌尔都", "اردو"],
    "sw-KE": ["swahili", "斯瓦希里"],
    "jv-JV": ["javanese", "爪哇"],
    "ceb-PH": ["cebuano", "宿务"],
}


def available_languages(project: str = "") -> list[dict]:
    out = []
    for code, label in VOICE_LANGUAGES.items():
        aliases = list(_LANGUAGE_ALIASES.get(code, []))
        # Always searchable by bare language subtag (e.g. km from km-KH).
        sub = code.split("-", 1)[0]
        if sub and sub.lower() not in {a.lower() for a in aliases}:
            aliases.append(sub)
        support = tts_language_supported(code, project=project)
        mark = ""
        if not support["ok"]:
            mark = " · 不可用"
        elif support["gemini"]:
            mark = " · Gemini"
        elif support["cloud"]:
            mark = " · 仅 Cloud"
        out.append(
            {
                "id": code,
                "label": label,
                "aliases": aliases,
                "gemini": bool(support["gemini"]),
                "cloud": bool(support["cloud"]),
                "ok": bool(support["ok"]),
                "detail": support.get("detail") or "",
                "display": f"{label} · {code}{mark}",
            }
        )
    return out


def available_voices(project: str = "") -> list[dict]:
    gemini = [
        _voice_dict(v["name"], v["gender"], engine="gemini", label=v["label"]) for v in GEMINI_VOICES
    ]
    try:
        cloud = list_voices(project)
        if not cloud:
            cloud = [_voice_dict(v["name"], v["gender"]) for v in FALLBACK_VOICES]
    except Exception:
        list_voices.cache_clear()
        cloud = [_voice_dict(v["name"], v["gender"]) for v in FALLBACK_VOICES]
    return gemini + cloud


def _strip_tags(text: str) -> str:
    return re.sub(r"^(?:\[[^\]]+\]\s*)+", "", text or "").strip()


def tagged_text(text: str, tag: str = "", line_id: str = "") -> str:
    body = _strip_tags(text)
    tag = (tag or (LINE_PERFORMANCE.get(line_id) or {}).get("tag") or "").strip()
    if tag and not tag.startswith("["):
        tag = f"[{tag}]"
    if tag:
        return f"{tag} {body}"
    return body


def style_prompt(
    *,
    display_name: str = "",
    persona: str = "",
    line_id: str = "",
    emotion: str = "",
    gender: str = "",
    tts_language: str = "cmn-CN",
    voice_age: str = "adult",
) -> str:
    title = next((s["title"] for s in VOICE_LINES if s["id"] == line_id), line_id or "line")
    emotion = emotion or (LINE_PERFORMANCE.get(line_id) or {}).get("emotion") or "in character, committed"
    who = display_name or "this historical fighter"
    lang_label = VOICE_LANGUAGES.get(tts_language, tts_language)
    age_label = VOICE_AGES.get(voice_age, voice_age)
    return (
        f"Perform a fighting-game battle shout in {lang_label}. "
        f"You ARE {who}. Do not narrate. Do not announce the emotion. "
        f"Persona: {persona or gender or 'a legendary warrior'}. "
        f"Speaker age: {age_label}. "
        f"This is the '{title}' line. "
        f"Emotional delivery: {emotion}. "
        f"Sound like a 2D arena fighter, not a newsreader, audiobook, or customer-service bot. "
        f"Commit. Vary pitch, bite consonants, use breath. Keep it short and punchy."
    )


def _ssml(text: str, line_id: str, speaking_rate: float, pitch: float) -> str:
    body = html.escape(_strip_tags(text))
    rate_pct = int(speaking_rate * 100)
    pitch_st = f"{pitch:+.0f}st"
    emphasis = {
        "attack": "strong",
        "skill": "strong",
        "combo": "strong",
        "combo_up": "strong",
        "combo_down": "strong",
        "super": "strong",
        "hurt": "moderate",
        "transform": "strong",
        "win": "moderate",
        "defeat": "reduced",
        "intro": "moderate",
        "select": "moderate",
    }.get(line_id, "moderate")
    return (
        f'<speak><prosody rate="{rate_pct}%" pitch="{pitch_st}">'
        f'<emphasis level="{emphasis}">{body}</emphasis>'
        f"</prosody></speak>"
    )


def _is_gemini(engine: str, voice_name: str, model_name: str) -> bool:
    if engine in {"cloud", "clone"}:
        return False
    if engine == "gemini" or model_name.startswith("gemini-"):
        return True
    return voice_name in GEMINI_VOICE_NAMES


CONSENT_SCRIPTS = {
    "cmn-CN": "我是此声音的拥有者并授权谷歌使用此声音创建语音合成模型",
    "en-US": "I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model.",
}

CLONE_KEY_URL = "https://texttospeech.googleapis.com/v1beta1/voices:generateVoiceCloningKey"


def consent_script(language_code: str = "cmn-CN") -> str:
    return CONSENT_SCRIPTS.get(language_code) or CONSENT_SCRIPTS["cmn-CN"]


def audio_encoding_for(filename: str = "", content_type: str = "") -> str:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    blob = f"{name} {ctype}"
    if "wav" in blob or "wave" in blob or "linear" in blob:
        return "LINEAR16"
    if "mp3" in blob or "mpeg" in blob:
        return "MP3"
    if "m4a" in blob or "mp4" in blob or "aac" in blob:
        return "MP4"
    return "LINEAR16"


def linear16_payload(data: bytes) -> bytes:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        i = 12
        while i + 8 <= len(data):
            chunk = data[i : i + 4]
            size = int.from_bytes(data[i + 4 : i + 8], "little")
            i += 8
            if chunk == b"data":
                return data[i : i + size]
            i += size + (size % 2)
    return data


def _clone_error_message(status: int, body: str) -> str:
    low = body.lower()
    if status in {404, 403} or "not allowed" in low or "allowlist" in low or "not enabled" in low:
        return (
            "当前 GCP 项目未开通 Chirp 3 Instant Custom Voice（需 allowlist）。"
            "可继续用 Gemini-TTS。原始错误：" + body[:240]
        )
    if "consent" in low:
        return "授权口播未通过。请用同一人、同一环境，一字不差地朗读授权文案后再传。原始错误：" + body[:240]
    if "SERVICE_DISABLED" in body or "has not been used" in body:
        return "Cloud Text-to-Speech API 未开通。请运行：gcloud services enable texttospeech.googleapis.com"
    return f"采集声线失败（HTTP {status}）：{body[:320]}"


def generate_clone_key(
    reference: bytes,
    consent: bytes,
    *,
    language_code: str = "cmn-CN",
    reference_encoding: str = "LINEAR16",
    consent_encoding: str = "LINEAR16",
    project: str = "",
) -> str:
    if not reference or not consent:
        raise ValueError("需要音色样本和授权口播两段录音。")
    if len(reference) < 8000 or len(consent) < 4000:
        raise ValueError("录音太短。音色样本建议约 10 秒，授权口播把整句念完。")
    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise RuntimeError("缺少 google-auth，无法调用克隆声线接口。") from exc

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not creds.valid:
        creds.refresh(Request())
    if not getattr(creds, "token", None):
        creds.refresh(Request())

    ref_bytes = linear16_payload(reference) if reference_encoding == "LINEAR16" else reference
    consent_bytes = linear16_payload(consent) if consent_encoding == "LINEAR16" else consent
    payload = {
        "reference_audio": {
            "audio_config": {"audio_encoding": reference_encoding},
            "content": base64.b64encode(ref_bytes).decode("ascii"),
        },
        "voice_talent_consent": {
            "audio_config": {"audio_encoding": consent_encoding},
            "content": base64.b64encode(consent_bytes).decode("ascii"),
        },
        "consent_script": consent_script(language_code),
        "language_code": language_code or "cmn-CN",
    }
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    if project:
        headers["x-goog-user-project"] = project
    req = urllib.request.Request(
        CLONE_KEY_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(_clone_error_message(exc.code, err_body)) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"采集声线失败：{exc}") from exc
    key = str(data.get("voiceCloningKey") or data.get("voice_cloning_key") or "").strip()
    if not key:
        raise RuntimeError("接口没有返回声线密钥。")
    return key


def synthesize(
    text: str,
    *,
    voice_name: str,
    speaking_rate: float = 1.0,
    pitch: float = 0.0,
    project: str = "",
    engine: str = "",
    model_name: str = "",
    prompt: str = "",
    emotion: str = "",
    tag: str = "",
    line_id: str = "",
    persona: str = "",
    display_name: str = "",
    gender: str = "",
    clone_key: str = "",
    clone_language: str = "cmn-CN",
    tts_language: str = "cmn-CN",
    voice_age: str = "adult",
) -> bytes:
    text = (text or "").strip()
    if not text:
        raise ValueError("台词是空的。")
    if len(_strip_tags(text)) > 80:
        raise ValueError("台词太长，格斗喊招请控制在 80 字内。")
    client = _client(project)
    use_clone = engine == "clone"
    if use_clone:
        if not clone_key:
            raise ValueError("还没有采集声线。请先上传或录制音色样本。")
        try:
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=clone_language or "cmn-CN",
                    voice_clone=texttospeech.VoiceCloneParams(voice_cloning_key=clone_key),
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=min(1.25, max(0.7, speaking_rate)),
                ),
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "SERVICE_DISABLED" in msg or "has not been used" in msg:
                raise RuntimeError(
                    "Cloud Text-to-Speech API 未开通。请运行：gcloud services enable texttospeech.googleapis.com"
                ) from exc
            raise RuntimeError(f"克隆声线合成失败：{exc}") from exc
        if not response.audio_content:
            raise RuntimeError("TTS 没有返回音频。")
        return response.audio_content
    use_gemini = _is_gemini(engine, voice_name, model_name)
    lang = (tts_language or "").strip() or "cmn-CN"
    support = tts_language_supported(lang, project=project)
    if not support["ok"]:
        raise ValueError(support["detail"] or f"不支持语言 {lang}")
    # Gemini 不支持该语种时，自动改用 Cloud 朗读（若有音色）
    if use_gemini and not support["gemini"]:
        if support["cloud"]:
            fallback = pick_cloud_voice(lang, gender=gender, project=project)
            if not fallback:
                raise ValueError(support["detail"] or f"不支持语言 {lang}")
            use_gemini = False
            voice_name = fallback
            engine = "cloud"
        else:
            raise ValueError(
                f"Gemini-TTS 不支持「{VOICE_LANGUAGES.get(lang, lang)}」（{lang}）。"
                + (support["detail"] or "请改用 Cloud 朗读或录音克隆。")
            )
    try:
        if use_gemini:
            model = model_name or "gemini-2.5-flash-tts"
            spoken = tagged_text(text, tag, line_id)
            style = prompt or style_prompt(
                display_name=display_name,
                persona=persona,
                line_id=line_id,
                emotion=emotion,
                gender=gender,
                tts_language=lang,
                voice_age=voice_age or "adult",
            )
            kwargs = {
                "input": texttospeech.SynthesisInput(text=spoken, prompt=style),
                "voice": texttospeech.VoiceSelectionParams(
                    language_code=lang,
                    name=voice_name if voice_name in GEMINI_VOICE_NAMES else "Charon",
                    model_name=model,
                ),
                "audio_config": texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3),
            }
            response = client.synthesize_speech(**kwargs)
        else:
            cloud_lang = _language_code(voice_name)
            # 外语台词 + 中文 Cloud 声线会念错；优先按所选语言换同性别 Cloud 音色
            if lang and cloud_lang.split("-")[0].lower() != _lang_tag(lang):
                alt = pick_cloud_voice(lang, gender=gender, project=project)
                if alt:
                    voice_name = alt
                    cloud_lang = _language_code(voice_name) or lang
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(ssml=_ssml(text, line_id, speaking_rate, pitch)),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=cloud_lang or lang,
                    name=voice_name,
                ),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=min(1.25, max(0.7, speaking_rate)),
                    pitch=min(8.0, max(-8.0, pitch)),
                ),
            )
    except ValueError:
        raise
    except Exception as exc:
        msg = str(exc)
        if "SERVICE_DISABLED" in msg or "has not been used" in msg or "disabled" in msg.lower():
            raise RuntimeError(
                "Cloud Text-to-Speech API 未开通。请运行：gcloud services enable texttospeech.googleapis.com"
            ) from exc
        if "language code" in msg.lower() and "not supported" in msg.lower():
            raise RuntimeError(
                f"当前引擎不支持语言 {lang}。"
                "Gemini-TTS 语种有限；高棉语等需录音克隆或换有音色的语种。"
                f" 原始错误：{exc}"
            ) from exc
        if use_gemini and ("model" in msg.lower() or "not found" in msg.lower() or "invalid" in msg.lower()):
            raise RuntimeError(
                f"Gemini-TTS 模型不可用（{model_name or 'gemini-2.5-flash-tts'}）。"
                "可改选 Gemini 2.5 Flash TTS，或确认项目已开通 Cloud TTS。"
                f" 原始错误：{exc}"
            ) from exc
        raise RuntimeError(f"TTS 失败：{exc}") from exc
    if not response.audio_content:
        raise RuntimeError("TTS 没有返回音频。")
    return response.audio_content


def probe_tts(project: str = "") -> dict:
    try:
        voices = list_voices(project)
        return {
            "ok": True,
            "detail": f"Cloud TTS 可用 · Gemini-TTS 演戏 + {len(voices)} 条朗读声线",
        }
    except Exception as exc:  # noqa: BLE001
        list_voices.cache_clear()
        return {
            "ok": False,
            "detail": f"{exc}。若未开通请运行 gcloud services enable texttospeech.googleapis.com",
        }
