"""Цензура мата в субтитрах: в озвучке мат остаётся, в субтитрах — звёздочки."""
import re

from loguru import logger

_PREFIX = r"(?:за|на|по|от|у|вы|до|пере|раз|рас|съ|въ|об|объ|под|подъ|при|про|из|изъ|недо|о|отъ|на)?"
_PATTERNS = [
    r"\w*ху[йеёяию]\w*",
    r"\w*пизд\w*",
    r"\b" + _PREFIX + r"[ьъ]?[её]б(?:[аулнитко]|ш|ыв)\w*",
    r"\b[её]б\b",
    r"\w*долбо[её]б\w*",
    r"\bбля\w*",
    r"\bсук(?:а|и|у|е|ой|ам|ами|ах|ин\w*)\b",
    r"\bмуд(?:ак|ил|о|ач)\w*",
    r"\bпид(?:о|а)?р\w*",
    r"\bгандон\w*",
    r"\b\w*залуп\w*",
    r"\bшлюх\w*",
    r"\b\w*дроч\w*",
]
_RE = re.compile("|".join(f"(?:{p})" for p in _PATTERNS), re.IGNORECASE)


def _mask(match: re.Match) -> str:
    w = match.group(0)
    if len(w) <= 3:
        return w[0] + "*" * (len(w) - 1)
    return w[0] + "*" * (len(w) - 2) + w[-1]


def censor_text(text: str) -> str:
    return _RE.sub(_mask, text)


def censor_srt_file(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        out = []
        for line in content.splitlines(keepends=True):
            # не трогаем номера и таймкоды
            if "-->" in line or line.strip().isdigit():
                out.append(line)
            else:
                out.append(censor_text(line))
        new = "".join(out)
        if new != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            logger.info("subtitle profanity censored")
    except Exception as e:
        logger.warning(f"subtitle censor failed: {e}")
