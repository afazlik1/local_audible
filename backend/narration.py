"""Conservative layout cleanup without deleting legitimate narrative numbers."""
import re


def speech_plan(text: str, limit: int = 700) -> list[tuple[str, float]]:
    """Preserve deliberate blank-line pauses, independent of a TTS engine's whitespace handling."""
    blocks = re.split(r"(\n[ \t]*\n(?:[ \t]*\n)*)", text.replace("\r\n", "\n"))
    plan = []
    for i in range(0, len(blocks), 2):
        block = blocks[i].strip()
        if not block:
            continue
        parts = [part.strip() for part in review_chunks(block, limit) if part.strip()]
        gap = blocks[i + 1] if i + 1 < len(blocks) else ""
        # One blank line: 450 ms; extra blank lines: up to 1.1 seconds.
        pause = min(1.1, 0.45 + 0.325 * max(0, gap.count("\n") - 2)) if gap else 0.0
        for j, part in enumerate(parts):
            plan.append((part, pause if j == len(parts) - 1 else 0.0))
    if plan:
        plan[-1] = (plan[-1][0], 0.0)  # No artificial silence after the book ends.
    return plan


def integrate(pages: list[str]) -> str:
    result = ""
    for page in pages:
        if page.strip() == "[NO NARRATIVE]":
            continue
        page = re.sub(r"(?m)^\s*\[Page \d+\]\s*$", "", page)
        page = re.sub(r"([a-z])-\n([a-z])", r"\1\2", page)
        page = "\n\n".join(" ".join(p.split()) for p in re.split(r"\n\s*\n", page) if p.strip())
        if not page:
            continue
        if result.endswith("-") and page[0].islower():
            result = result[:-1] + page
        elif result and result[-1] not in '.!?…:”"' and page[0].islower():
            result += " " + page
        else:
            result += ("\n\n" if result else "") + page
    return result.strip()


def review_chunks(text: str, limit: int = 6000) -> list[str]:
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n\n", limit // 2, limit)
        if cut < 0:
            cut = text.rfind(". ", limit // 2, limit)
            if cut >= 0:
                cut += 1
        if cut < 0:
            cut = text.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:]
    if text:
        parts.append(text)
    return parts
