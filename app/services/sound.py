"""«Как звучит …»: ищем настоящую запись на Wikimedia Commons и приклеиваем её в конец видео
с визуализатором волны поверх фото объекта."""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

from app.services import motion

UA = {"User-Agent": "MoneyPrinterTurbo-personal/1.0 (personal shorts generator)"}


def _get(url: str, params: dict | None = None, timeout=30):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def find_audio(query: str) -> tuple[str, str]:
    """-> (url, название файла) первой подходящей аудиозаписи на Commons."""
    for q in (query, " ".join(query.split()[:2])):
        try:
            d = json.loads(_get("https://commons.wikimedia.org/w/api.php", {
                "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
                "gsrsearch": f"filetype:audio {q}", "gsrlimit": 10, "prop": "imageinfo",
                "iiprop": "url|mime|size"}))
        except Exception:
            continue
        pages = sorted((d.get("query", {}).get("pages", {}) or {}).values(), key=lambda p: p.get("index", 99))
        for p in pages:
            ii = (p.get("imageinfo") or [{}])[0]
            if str(ii.get("mime", "")).startswith(("audio/", "application/ogg", "video/webm")) and ii.get("size", 0) < 40_000_000:
                return ii.get("url", ""), p.get("title", "")
    return "", ""


def append_sound(video_path: str, query: str, task_dir: str, log=print, seconds: float = 9.0) -> str:
    if not query or not os.path.exists(video_path):
        return video_path
    url, title = find_audio(query)
    if not url:
        log(f"sound: nothing found for '{query}'")
        return video_path
    work = os.path.join(task_dir, "sound")
    os.makedirs(work, exist_ok=True)
    raw = os.path.join(work, "raw" + os.path.splitext(urllib.parse.urlparse(url).path)[1][:6])
    try:
        open(raw, "wb").write(_get(url, timeout=120))
    except Exception as e:
        log(f"sound: download failed: {e}")
        return video_path
    ff = motion._ffmpeg()
    wav = os.path.join(work, "clip.wav")
    # громкость по-взрослому: loudnorm -14 LUFS, фейды, моно->стерео
    r = subprocess.run([ff, "-y", "-v", "error", "-i", raw, "-t", str(seconds), "-vn",
                        "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:d=0.15,afade=t=out:st={seconds - 0.6}:d=0.6",
                        "-ar", "44100", "-ac", "2", wav], capture_output=True, text=True)
    dur = motion._probe_duration(wav)
    if r.returncode != 0 or dur < 2.0:
        log(f"sound: bad audio ({dur:.1f}s) {r.stderr[-200:]}")
        return video_path
    # фон: фото объекта из Википедии (если было) или последний кадр видео
    imgs = sorted(glob.glob(os.path.join(task_dir, "wiki_images", "*.jpg")))
    bg = imgs[0] if imgs else os.path.join(work, "last.jpg")
    if not imgs:
        subprocess.run([ff, "-y", "-v", "error", "-sseof", "-0.2", "-i", video_path, "-frames:v", "1", bg])
    badge = os.path.join(work, "badge.png")
    motion._sticker("Настоящий звук", 1).save(badge)
    seg = os.path.join(work, "seg.mp4")
    flt = (f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
           f"zoompan=z='min(zoom+0.0008,1.12)':d={int(dur * 30) + 30}:s=1080x1920:fps=30,eq=brightness=-0.12[bg];"
           f"[1:a]asplit[a1][a2];"
           f"[a1]showwaves=s=1000x420:mode=cline:colors=#FFFFFF|#FF2D55:scale=sqrt:rate=30,format=rgba[w];"
           f"[bg][w]overlay=40:(H-h)/2+160[v1];"
           f"[2:v]scale=iw*0.8:-1[b];[v1][b]overlay=(W-w)/2:230[vout]")
    r = subprocess.run([ff, "-y", "-v", "error", "-i", bg, "-i", wav, "-i", badge,
                        "-filter_complex", flt, "-map", "[vout]", "-map", "[a2]", "-t", f"{dur:.2f}",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", seg], capture_output=True, text=True)
    if r.returncode != 0:
        log(f"sound: segment failed: {r.stderr[-300:]}")
        return video_path
    out = video_path[:-4] + ".sound.mp4"
    r = subprocess.run([ff, "-y", "-v", "error", "-i", video_path, "-i", seg, "-filter_complex",
                        "[0:v]fps=30,format=yuv420p,setsar=1[v0];[1:v]fps=30,format=yuv420p,setsar=1[v1];"
                        "[0:a]aresample=44100,aformat=channel_layouts=stereo[a0];[1:a]aresample=44100,aformat=channel_layouts=stereo[a1];"
                        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]",
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-maxrate", "8M", "-bufsize", "16M",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        log(f"sound: concat failed: {r.stderr[-300:]}")
        return video_path
    os.replace(out, video_path)
    log(f"sound: appended '{title}' ({dur:.1f}s)")
    return video_path
