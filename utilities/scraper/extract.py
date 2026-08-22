"""Shared HTML-to-text extraction — used by both scraper and AI processor."""

import re

from bs4 import BeautifulSoup


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    # Replace image tags with a text marker preserving position:
    # [image: <filename>] — filename only, no path/URL.
    for el in soup.select("img"):
        src = el.get("src", "")
        name = src.rsplit("/", 1)[-1] if "/" in src else src
        name = name.split("?")[0]
        el.replace_with(soup.new_string(f" [image: {name}] "))

    # Convert math script tags to LaTeX text
    for sel, fmt in [
        ("script[type='math/tex']", "$ {} $"),
        ("script[type='math/tex; mode=display']", "$$ {} $$ "),
    ]:
        for el in soup.select(sel):
            if el.string:
                val = el.string.strip()
                token = fmt.replace("{}", val).strip()
                el.replace_with(soup.new_string(f" {token} "))

    # Remove MathJax visual spans (they're just rendered markup, redundant)
    for el in soup.select(".MathJax, .MathJax_Preview"):
        el.decompose()

    # Remove tex-spans: they duplicate plain text
    for el in soup.select("span.tex-span"):
        val = el.get_text().strip()
        el.replace_with(soup.new_string(f" ${val}$ "))

    # Remove duplicate text nodes around tex-span replacements
    for el in soup.find_all(string=True):
        if el.parent and el.parent.name in ("p", "div", "span") and el.strip() == "":
            prev = el.find_previous_sibling(string=True)
            if prev and prev.strip() == el.strip() and prev.parent is el.parent:
                pass

    c = soup.select_one("div.problemindexholder") or soup.select_one("div.problem-statement")
    if not c:
        return html

    lines = []

    def strip_sec_name(text: str, name: str) -> str:
        if text.lower().startswith(name.lower()):
            text = text[len(name) :].lstrip(" .:\n")
        return text

    def get_clean(el) -> str:
        if not el:
            return ""
        text = el.get_text(" ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    header = c.select_one(".header")
    if header:
        t = header.select_one(".title")
        if t:
            lines.append("Title: " + t.get_text(strip=True))
        tl = header.select_one(".time-limit")
        if tl:
            lines.append(
                "Time: " + tl.get_text(strip=True).replace("time limit per test", "").strip(": \n")
            )
        ml = header.select_one(".memory-limit")
        if ml:
            lines.append(
                "Memory: "
                + ml.get_text(strip=True).replace("memory limit per test", "").strip(": \n")
            )
        lines.append("")

    # Description: all content between .header and first section div
    desc_parts = []
    for sibling in header.find_next_siblings() if header else []:
        if sibling.name == "div" and sibling.get("class"):
            cls = " ".join(sibling.get("class"))
            if cls in ("input-specification", "output-specification", "sample-tests", "note"):
                break
        t = get_clean(sibling)
        if t:
            desc_parts.append(t)
    if desc_parts:
        lines.append("Description:")
        lines.append("\n".join(desc_parts))
        lines.append("")

    inp_sec = c.select_one(".input-specification")
    if inp_sec:
        inp_text = strip_sec_name(get_clean(inp_sec), "Input")
        if inp_text:
            lines.append("Input:")
            lines.append(inp_text)
            lines.append("")

    out_sec = c.select_one(".output-specification")
    if out_sec:
        out_text = strip_sec_name(get_clean(out_sec), "Output")
        if out_text:
            lines.append("Output:")
            lines.append(out_text)
            lines.append("")

    for i, s in enumerate(c.select(".sample-test"), 1):
        inp = s.select_one(".input pre")
        out = s.select_one(".output pre")
        if inp:
            lines.append(f"Example {i} Input:")
            lines.append(inp.get_text("\n").strip())
            lines.append("")
        if out:
            lines.append(f"Example {i} Output:")
            lines.append(out.get_text("\n").strip())
            lines.append("")

    note = c.select_one(".note")
    if note:
        note_text = strip_sec_name(get_clean(note), "Note")
        if note_text:
            lines.append("Note:")
            lines.append(note_text)
            lines.append("")

    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"^\s+$", "", result, flags=re.MULTILINE)
    return result.strip()
