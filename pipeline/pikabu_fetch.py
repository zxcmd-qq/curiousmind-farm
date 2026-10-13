"""Реальные истории с Пикабу (сообщество «Истории из жизни» + тег). Копит кэш, не повторяет.
Печатает JSON: {"source": "...", "sub": "pikabu", "stories": [{id,title,text,sub,author,rating}]}"""
import html, json, os, random, re, sys

BASE = os.environ.get("CM_STATE") or os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(BASE, "pikabu-cache.json")
USED_FILE = os.path.join(BASE, "used-facts.txt")
PAGES = ["https://pikabu.ru/community/stories?f=best",
         "https://pikabu.ru/community/stories",
         "https://pikabu.ru/tag/%D0%98%D1%81%D1%82%D0%BE%D1%80%D0%B8%D1%8F%20%D0%B8%D0%B7%20%D0%B6%D0%B8%D0%B7%D0%BD%D0%B8?n=4",
         "https://pikabu.ru/community/stories?page=2", "https://pikabu.ru/community/stories?f=best&page=2",
         "https://pikabu.ru/community/stories?f=best&page=3"]
BAD = re.compile(r"суицид|самоубий|изнасил|педофил|умер|умерла|смерт|похорон|рак |онколог|детдом|избил|насили|кров(ь|и\b|ью|ав|оте)|труп|убил|убий|зарезал|нож[оа]м|ранен|травм|перелом|драк|авари|дтп|больниц|реанимац|скорая|морг|мертв|покойн|полици|\bмент[ыо]|секс|интим|голая|голый|голые|член|минет|порн|эрот|18\+|наркот|закладк|блев|рвот|понос|гинеколог|беремен|аборт|войн|сво |политик|ребен|ребён|детск|\bдет(и|ей|ям|ьми)\b|дочь|дочк|дочер|сынок|\bсын(а|у|ом)?\b|школьн|малыш|младен|подрост", re.I)


def used_ids():
    try:
        return {l.strip()[7:] for l in open(USED_FILE, encoding="utf-8") if l.startswith("pikabu:")}
    except Exception:
        return set()


def text_of(chunk):
    paras = re.findall(r'story-block_type_text">(.*?)</div>', chunk, re.S)
    t = " ".join(re.sub(r"<[^>]+>", " ", p) for p in paras)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def parse(page):
    out = []
    parts = re.split(r'(?=<article class="story" )', page)
    for p in parts[1:]:
        head = p[:1500]
        sid = re.search(r'data-story-id="(\d+)"', head)
        if not sid or 'data-is-fixed-story="true"' in head or 'data-is-adv' in head:
            continue
        rating = int((re.search(r'data-rating="(-?\d+)"', head) or [0, 0])[1])
        author = (re.search(r'data-author-name="([^"]*)"', head) or [0, ""])[1]
        title = re.search(r'class="story__title-link"[^>]*>(.*?)</a>', p, re.S)
        title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", title[1]))).strip() if title else ""
        tags = re.findall(r'data-tag="([^"]+)"', p[:40000])
        body = text_of(p[:60000])
        if len(body) < 600 or BAD.search(title + " " + body) or "Реклама" in tags:
            continue
        out.append({"id": sid[1], "title": title, "text": body[:2200], "sub": "pikabu",
                    "author": author, "rating": rating, "translated_reddit": any("Reddit" in t for t in tags)})
    return out


def main():
    used = used_ids()
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        cache = []
    fresh = []
    try:
        from curl_cffi import requests as cr
        for u in PAGES:
            try:
                r = cr.get(u, impersonate="safari17_0", timeout=25)
                if r.status_code == 200:
                    fresh += parse(r.content.decode("cp1251", "ignore"))
            except Exception:
                pass
    except Exception:
        pass
    known = {s["id"] for s in cache}
    cache += [s for s in fresh if s["id"] not in known]
    cache = cache[-500:]
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    pool = [s for s in {s["id"]: s for s in fresh}.values() if s["id"] not in used]
    source = "pikabu"
    if not pool:
        source = "cache"
        pool = [s for s in cache if s["id"] not in used]
    pool = [s for s in pool if not BAD.search(s.get("title", "") + " " + s.get("text", ""))]   # и старый кэш тоже фильтруем
    pool.sort(key=lambda s: -s.get("rating", 0))
    top = pool[:12]
    random.shuffle(top)
    print(json.dumps({"source": source, "sub": "pikabu", "stories": top[:8]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
