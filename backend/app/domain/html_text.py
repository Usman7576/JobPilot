"""Turn scraped job descriptions (HTML or markdown) into clean plain text.

We store text only and render it as text, so no third-party HTML ever reaches the page.
"""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

_BLOCK_TAGS = ("p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr")
MAX_DESCRIPTION_CHARS = 20_000
# Built with chr() so this source file stays plain ASCII.
_NO_BREAK_SPACE = chr(0xA0)
_CARRIAGE_RETURN = chr(13)


def html_to_text(raw: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe"]):
        tag.decompose()
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after("\n")
    return tidy(soup.get_text())


def markdown_to_text(raw: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), raw)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [label](url) -> label
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[*+]\s+", "- ", text, flags=re.M)
    text = re.sub(r"\\([-.*_#()\[\]!+])", r"\1", text)  # markdown escapes like \- or \.
    return tidy(text)


def tidy(text: str) -> str:
    text = html.unescape(text).replace(_NO_BREAK_SPACE, " ").replace(_CARRIAGE_RETURN, "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_DESCRIPTION_CHARS]


def clean_description(raw: str | None, is_html: bool) -> str | None:
    if not raw:
        return None
    if re.search(r"&lt;/?(p|div|br|li|ul|span|strong)\b", raw, re.I):
        raw = html.unescape(raw)  # some feeds escape their HTML twice
    looks_html = is_html or bool(re.search(r"</?(p|div|br|li|ul|span|strong)\b", raw, re.I))
    text = html_to_text(raw) if looks_html else markdown_to_text(raw)
    return text or None
