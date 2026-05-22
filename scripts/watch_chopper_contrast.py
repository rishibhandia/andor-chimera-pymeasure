"""Watch the running andor_qt app's log and print chopper_2x2 ON/OFF contrast.

Usage: run while the app is running (and a TA monitor / scan in chopper_2x2 mode
is active). Adjust the probe chopper phase knob; the contrast number is the one
you want to maximise.

Reads the log file passed as argv[1]. Looks for lines like:
  chopper_2x2 incremental: 4260 frames total, 0 discarded, 2130 ON, 2113 OFF,
  2113 pairs  |  ON mean=800.2, OFF mean=800.6
"""

from __future__ import annotations

import re
import sys
import time

LINE_RE = re.compile(
    r"ON mean=(?P<on>[-\d.]+),\s*OFF mean=(?P<off>[-\d.]+)"
)


def follow(path: str):
    with open(path, "rb") as fh:
        fh.seek(0, 2)  # jump to end
        while True:
            chunk = fh.readline()
            if not chunk:
                time.sleep(0.2)
                continue
            try:
                yield chunk.decode("utf-8", errors="replace")
            except Exception:
                continue


def main(path: str) -> None:
    print(f"Watching {path}")
    print(f"{'ON mean':>10} {'OFF mean':>10} {'diff':>10} {'contrast':>10}  verdict")
    print("-" * 60)
    for line in follow(path):
        m = LINE_RE.search(line)
        if not m:
            continue
        on = float(m.group("on"))
        off = float(m.group("off"))
        diff = on - off
        denom = (on + off) / 2
        contrast = (diff / denom * 100) if denom else 0.0
        verdict = (
            "GOOD - ON >> OFF, probe blocked when pump off"
            if contrast > 50
            else ("BACKWARDS - OFF >> ON, swap phase 180°"
                  if contrast < -50
                  else "NO CONTRAST - probe not modulated"
                       if abs(contrast) < 5
                       else "weak contrast")
        )
        print(f"{on:10.1f} {off:10.1f} {diff:+10.1f} {contrast:+9.2f}%  {verdict}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python watch_chopper_contrast.py <log_path>")
        sys.exit(1)
    main(sys.argv[1])
