"""Format chat replies as readable Markdown for the UI."""


def to_markdown_reply(text: str) -> str:
    """Convert plain-text agent output into structured Markdown."""
    stripped = text.strip()
    if stripped.startswith("## "):
        return stripped

    blocks = [b.strip() for b in stripped.split("\n\n") if b.strip()]
    if not blocks:
        return stripped

    summary = blocks[0].replace("\n", " ")
    findings: list[str] = []

    for block in blocks[1:]:
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("•"):
                findings.append(line[1:].strip())
            elif line.startswith("- "):
                findings.append(line[2:].strip())
            elif line.startswith("  •"):
                findings.append(line[3:].strip())
            elif line.endswith(":") and len(line) < 40:
                findings.append(f"**{line.rstrip(':')}**")
            else:
                findings.append(line)

    parts = [f"## Summary\n{summary}"]
    if findings:
        parts.append("## Key findings")
        parts.extend(f"- {item}" if not item.startswith("-") else item for item in findings)

    return "\n\n".join(parts)
