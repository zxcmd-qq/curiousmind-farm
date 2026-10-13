"""Хайп-моушн поверх готового видео (стиль MrBeast/TikTok):
- заглавная плашка с темой в начале;
- плашки-стикеры с ключевыми числами/словами, вылетают в момент, когда диктор произносит слово,
  с лучами-вспышкой, отскоком и счётчиком чисел (0 -> 150);
- на каждом «ударе» — зум-панч, тряска камеры и белая вспышка;
- цветокор (контраст/насыщенность), виньетка, полоска прогресса сверху.

params.callouts = [{"text": "3 СЕРДЦА", "word": "сердца"}, ...]; время берём из пословного subtitle.srt.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
CANVAS_H = 760           # высота полосы с плашкой
TOP_Y = 170              # где полоса начинается (ниже интерфейса TikTok, выше субтитров)
DUR = 1.9                # сколько висит плашка
STYLES = [  # (плашка, текст)
    ("#FF8A00", "#FFFFFF"),
    ("#FF2D55", "#FFFFFF"),
    ("#0A84FF", "#FFFFFF"),
    ("#8B3DFF", "#FFFFFF"),
    ("#00B86B", "#FFFFFF"),
]


def _ffmpeg() -> str:
    try:
        from app.utils import utils
        return utils.get_ffmpeg_binary()
    except Exception:
        return shutil.which("ffmpeg") or "ffmpeg"


def _font_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for p in ("../../resource/fonts/bangerscyrillic.ttf", "../../resource/fonts/Impact Regular.ttf"):
        fp = os.path.normpath(os.path.join(here, p))
        if os.path.exists(fp):
            return fp
    return ""


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]", "", str(s).lower().replace("ё", "е"))


def parse_words(srt_path: str) -> list[tuple[float, float, str]]:
    out = []
    try:
        txt = open(srt_path, encoding="utf-8").read()
    except Exception:
        return out
    for m in re.finditer(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)\s*\n(.*?)(?:\n\s*\n|\Z)", txt, re.S):
        g = m.groups()
        a = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        b = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        for w in g[8].split():
            out.append((a, b, w))
    return out


def _times(callouts, words, total, start=0.8):
    res, last = [], start
    for i, c in enumerate(callouts):
        anchor = _norm(c.get("word") or c.get("text", "").split()[-1])[:5]
        t = None
        if anchor:
            for a, _, w in words:
                if a >= last and _norm(w).startswith(anchor):
                    t = a
                    break
        if t is None:
            t = max(last, total * (i + 1) / (len(callouts) + 1))
        if t > total - 1.2:
            continue
        res.append((max(0.0, t - 0.06), c))
        last = t + DUR + 0.3
    return res


# ------------------------------------------------------------------ графика
_FONTS: dict = {}


def _font(size):
    if size not in _FONTS:
        fp = _font_path()
        _FONTS[size] = ImageFont.truetype(fp, size) if fp else ImageFont.load_default()
    return _FONTS[size]


def _wrap(draw, text, font, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(text, maxw=820, big=165, small=80):
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    size = big
    while size > small:
        f = _font(size)
        lines = _wrap(tmp, text, f, maxw)
        if len(lines) <= 2 and max(tmp.textlength(l, font=f) for l in lines) <= maxw:
            return size, lines
        size -= 8
    return small, _wrap(tmp, text, _font(small), maxw)


def _sticker(text: str, style: int, size: int | None = None) -> Image.Image:
    plate, ink = STYLES[style % len(STYLES)]
    text = text.upper().replace("І", "I").replace("Ґ", "Г")
    if size is None:
        size, lines = _fit(text)
    else:
        tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        lines = _wrap(tmp, text, _font(size), 860)
    f = _font(size)
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    tw = int(max(d0.textlength(l, font=f) for l in lines))
    lh = int(size * 1.0)
    padx, pady = int(size * 0.32), int(size * 0.16)
    pw, ph = tw + padx * 2, lh * len(lines) + pady * 2
    sh, border = 16, 8
    img = Image.new("RGBA", (pw + sh + border * 2 + 4, ph + sh + border * 2 + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.22)
    # жёсткая тень-«стикер»
    d.rounded_rectangle((sh, sh, sh + pw + border * 2, sh + ph + border * 2), r + border, fill=(0, 0, 0, 200))
    # белая обводка
    d.rounded_rectangle((0, 0, pw + border * 2, ph + border * 2), r + border, fill="#FFFFFF")
    # плашка
    d.rounded_rectangle((border, border, border + pw, border + ph), r, fill=plate)
    # блик сверху (отдельным слоем, чтобы не «пробивать» плашку)
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle((border + 6, border + 6, border + pw - 6, border + int(ph * 0.42)), r, fill=(255, 255, 255, 45))
    img.alpha_composite(hl)
    for i, l in enumerate(lines):
        x = border + (pw - d.textlength(l, font=f)) / 2
        y = border + pady + i * lh - size * 0.06
        d.text((x, y), l, font=f, fill="#FFFFFF", stroke_width=max(4, size // 16), stroke_fill="#000000")
    return img


def _rays(frame: Image.Image, cx, cy, k: float, color: str):
    """Лучи-вспышка от центра: k=0..1 (растут и гаснут)."""
    if k <= 0 or k >= 1:
        return
    lay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    rgb = Image.new("RGB", (1, 1), color).getpixel((0, 0))
    a = int(230 * (1 - k))
    n = 16
    r0, r1 = 120 + 260 * k, 220 + 420 * k
    for i in range(n):
        ang = i * 2 * math.pi / n + 0.2
        w = 0.06
        p = [(cx + r0 * math.cos(ang - w), cy + r0 * math.sin(ang - w) * 0.75),
             (cx + r1 * math.cos(ang), cy + r1 * math.sin(ang) * 0.75),
             (cx + r0 * math.cos(ang + w), cy + r0 * math.sin(ang + w) * 0.75)]
        d.polygon(p, fill=(*rgb, a))
    frame.alpha_composite(lay)


def _count_text(text: str, k: float) -> str:
    """'150 ЛЕТ' при k<1 -> '87 ЛЕТ' (счётчик)."""
    m = re.match(r"^([-+]?)(\d[\d ]*)(.*)$", text.strip())
    if not m or k >= 1:
        return text
    num = int(m.group(2).replace(" ", ""))
    if num < 5:
        return text
    v = int(num * (1 - (1 - k) ** 3))
    return f"{m.group(1)}{v}{m.group(3)}"


def _ease_out_back(x):
    c1, c3 = 2.2, 3.2
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def _frames(text: str, idx: int, dur: float, size=None):
    n = int(dur * FPS)
    tilt = (-5, 4, -3, 5, -4)[idx % 5]
    plate = STYLES[idx % len(STYLES)][0]
    base = _sticker(text, idx, size)
    count_until = 0.5
    for f in range(n):
        t = f / FPS
        card = _sticker(_count_text(text, t / count_until), idx, size) if t < count_until else base
        if t < 0.22:                                  # SLAM: из огромного в нормальный с отскоком
            x = t / 0.22
            s = 1.7 - 0.7 * _ease_out_back(x)
            a = min(1.0, t / 0.06)
            rot = tilt + (1 - x) * 14 * (1 if idx % 2 else -1)
        elif t > dur - 0.16:                          # уход: схлопывание
            k = (t - (dur - 0.16)) / 0.16
            s, a, rot = 1 - 0.5 * k, 1 - k, tilt - 6 * k
        else:                                         # «дышит»
            s = 1 + 0.03 * math.sin((t - 0.22) * 8)
            a, rot = 1.0, tilt + 1.2 * math.sin((t - 0.22) * 6)
        im = card.resize((max(1, int(card.width * s)), max(1, int(card.height * s))), Image.BICUBIC)
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
        if a < 1:
            im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        fr = Image.new("RGBA", (W, CANVAS_H), (0, 0, 0, 0))
        _rays(fr, W / 2, CANVAS_H / 2, (t - 0.03) / 0.45, plate)
        fr.alpha_composite(im, ((W - im.width) // 2, (CANVAS_H - im.height) // 2))
        yield fr


def _render_clip(text: str, idx: int, out: str, dur: float = DUR, size=None) -> str:
    p = subprocess.Popen([_ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{CANVAS_H}",
                          "-r", str(FPS), "-i", "-", "-c:v", "qtrle", "-pix_fmt", "argb", out], stdin=subprocess.PIPE)
    for fr in _frames(text, idx, dur, size):
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()
    return out if p.returncode == 0 and os.path.exists(out) else ""


def _probe_duration(path: str) -> float:
    try:
        r = subprocess.run([_ffmpeg(), "-i", path], capture_output=True, text=True)
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        return 0.0


def _base_filter(hits: list[float], total: float) -> str:
    """Зум-панч + тряска + вспышка на каждом ударе, цветокор, виньетка."""
    if hits:
        pulse = "+".join(f"if(gte(t,{h:.3f}),exp(-(t-{h:.3f})/0.13),0)" for h in hits)
        shake = "+".join(f"if(between(t,{h:.3f},{h + 0.3:.3f}),exp(-(t-{h:.3f})/0.09),0)" for h in hits)
        flash = "+".join(f"if(between(t,{h:.3f},{h + 0.12:.3f}),1-(t-{h:.3f})/0.12,0)" for h in hits)
    else:
        pulse = shake = flash = "0"
    z = f"(1.045+0.13*({pulse}))"
    return (
        f"scale=w='trunc({W}*{z}/2)*2':h=-2:eval=frame,"
        f"crop={W}:{H}:x='(iw-{W})/2+16*sin(t*97)*({shake})':y='(ih-{H})/2+12*cos(t*83)*({shake})',"
        f"eq=contrast=1.07:saturation=1.22:brightness='0.22*({flash})':eval=frame,"
        f"vignette=angle=PI/5"
    )


def _font_clean(size):
    """Чистый жирный шрифт с кириллицей (для Reddit-карточки)."""
    here = os.path.dirname(os.path.abspath(__file__))
    key = ("clean", size)
    if key not in _FONTS:
        for fp in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
                   "/System/Library/Fonts/Supplemental/Arial Black.ttf",
                   os.path.normpath(os.path.join(here, "../../resource/fonts/MicrosoftYaHeiBold.ttc"))):
            if os.path.exists(fp):
                try:
                    _FONTS[key] = ImageFont.truetype(fp, size)
                    break
                except Exception:
                    pass
        else:
            _FONTS[key] = _font(size)
    return _FONTS[key]


# ------------------------------------------------------------------ Reddit-карточка
def _reddit_card(title: str, sub: str, style: str = "reddit") -> Image.Image:
    w = 960
    ft, fs = _font_clean(54), _font_clean(36)
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lines = _wrap(d0, title, ft, w - 80)[:5]
    h = 150 + len(lines) * 68 + 40
    pik = style == "pikabu"
    img = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((14, 14, w + 14, h + 14), 36, fill=(0, 0, 0, 150))
    if pik:   # светлая карточка Пикабу с зелёной полосой
        d.rounded_rectangle((0, 0, w, h), 36, fill="#FFFFFF", outline="#8AC858", width=4)
        d.ellipse((40, 36, 120, 116), fill="#8AC858")
        d.text((80, 76), "П", font=_font_clean(46), fill="#FFFFFF", anchor="mm")
        d.text((140, 46), "Пикабу" + (f" · @{sub}" if sub and sub != "pikabu" else ""), font=fs, fill="#111111")
        d.text((140, 88), "история из жизни", font=_font_clean(28), fill="#8A8A8A")
        ink = "#111111"
    else:
        d.rounded_rectangle((0, 0, w, h), 36, fill="#1A1A1B", outline="#343536", width=3)
        d.ellipse((40, 36, 120, 116), fill="#FF4500")
        d.text((80, 76), "r/", font=_font_clean(38), fill="#FFFFFF", anchor="mm")
        d.text((140, 46), f"r/{sub}" if sub else "Reddit", font=fs, fill="#FFFFFF")
        d.text((140, 88), "история с Reddit", font=_font_clean(28), fill="#9A9DA0")
        ink = "#FFFFFF"
    for i, l in enumerate(lines):
        d.text((40, 150 + i * 68), l, font=ft, fill=ink)
    return img


def _reddit_frames(title, sub, dur, style="reddit"):
    card = _reddit_card(title, sub, style)
    n = int(dur * FPS)
    for f in range(n):
        t = f / FPS
        if t < 0.35:
            k = _ease_out_back(t / 0.35)
            dy, a, s = int((1 - k) * 260), min(1, t / 0.15), 0.9 + 0.1 * k
        elif t > dur - 0.3:
            k = (t - (dur - 0.3)) / 0.3
            dy, a, s = int(-k * 120), 1 - k, 1.0
        else:
            dy, a, s = 0, 1.0, 1.0
        im = card.resize((int(card.width * s), int(card.height * s)), Image.BICUBIC) if s != 1 else card.copy()
        if a < 1:
            im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        fr = Image.new("RGBA", (W, CANVAS_H), (0, 0, 0, 0))
        fr.alpha_composite(im, ((W - im.width) // 2, max(0, (CANVAS_H - im.height) // 2 + dy)))
        yield fr


# ------------------------------------------------------------------ Квиз
QUIZ_H = 1000
QUIZ_Y = 160
OPT_COLORS = ["#FF8A00", "#0A84FF", "#8B3DFF"]
LETTERS = ["А", "Б", "В"]


def _opt_plate(text: str, i: int, state: str = "normal") -> Image.Image:
    """state: normal | right | wrong"""
    w, h = 760, 190
    color = {"right": "#00C853", "wrong": "#55575C"}.get(state, OPT_COLORS[i % 3])
    img = Image.new("RGBA", (w + 16, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((12, 12, w + 12, h + 12), 40, fill=(0, 0, 0, 170))
    d.rounded_rectangle((0, 0, w, h), 40, fill="#FFFFFF")
    d.rounded_rectangle((7, 7, w - 7, h - 7), 34, fill=color)
    d.ellipse((24, 30, 154, 160), fill="#FFFFFF")
    if state == "right":   # галочка рисуется линиями — не зависит от шрифта
        d.line([(55, 98), (80, 125), (125, 68)], fill=color, width=18, joint="curve")
    else:
        d.text((89, 98), LETTERS[i % 3], font=_font(90), fill=color, anchor="mm")
    size, lines = _fit(text.upper(), maxw=w - 210, big=78, small=40)
    f = _font(size)
    lh = int(size * 1.0)
    y0 = (h - lh * len(lines)) / 2 - size * 0.05
    for k, l in enumerate(lines):
        d.text((180, y0 + k * lh), l, font=f, fill="#FFFFFF", stroke_width=max(3, size // 16), stroke_fill="#000000")
    return img


def _timer(num: int, k: float, total_k: float = 0.0) -> Image.Image:
    """Секундомер: циферблат, красный сектор заполняется, стрелка бежит, в центре цифра.
    k — доля текущей секунды (0..1), total_k — доля всей паузы (0..1)."""
    sz = 270
    img = Image.new("RGBA", (sz, sz + 30), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, r = sz / 2, sz / 2 + 30, sz / 2 - 14
    d.rounded_rectangle((cx - 22, 0, cx + 22, 30), 6, fill="#FFFFFF")              # кнопка
    d.rounded_rectangle((cx - 34, 18, cx + 34, 36), 6, fill="#D0D0D0")
    d.ellipse((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10), fill="#111111")  # корпус
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill="#FFFFFF")                      # циферблат
    if total_k > 0:
        d.pieslice((cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8), -90, -90 + 360 * total_k, fill="#FF2D55")
    for i in range(12):                                                              # риски
        a = i * math.pi / 6
        r1, r2 = r - 6, r - (26 if i % 3 == 0 else 16)
        d.line((cx + r1 * math.sin(a), cy - r1 * math.cos(a), cx + r2 * math.sin(a), cy - r2 * math.cos(a)),
               fill="#111111", width=6 if i % 3 == 0 else 3)
    a = 2 * math.pi * total_k                                                        # стрелка
    d.line((cx, cy, cx + (r - 30) * math.sin(a), cy - (r - 30) * math.cos(a)), fill="#111111", width=8)
    d.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill="#111111")
    d.text((cx, cy + 4), str(num), font=_font(110), fill="#FFFFFF", anchor="mm", stroke_width=8, stroke_fill="#000000")
    s = 1.18 - 0.18 * min(1.0, _ease_out_back(min(1.0, k / 0.2)))                   # толчок на каждом «пик»
    return img.resize((int(img.width * s), int(img.height * s)), Image.BICUBIC)


def _quiz_plan(quiz: dict, words, total):
    opts = [str(o) for o in (quiz.get("options") or [])][:3]
    ans = int(quiz.get("answer", 0) or 0)
    t_opt, last = [], 1.5
    for o in opts:
        a = _norm(o.split()[0])[:5] if o.split() else ""
        t = next((w0 for w0, _, w in words if w0 >= last and a and _norm(w).startswith(a)), None)
        t = t if t is not None else last + 1.2
        t_opt.append(t)
        last = t + 0.3
    cd = []
    for key in ("три", "два", "один"):
        t = next((w0 for w0, _, w in words if w0 >= last and _norm(w).startswith(key)), None)
        if t is None:
            break
        cd.append(t)
        last = t + 0.3
    t_ans = next((w0 for w0, _, w in words if w0 >= last and _norm(w).startswith("ответ")), None)
    if len(cd) < 3:
        base = (t_ans or (last + 3.5)) - 3.2
        cd = [base, base + 1.0, base + 2.0]
    if t_ans is None:
        t_ans = cd[-1] + 1.0
    end = min(total - 0.1, t_ans + 3.0)
    return opts, ans, t_opt, cd, t_ans, end


def _quiz_frames(opts, ans, t_opt, cd, t_ans, start, end):
    n = int((end - start) * FPS)
    plates = {i: _opt_plate(o, i) for i, o in enumerate(opts)}
    right = _opt_plate(opts[ans], ans, "right") if 0 <= ans < len(opts) else None
    wrong = {i: _opt_plate(o, i, "wrong") for i, o in enumerate(opts)}
    for f in range(n):
        t = start + f / FPS
        fr = Image.new("RGBA", (W, QUIZ_H), (0, 0, 0, 0))
        for i, o in enumerate(opts):
            if t < t_opt[i]:
                continue
            lt = t - t_opt[i]
            if t >= t_ans:
                im = right if i == ans else wrong[i]
                at = t - t_ans
                s = (1 + 0.12 * math.exp(-at / 0.25) * (1 if i == ans else 0)) if i == ans else 0.94
                a = 1.0 if i == ans else 0.55
            else:
                im = plates[i]
                s = 1.5 - 0.5 * _ease_out_back(min(1, lt / 0.22)) if lt < 0.22 else 1.0
                a = min(1, lt / 0.06)
            x_off = int((1 - min(1, lt / 0.22)) * -300) if lt < 0.22 and t < t_ans else 0
            im2 = im.resize((int(im.width * s), int(im.height * s)), Image.BICUBIC) if s != 1 else im
            if a < 1:
                im2 = im2.copy()
                im2.putalpha(im2.getchannel("A").point(lambda v: int(v * a)))
            cy = 120 + i * 230
            fr.alpha_composite(im2, (40 + x_off + (im.width - im2.width) // 2, cy - im2.height // 2 + 95 - 95))
        for k, tc in enumerate(cd):
            if tc <= t < tc + 1.0 and t < t_ans:
                tm = _timer(3 - k, t - tc, (t - cd[0]) / 3.0)
                fr.alpha_composite(tm, (W - 150 - tm.width // 2, 330 - tm.height // 2))
        yield fr


def insert_pause(video_path: str, t: float, dur: float = 3.0, log=print) -> bool:
    """Вставляет в видео стоп-кадр на dur секунд в момент t, со звуком «пик» каждую секунду
    (последний — выше). Остальное сдвигается на dur."""
    tmp = video_path[:-4] + ".pause.mp4"
    beep = (f"aevalsrc='0.32*sin(2*PI*if(gte(t,{dur - 1:.2f}),1568,1046)*t)*lt(mod(t,1),0.11)"
            f"*min(1,mod(t,1)/0.005)*exp(-mod(t,1)*9)':s=44100:d={dur:.2f},aformat=channel_layouts=stereo")
    flt = (f"[0:v]trim=0:{t:.3f},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={dur:.2f}[v1];"
           f"[0:v]trim={t:.3f},setpts=PTS-STARTPTS[v2];"
           f"[0:a]atrim=0:{t:.3f},asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[a1];"
           f"{beep}[ab];"
           f"[0:a]atrim={t:.3f},asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[a2];"
           f"[a1][ab][a2]concat=n=3:v=0:a=1[a];[v1][v2]concat=n=2:v=1:a=0[v]")
    r = subprocess.run([_ffmpeg(), "-y", "-v", "error", "-i", video_path, "-filter_complex", flt, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", tmp], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"motion: pause failed: {r.stderr[-300:]}")
        return False
    os.replace(tmp, video_path)
    return True


def _render_frames(frames, out, h):
    p = subprocess.Popen([_ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{h}",
                          "-r", str(FPS), "-i", "-", "-c:v", "qtrle", "-pix_fmt", "argb", out], stdin=subprocess.PIPE)
    for fr in frames:
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()
    return out if p.returncode == 0 and os.path.exists(out) else ""


def apply(video_path: str, callouts, srt_path: str, log=print, title: str = "",
          quiz: dict | None = None, title_style: str = "", reddit_sub: str = "") -> str:
    """Накладывает хайп-моушн на video_path (перезаписывает файл)."""
    callouts = [c if isinstance(c, dict) else {"text": str(c)} for c in (callouts or []) if c]
    callouts = [c for c in callouts if str(c.get("text", "")).strip()][:6]
    if not os.path.exists(video_path) or not (callouts or title or quiz):
        return video_path
    total = _probe_duration(video_path)
    words = parse_words(srt_path)
    work = os.path.join(os.path.dirname(video_path), "motion")
    os.makedirs(work, exist_ok=True)
    clips, hits = [], []   # (start, path, y)

    if title_style in ("reddit", "pikabu") and title:
        p = _render_frames(_reddit_frames(str(title)[:160], reddit_sub, 3.4, title_style), os.path.join(work, "reddit.mov"), CANVAS_H)
        if p:
            clips.append((0.05, p, TOP_Y))
            hits.append(0.3)
    elif title:
        p = _render_clip(str(title).strip()[:50], 0, os.path.join(work, "title.mov"), dur=1.9)
        if p:
            clips.append((0.05, p, TOP_Y))
            hits.append(0.22)

    busy_until = 2.1 if title else 0.8
    if quiz and quiz.get("options"):
        opts, ans, t_opt, cd, t_ans, end = _quiz_plan(quiz, words, total)
        # пауза «думай» 3 сек со стоп-кадром, часами и «пик-пик-пик»
        t_cut = next((b for a, b, w in words if a >= max(t_opt) and _norm(w).startswith(("коммент", "пиши", "пишите"))
                      and _norm(w).startswith("коммент")), None) or max(t_opt[-1] + 1.0, t_ans - 0.4)
        if insert_pause(video_path, t_cut, 3.0, log):
            words = [(a + 3.0 if a >= t_cut else a, b + 3.0 if a >= t_cut else b, w) for a, b, w in words]
            total = _probe_duration(video_path)
            t_ans = next((a for a, _, w in words if a >= t_cut + 3.0 and _norm(w).startswith("ответ")), t_cut + 3.1)
            cd = [t_cut, t_cut + 1.0, t_cut + 2.0]
            end = min(total - 0.1, t_ans + 3.0)
            hits += [t_cut + 0.02, t_cut + 1.02, t_cut + 2.02]
        start = max(0.0, min(t_opt) - 0.05)
        p = _render_frames(_quiz_frames(opts, ans, t_opt, cd, t_ans, start, end), os.path.join(work, "quiz.mov"), QUIZ_H)
        if p:
            clips.append((start, p, QUIZ_Y))
            hits += [t + 0.15 for t in t_opt] + [t_ans + 0.05]
            busy_until = end + 0.3
        callouts = []  # в квизе плашки-факты не нужны

    for i, (t, c) in enumerate(_times(callouts, words, total, start=busy_until)):
        p = _render_clip(str(c["text"]).strip()[:40], i + 1, os.path.join(work, f"c{i}.mov"))
        if p:
            clips.append((t, p, TOP_Y))
            hits.append(t + 0.17)
    if not clips:
        return video_path

    inputs, filt = [], [f"[0:v]{_base_filter(hits, total)}[b0]"]
    last = "b0"
    for k, (t, p, y) in enumerate(clips, start=1):
        inputs += ["-i", p]
        filt.append(f"[{k}:v]setpts=PTS-STARTPTS+{t:.3f}/TB[o{k}]")
        filt.append(f"[{last}][o{k}]overlay=0:{y}:eof_action=pass[v{k}]")
        last = f"v{k}"
    filt.append(f"[{last}]null[vout]")
    tmp = video_path[:-4] + ".motion.mp4"
    cmd = [_ffmpeg(), "-y", "-v", "error", "-i", video_path] + inputs + [
        "-filter_complex", ";".join(filt), "-map", "[vout]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", tmp]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        log(f"motion: ffmpeg failed: {r.stderr[-600:]}")
        return video_path
    os.replace(tmp, video_path)
    log(f"motion: clips={len(clips)} quiz={bool(quiz)} style={title_style or 'hype'} -> {video_path}")
    return video_path



# ------------------------------------------------------------------ Энд-кард «подпишись»
ENDCARD_H = 900
ENDCARD_Y = 420
ENDCARD_DUR = 1.8


def _endcard_frames(title: str, sub: str, dur: float):
    idx = 1
    plate = STYLES[idx][0]
    card = _sticker(title, idx)
    ft = _font(70)
    d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lines = _wrap(d0, sub.upper(), ft, 920)[:2] if sub else []
    subimg = None
    if lines:
        lh = 84
        subimg = Image.new("RGBA", (W, lh * len(lines) + 24), (0, 0, 0, 0))
        ds = ImageDraw.Draw(subimg)
        for i, l in enumerate(lines):
            ds.text(((W - ds.textlength(l, font=ft)) / 2, 8 + i * lh), l, font=ft, fill="#FFFFFF",
                    stroke_width=5, stroke_fill="#000000")
    cy = 300
    for f in range(int(dur * FPS)):
        t = f / FPS
        if t < 0.22:
            x = t / 0.22
            s, a, rot = 1.7 - 0.7 * _ease_out_back(x), min(1.0, t / 0.06), -3 + (1 - x) * 12
        else:
            s, a, rot = 1 + 0.035 * math.sin((t - 0.22) * 8), 1.0, -3 + 1.2 * math.sin((t - 0.22) * 6)
        im = card.resize((max(1, int(card.width * s)), max(1, int(card.height * s))), Image.BICUBIC)
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
        if a < 1:
            im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        fr = Image.new("RGBA", (W, ENDCARD_H), (0, 0, 0, 0))
        _rays(fr, W / 2, cy, (t - 0.03) / 0.45, plate)
        fr.alpha_composite(im, ((W - im.width) // 2, cy - im.height // 2))
        if subimg is not None and t > 0.25:
            k = min(1.0, (t - 0.25) / 0.2)
            si = subimg
            if k < 1:
                si = subimg.copy()
                si.putalpha(si.getchannel("A").point(lambda v: int(v * k)))
            fr.alpha_composite(si, (0, cy + card.height // 2 + 50 + int((1 - k) * 40)))
        yield fr


def append_endcard(video_path: str, title: str, sub: str = "", log=print, dur: float = ENDCARD_DUR) -> bool:
    """Дописывает в конец видео 1.8 с: размытый стоп-кадр + плашка «ПОДПИШИСЬ» + подпись + «дзынь»."""
    if not title or not os.path.exists(video_path):
        return False
    work = os.path.join(os.path.dirname(video_path), "motion")
    os.makedirs(work, exist_ok=True)
    last = os.path.join(work, "last.png")
    subprocess.run([_ffmpeg(), "-y", "-v", "error", "-sseof", "-0.3", "-i", video_path, "-frames:v", "1", last],
                   capture_output=True)
    card = _render_frames(_endcard_frames(str(title)[:30], str(sub or "")[:60], dur), os.path.join(work, "endcard.mov"), ENDCARD_H)
    if not os.path.exists(last) or not card:
        log("motion: endcard render failed")
        return False
    ding = (f"aevalsrc='0.22*sin(2*PI*1318*t)*exp(-t*4)+0.14*sin(2*PI*1976*t)*exp(-t*5)':s=44100:d={dur:.2f},"
            f"aformat=channel_layouts=stereo")
    flt = (f"[1:v]scale={W}:{H},boxblur=22:2,eq=brightness=-0.22:saturation=1.1,fps={FPS},setsar=1[bg];"
           f"[2:v]setpts=PTS-STARTPTS[ov];[bg][ov]overlay=0:{ENDCARD_Y}:eof_action=pass,format=yuv420p[ec];"
           f"{ding}[ad];"
           f"[0:v]fps={FPS},setsar=1,format=yuv420p[mv];[0:a]aresample=44100,aformat=channel_layouts=stereo[ma];"
           f"[mv][ma][ec][ad]concat=n=2:v=1:a=1[v][a]")
    tmp = video_path[:-4] + ".end.mp4"
    r = subprocess.run([_ffmpeg(), "-y", "-v", "error", "-i", video_path, "-loop", "1", "-framerate", str(FPS),
                        "-t", f"{dur:.2f}", "-i", last, "-i", card, "-filter_complex", flt, "-map", "[v]", "-map", "[a]",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-maxrate", "8M", "-bufsize", "16M",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp):
        log(f"motion: endcard failed: {r.stderr[-400:]}")
        return False
    os.replace(tmp, video_path)
    log(f"motion: endcard '{title}' -> {video_path}")
    return True
