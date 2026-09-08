"""Procedural UI / fight SFX as WAV (no extra deps)."""

from __future__ import annotations

import math
import random
import struct
import wave
from io import BytesIO
from pathlib import Path

SAMPLE_RATE = 44100


def _fade(samples: list[float], attack: float = 0.004, release: float = 0.02) -> list[float]:
    n = len(samples)
    if n < 2:
        return samples
    a = min(n // 2, max(1, int(SAMPLE_RATE * attack)))
    r = min(n // 2, max(1, int(SAMPLE_RATE * release)))
    out = samples[:]
    for i in range(a):
        out[i] *= i / a
    for i in range(r):
        out[n - 1 - i] *= i / r
    return out


def _sine(freq: float, duration: float, amp: float = 0.5) -> list[float]:
    n = max(1, int(SAMPLE_RATE * duration))
    return [amp * math.sin(2 * math.pi * freq * t / SAMPLE_RATE) for t in range(n)]


def _noise(duration: float, amp: float = 0.25) -> list[float]:
    n = max(1, int(SAMPLE_RATE * duration))
    return [amp * (random.random() * 2 - 1) for _ in range(n)]


def _lowpass(samples: list[float], cutoff: float = 1400.0) -> list[float]:
    if not samples:
        return samples
    rc = 1.0 / (2.0 * math.pi * max(40.0, cutoff))
    dt = 1.0 / SAMPLE_RATE
    a = dt / (rc + dt)
    y = 0.0
    out = []
    for x in samples:
        y += a * (x - y)
        out.append(y)
    return out


def _band_noise(duration: float, amp: float = 0.4, low: float = 180.0, high: float = 1600.0) -> list[float]:
    raw = _noise(duration, amp)
    hi = _lowpass(raw, high)
    lo = _lowpass(hi, low)
    return [a - b for a, b in zip(hi, lo)]


def _highpass(samples: list[float], cutoff: float = 400.0) -> list[float]:
    if not samples:
        return samples
    rc = 1.0 / (2.0 * math.pi * max(40.0, cutoff))
    dt = 1.0 / SAMPLE_RATE
    a = rc / (rc + dt)
    y = 0.0
    prev = samples[0]
    out = []
    for x in samples:
        y = a * (y + x - prev)
        prev = x
        out.append(y)
    return out


def _exp_decay(samples: list[float], tau: float = 0.04) -> list[float]:
    if not samples:
        return samples
    out = []
    for i, x in enumerate(samples):
        out.append(x * math.exp(-i / max(1.0, SAMPLE_RATE * tau)))
    return out


def _pad(track: list[float], offset: int) -> list[float]:
    return [0.0] * max(0, offset) + track


def _mix(*tracks: list[float], gain: float = 1.0, peak: float = 0.92) -> list[float]:
    length = max(len(t) for t in tracks) if tracks else 0
    out = [0.0] * length
    for track in tracks:
        for i, v in enumerate(track):
            out[i] += v
    loud = max(abs(x) for x in out) or 1.0
    scale = min(1.0, peak / loud) * gain
    return [x * scale for x in out]


def _to_wav_bytes(samples: list[float]) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", int(max(-32767, min(32767, round(s * 32767))))) for s in samples
        )
        wf.writeframes(frames)
    return buf.getvalue()


def synth_click() -> bytes:
    thump = _fade(_sine(200, 0.055, 0.72), attack=0.001, release=0.028)
    tap = _fade(_mix(_sine(1100, 0.024, 0.38), _noise(0.016, 0.22)), attack=0.0005, release=0.014)
    body = _mix(thump, tap + [0.0] * max(0, len(thump) - len(tap)), gain=1.05)
    return _to_wav_bytes(_fade(body[: max(len(thump), len(tap))], release=0.012))


def synth_click_firm() -> bytes:
    thump = _fade(_sine(110, 0.075, 0.82), attack=0.001, release=0.035)
    tick = _fade(
        _mix(_sine(620, 0.028, 0.42), _sine(1240, 0.02, 0.28), _noise(0.012, 0.18)),
        attack=0.0003,
        release=0.018,
    )
    body = _mix(thump, tick + [0.0] * max(0, len(thump) - len(tick)), gain=1.08)
    return _to_wav_bytes(_fade(body[: max(len(thump), len(tick))], release=0.02))


def synth_map_draw_tick() -> bytes:
    ping = _fade(
        _mix(_sine(720, 0.038, 0.55), _sine(1440, 0.022, 0.22), _noise(0.01, 0.12)),
        attack=0.0005,
        release=0.025,
    )
    return _to_wav_bytes(ping)


def synth_map_draw_pick() -> bytes:
    parts: list[list[float]] = []
    for i, (freq, dur, amp) in enumerate(
        [(392, 0.1, 0.42), (523, 0.1, 0.44), (659, 0.12, 0.46), (784, 0.22, 0.48)]
    ):
        offset = int(SAMPLE_RATE * 0.05 * i)
        tone = _fade(_sine(freq, dur, amp), attack=0.002, release=0.07)
        parts.append([0.0] * offset + tone)
    length = max(len(p) for p in parts)
    merged = [0.0] * length
    for p in parts:
        for i, v in enumerate(p):
            merged[i] += v
    hit = _fade(_mix(_sine(98, 0.08, 0.45), _noise(0.025, 0.15)), release=0.05)
    merged = _mix(merged, hit + [0.0] * max(0, len(merged) - len(hit)), gain=1.05)
    return _to_wav_bytes(_fade(merged, release=0.12))


def synth_count_tick() -> bytes:
    ping = _mix(
        _sine(880, 0.11, 0.42),
        _sine(1760, 0.08, 0.12),
        _noise(0.018, 0.04),
    )
    return _to_wav_bytes(_fade(ping, attack=0.001, release=0.05))


def synth_count_go() -> bytes:
    parts = []
    for i, freq in enumerate((523.25, 659.25, 783.99, 1046.5)):
        offset = int(SAMPLE_RATE * 0.045 * i)
        tone = _fade(_sine(freq, 0.16, 0.38 - i * 0.04), attack=0.002, release=0.08)
        pad = [0.0] * offset + tone
        parts.append(pad)
    length = max(len(p) for p in parts)
    merged = [0.0] * length
    for p in parts:
        for i, v in enumerate(p):
            merged[i] += v
    hit = _fade(_mix(_sine(130.81, 0.12, 0.35), _noise(0.04, 0.08)), release=0.06)
    merged = _mix(merged, hit + [0.0] * max(0, len(merged) - len(hit)))
    return _to_wav_bytes(_fade(merged, release=0.09))


def synth_result_win() -> bytes:
    melody = [
        (523.25, 0.14),
        (659.25, 0.14),
        (783.99, 0.14),
        (1046.5, 0.22),
        (783.99, 0.1),
        (1046.5, 0.34),
    ]
    parts: list[list[float]] = []
    cursor = 0
    for freq, dur in melody:
        tone = _fade(_sine(freq, dur, 0.36), attack=0.003, release=0.07)
        parts.append([0.0] * cursor + tone)
        cursor += int(SAMPLE_RATE * dur * 0.82)
    length = max(len(p) for p in parts)
    merged = [0.0] * length
    for p in parts:
        for i, v in enumerate(p):
            merged[i] += v
    brass = _fade(_sine(261.63, length / SAMPLE_RATE, 0.12), release=0.2)
    merged = _mix(merged, brass[: len(merged)])
    return _to_wav_bytes(_fade(merged, release=0.15))


def synth_result_lose() -> bytes:
    notes = [(440, 0.22), (349.23, 0.24), (293.66, 0.34)]
    parts: list[list[float]] = []
    cursor = 0
    for freq, dur in notes:
        tone = _fade(_sine(freq, dur, 0.34), attack=0.004, release=0.09)
        parts.append([0.0] * cursor + tone)
        cursor += int(SAMPLE_RATE * dur * 0.9)
    length = max(len(p) for p in parts)
    merged = [0.0] * length
    for p in parts:
        for i, v in enumerate(p):
            merged[i] += v
    return _to_wav_bytes(_fade(merged, release=0.18))


def _chirp(f0: float, f1: float, duration: float, amp: float = 0.5) -> list[float]:
    n = max(1, int(SAMPLE_RATE * duration))
    out = []
    phase = 0.0
    for t in range(n):
        p = t / max(1, n - 1)
        freq = f0 * ((f1 / max(1.0, f0)) ** p)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        out.append(amp * math.sin(phase))
    return out


def _soft_clip(samples: list[float], drive: float = 1.55) -> list[float]:
    """轻饱和：加谐波厚度，避免空心正弦感。"""
    return [math.tanh(x * drive) for x in samples]


def _hard_cut(samples: list[float], seconds: float, release: float = 0.012) -> list[float]:
    cut = max(1, int(SAMPLE_RATE * seconds))
    return _fade(samples[:cut], attack=0.00005, release=release)


def _layer_top(*, wet: float = 1.0, bone: float = 0.55) -> list[float]:
    """高频：sharp skin slap / wet flesh whip / bone crack transient。"""
    # 极短湿皮肉拍（切肉感）
    whip = _highpass(_band_noise(0.018, 1.25 * wet, 900, 7000), 1200)
    whip = _fade(whip, attack=0.00005, release=0.01)
    whip = _exp_decay(whip, 0.012)
    # 第二下“啪”微延迟，模拟皮肉回弹
    slap2 = _pad(
        _fade(_highpass(_band_noise(0.012, 0.7 * wet, 700, 5000), 900), attack=0.00005, release=0.008),
        int(SAMPLE_RATE * 0.006),
    )
    crack = _fade(
        _mix(
            _sine(2100, 0.008, 0.45 * bone),
            _sine(3800, 0.005, 0.22 * bone),
            _highpass(_noise(0.008, 0.55 * bone), 2000),
        ),
        attack=0.00004,
        release=0.006,
    )
    return _mix(whip, slap2, crack, peak=0.99)


def _layer_mid(*, body: float = 1.0) -> list[float]:
    """中频：leather punch / wet sandbag — 肉感实体。"""
    # 湿沙袋闷击：中低频噪声实体
    bag = _band_noise(0.07, 1.1 * body, 70, 900)
    bag = _fade(bag, attack=0.0002, release=0.04)
    bag = _exp_decay(bag, 0.045)
    # 皮革/衣物撞击
    leather = _band_noise(0.04, 0.85 * body, 200, 1600)
    leather = _fade(leather, attack=0.00015, release=0.025)
    leather = _exp_decay(leather, 0.028)
    # 实体“咚”心
    punch = _fade(_sine(155, 0.055, 0.75 * body), attack=0.0003, release=0.035)
    punch = _exp_decay(punch, 0.04)
    thump = _fade(_sine(95, 0.07, 0.55 * body), attack=0.0005, release=0.045)
    return _mix(bag, leather, punch, thump, peak=0.99)


def _layer_sub(*, f0: float = 36.0, amp: float = 1.0, dur: float = 0.14) -> list[float]:
    """低频：cinematic sub-bass thud — 耳机发抖的那一下。"""
    # 硬起音瞬态（不是软 fade-in，否则像木头空响）
    fund = _sine(f0, dur, amp)
    fund = _fade(fund, attack=0.0002, release=dur * 0.45)
    fund = _exp_decay(fund, dur * 0.42)
    # 二次谐波给厚度，避免纯正弦空心
    harm = _sine(f0 * 2.05, dur * 0.7, amp * 0.38)
    harm = _fade(harm, attack=0.0003, release=dur * 0.4)
    harm = _exp_decay(harm, dur * 0.38)
    # 次低频噪声冲击力
    boom_n = _lowpass(_noise(dur, amp * 0.85), 75)
    boom_n = _fade(boom_n, attack=0.0003, release=dur * 0.5)
    boom_n = _exp_decay(boom_n, dur * 0.4)
    # 开头 3ms 额外冲击尖峰
    click = _fade(_lowpass(_noise(0.004, amp * 1.1), 120), attack=0.00005, release=0.0025)
    return _mix(fund, harm, boom_n, click, peak=0.99)


def _layered_impact(*, wet: float, bone: float, mid: float, sub_f0: float, sub_amp: float, sub_dur: float, total: float) -> bytes:
    """三层叠加：Top 切肉 + Mid 沙袋肉感 + Sub 低频冲击，干声短截。"""
    top = _layer_top(wet=wet, bone=bone)
    mid_l = _layer_mid(body=mid)
    sub = _layer_sub(f0=sub_f0, amp=sub_amp, dur=sub_dur)
    stacked = _mix(top, mid_l, sub, peak=0.99)
    stacked = _soft_clip(stacked, drive=1.65)
    # 再抬一点开头瞬态
    n = min(len(stacked), int(SAMPLE_RATE * 0.004))
    for i in range(n):
        stacked[i] *= 1.0 + 0.55 * (1.0 - i / max(1, n))
    body = _hard_cut(stacked, total, release=0.01)
    return _to_wav_bytes(_mix(body, peak=0.98))


def synth_hit_light() -> bytes:
    """轻拳/轻腿：清脆切肉 + 短促肉感 + 紧凑 sub，约 0.12s。"""
    return _layered_impact(
        wet=1.05,
        bone=0.45,
        mid=0.85,
        sub_f0=42,
        sub_amp=0.95,
        sub_dur=0.1,
        total=0.12,
    )


def synth_hit_heavy() -> bytes:
    """重拳/重腿：湿皮肉 + 沙袋闷击 + 深 sub，约 0.18s，零混响拖尾。"""
    return _layered_impact(
        wet=1.15,
        bone=0.85,
        mid=1.15,
        sub_f0=28,
        sub_amp=1.15,
        sub_dur=0.16,
        total=0.18,
    )


def synth_hit_whoosh() -> bytes:
    """破空 + 三层命中（命中段同样短硬）。"""
    whoosh_noise = _fade(_band_noise(0.07, 0.55, 220, 5000), attack=0.003, release=0.035)
    whoosh_noise = _highpass(whoosh_noise, 300)
    whoosh_tone = _fade(_chirp(980, 140, 0.075, 0.34), attack=0.002, release=0.035)
    air = _mix(whoosh_noise, whoosh_tone, peak=0.7)
    delay = int(SAMPLE_RATE * 0.055)
    top = _layer_top(wet=1.1, bone=0.7)
    mid_l = _layer_mid(body=1.05)
    sub = _layer_sub(f0=32, amp=1.1, dur=0.14)
    hit = _soft_clip(_mix(top, mid_l, sub, peak=0.99), drive=1.65)
    n = min(len(hit), int(SAMPLE_RATE * 0.004))
    for i in range(n):
        hit[i] *= 1.0 + 0.55 * (1.0 - i / max(1, n))
    hit = _hard_cut(hit, 0.16, release=0.01)
    body = _mix(air, _pad(hit, delay), peak=0.98)
    return _to_wav_bytes(_hard_cut(body, 0.24, release=0.015))


def synth_hit_guard() -> bytes:
    """格挡：中频闷击 + 轻 sub，少切肉。"""
    mid_l = _layer_mid(body=0.7)
    sub = _layer_sub(f0=55, amp=0.55, dur=0.08)
    puff = _fade(_band_noise(0.04, 0.55, 400, 2200), attack=0.0003, release=0.025)
    body = _soft_clip(_mix(mid_l, sub, puff, peak=0.95), drive=1.3)
    return _to_wav_bytes(_hard_cut(body, 0.1, release=0.012))


UI_SFX_FILES = {
    "click": ("click.wav", synth_click),
    "click_firm": ("click_firm.wav", synth_click_firm),
    "map_draw_tick": ("map_draw_tick.wav", synth_map_draw_tick),
    "map_draw_pick": ("map_draw_pick.wav", synth_map_draw_pick),
    "count_tick": ("count_tick.wav", synth_count_tick),
    "count_go": ("count_go.wav", synth_count_go),
    "result_win": ("result_win.wav", synth_result_win),
    "result_lose": ("result_lose.wav", synth_result_lose),
    "hit_light": ("hit_light.wav", synth_hit_light),
    "hit_heavy": ("hit_heavy.wav", synth_hit_heavy),
    "hit_whoosh": ("hit_whoosh.wav", synth_hit_whoosh),
    "hit_guard": ("hit_guard.wav", synth_hit_guard),
}


def write_ui_sfx(out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for key, (name, fn) in UI_SFX_FILES.items():
        path = out_dir / name
        path.write_bytes(fn())
        written[key] = name
    return written
