# /// script
# dependencies = ["numpy"]
# ///
"""合成 Claude「回复完成」提示音。uv run sounds/make-chimes.py → .local/share/sounds/atelier/claude-done.wav
2026-10-07 从 A 玻璃双音 / B 三连琶音 / C 木琴轻敲 三个候选里选定 A。

设计要点(参考 Apple 系统提示音的做法):
- 音色:加法合成,少量非谐波泛音(像玻璃/木琴的敲击),高泛音衰减更快 → 起音亮、尾巴干净;
- 起音 2ms 淡入防爆音,整体 <1s,不拖沓;
- 音程上行 = 「完成/积极」的听感;最后一个音最长,收得住;
- 响度统一归一到 -1 dBFS 峰值,比 freedesktop complete.oga 明显。
"""
from pathlib import Path
import wave
import numpy as np

SR = 48000
OUT = Path(__file__).parent / ".local/share/sounds/atelier"

def strike(freq, dur, partials, decay):
    t = np.arange(int(SR * dur)) / SR
    y = np.zeros_like(t)
    for ratio, amp in partials:
        # 越高的泛音衰减越快,模拟敲击类乐器
        y += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t * decay * ratio ** 0.7)
    attack = np.minimum(t / 0.002, 1.0)
    return y * attack

GLASS = [(1, 1.0), (2.0, 0.35), (3.01, 0.12), (4.95, 0.05)]

def mix(notes, total):
    out = np.zeros(int(SR * total))
    for start, sig in notes:
        i = int(SR * start)
        out[i:i + len(sig)] += sig[: len(out) - i]
    # 一点点短混响:几路衰减延迟叠加,让声音有空间感而不干瘪
    wet = np.zeros_like(out)
    for d_ms, g in [(23, 0.18), (41, 0.12), (67, 0.08), (97, 0.05)]:
        d = int(SR * d_ms / 1000)
        wet[d:] += g * out[:-d]
    out = out + wet
    fade = int(SR * 0.04)
    out[-fade:] *= np.linspace(1, 0, fade)
    return out / np.max(np.abs(out)) * 10 ** (-1 / 20)

def write(name, y):
    OUT.mkdir(parents=True, exist_ok=True)
    pcm = (y * 32767).astype("<i2")
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())

N = lambda midi: 440 * 2 ** ((midi - 69) / 12)

# 玻璃双音:G5 → D6 纯五度上行,干净利落
write("claude-done", mix([(0, strike(N(79), 0.5, GLASS, 9)),
                          (0.11, strike(N(86), 0.8, GLASS, 6))], 0.95))
