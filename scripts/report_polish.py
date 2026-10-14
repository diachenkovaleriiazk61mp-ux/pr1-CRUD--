"""Markdown formatting only; numeric analysis belongs to report.py."""
import re

def polish(text, out=None):
    text = re.sub(r'(?m)(^\|[^\n]*\|)\n(?:[ \t]*\n)+(?=\|)', r'\1\n', text)
    return re.sub(r'\n{3,}', '\n\n', text)
