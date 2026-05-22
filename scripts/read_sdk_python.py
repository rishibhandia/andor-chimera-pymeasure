"""Extract Chapter 3 (Python SDK) from the MC2000B SDK Manual."""
from pathlib import Path
import pypdf

PDF = Path(r"C:\Program Files (x86)\Thorlabs\MC2000B\Sample\MC2000B SDK Manual.pdf")
OUT = Path("docs/datasheets/MC2000B_SDK_Python.txt")

r = pypdf.PdfReader(PDF)
with OUT.open("w", encoding="utf-8") as fh:
    for p in range(17, 24):  # pages 17-23 cover Python SDK
        fh.write(f"\n====== Page {p} ======\n")
        fh.write(r.pages[p - 1].extract_text() or "(empty)")
print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
