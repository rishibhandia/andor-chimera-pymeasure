"""Search the MC2000B manuals for specific terms about REF OUT polarity."""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pypdf

KEYWORDS = [
    r"\b[Rr]ef\s*[Oo]ut",
    r"\b[Oo]ut[Pp]ut\s*[Rr]ef",
    r"\bpolarity\b",
    r"\bduty\s*cycle\b",
    r"\b[Hh]igh\s*when\b",
    r"\b[Ll]ogic\s*level\b",
    r"\b[Bb]lade\s*open\b",
    r"\b[Bb]lade\s*[Cc]losed\b",
    r"\bphase\s*adjust\b",
    r"\bphase\s*lock\b",
    r"\b[Ss]lot\b",
    r"\bopen\s*(?:slot|window|phase)\b",
    r"\bphoto-?\s*interrupter\b",
]

for pdf_name in ["MC2000B_Manual_official.pdf", "MC2000B_Manual.pdf"]:
    pdf_path = Path("docs/datasheets") / pdf_name
    if not pdf_path.exists():
        continue
    print(f"\n{'='*70}\n{pdf_name}\n{'='*70}")
    r = pypdf.PdfReader(pdf_path)
    for i, page in enumerate(r.pages):
        text = page.extract_text() or ""
        hits = []
        for kw in KEYWORDS:
            for m in re.finditer(kw, text):
                start = max(0, m.start() - 80)
                end = min(len(text), m.end() + 80)
                snippet = text[start:end].replace("\n", " ").replace("\r", " ")
                snippet = re.sub(r"\s+", " ", snippet)
                hits.append((m.group(), snippet))
        if hits:
            print(f"\n  --- Page {i+1} ---")
            seen = set()
            for kw, snip in hits:
                key = snip[:100]
                if key in seen:
                    continue
                seen.add(key)
                print(f"  [{kw}]")
                print(f"    {snip}")
