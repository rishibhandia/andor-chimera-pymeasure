import pypdf
from pathlib import Path

PDF = Path(r"C:\Program Files (x86)\Thorlabs\MC2000B\Sample\MC2000B SDK Manual.pdf")
OUT = Path("docs/datasheets/MC2000B_SDK_Manual_excerpts.txt")

r = pypdf.PdfReader(PDF)
with OUT.open("w", encoding="utf-8") as fh:
    for p in [1, 2, 3, 12, 15, 23, 24, 25]:
        fh.write(f"\n====== Page {p} ======\n")
        fh.write(r.pages[p - 1].extract_text() or "(empty)")
print("ok")
