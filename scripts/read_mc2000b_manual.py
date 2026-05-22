"""One-shot helper to dump key pages of the MC2000B manual to a UTF-8 text file."""
import sys
from pathlib import Path
import pypdf

PDF = Path("docs/datasheets/MC2000B_Manual.pdf")
OUT = Path("docs/datasheets/MC2000B_Manual_excerpts.txt")
PAGES = [3, 6, 9, 11, 19, 20, 21, 22, 23, 24, 29, 33]  # 1-indexed

reader = pypdf.PdfReader(PDF)
with OUT.open("w", encoding="utf-8") as fh:
    for p in PAGES:
        fh.write(f"\n====== Page {p} ======\n")
        fh.write(reader.pages[p - 1].extract_text() or "(empty)")
        fh.write("\n")
print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
