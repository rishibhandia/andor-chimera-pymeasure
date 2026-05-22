"""Standalone control script for Thorlabs MC2000B choppers.

Talks raw serial over USB (115200 8N1) — does NOT use Thorlabs' DLL because
its command framing times out against MC2000B firmware v4.19. The ASCII
command set is fully documented in the manual; we use that directly.

Subcommands
-----------
  list                       List available COM ports.
  info <port>                Open a chopper and print all parameters.
  setup --pump <port> --probe <port> [--freq HZ] [--blade NAME] [--n N] [--d D]
                             Configure pump as master (internal ref, given blade,
                             given freq) and probe as slave (external ref, N/D
                             harmonic, phase=0).
  phase <port> <deg>         Set probe phase (0-360°).
  enable <port> 0|1          Enable / disable a chopper.
  sweep --probe <port> --from D --to D --step D [--dwell S]
                             Sweep probe phase. While running, watch andor_qt
                             log for contrast.
  shutdown <port> [<port>...]
                             Disable each port.

Example
-------
  .venv/Scripts/python.exe scripts/chopper_control.py info COM3
  .venv/Scripts/python.exe scripts/chopper_control.py setup --pump COM3 --probe COM4
  .venv/Scripts/python.exe scripts/chopper_control.py sweep --probe COM4 --from 0 --to 359 --step 20 --dwell 5
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

import serial
import serial.tools.list_ports

BAUD = 115200
DEFAULT_TIMEOUT = 0.5  # seconds — replies arrive in tens of ms

# Blade index per manual section 8.2 ("blade=" command)
BLADE_INDEX = {
    "MC1F2":     0,
    "MC1F10":    1,
    "MC1F15":    2,
    "MC1F30":    3,
    "MC1F60":    4,
    "MC1F100":   5,
    "MC1F10HP":  6,
    "MC1F2P10":  7,
    "MC1F6P10":  8,
    "MC1F10A":   9,
    "MC2F330":  10,
    "MC2F47":   11,
    "MC2F57B":  12,
    "MC2F860":  13,
    "MC2F5360": 14,
}

# Ref-input modes per manual section 8.3 (depends on blade — these are the
# canonical 4-value codes for high-precision blades like MC1F10HP / MC1F2 /
# MC1F2P10; simpler blades use 0=internal / 1=external).
REF_INPUT_HIGHPREC = {
    "INT-OUTER": 0,
    "INT-INNER": 1,
    "EXT-OUTER": 2,
    "EXT-INNER": 3,
}
REF_INPUT_BASIC = {"INT": 0, "EXT": 1}


# ---------------------------------------------------------------------------
# Serial communication
# ---------------------------------------------------------------------------

class Chopper:
    """One MC2000B over a serial port. Use as context manager."""

    def __init__(self, port: str, timeout: float = DEFAULT_TIMEOUT):
        self.port = port
        self._timeout = timeout
        self._ser: Optional[serial.Serial] = None

    def __enter__(self):
        self._ser = serial.Serial(
            self.port, BAUD,
            bytesize=8, parity="N", stopbits=1,
            timeout=self._timeout, write_timeout=self._timeout,
        )
        # No flow control; read off any pending banner
        time.sleep(0.05)
        self._ser.reset_input_buffer()
        return self

    def __exit__(self, *a):
        if self._ser is not None:
            self._ser.close()

    def _query(self, cmd: str) -> str:
        """Send a command, return the response body (without echo or prompt)."""
        assert self._ser is not None
        self._ser.reset_input_buffer()
        self._ser.write((cmd + "\r").encode("ascii"))
        # Read until we see the "> " prompt
        buf = b""
        deadline = time.time() + self._timeout * 4
        while time.time() < deadline:
            chunk = self._ser.read(256)
            if chunk:
                buf += chunk
                if buf.endswith(b"> "):
                    break
            else:
                time.sleep(0.01)
        text = buf.decode("ascii", errors="replace")
        # Strip echo (the command we sent) and trailing prompt
        lines = [ln for ln in text.replace("\r", "\n").split("\n") if ln.strip()]
        if lines and lines[0].strip() == cmd:
            lines = lines[1:]
        if lines and lines[-1].strip() == ">":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def query(self, cmd: str) -> str:
        return self._query(cmd)

    def get_int(self, cmd: str) -> int:
        resp = self._query(cmd)
        try:
            return int(resp.strip())
        except ValueError as e:
            raise RuntimeError(f"{cmd!r} returned non-int: {resp!r}") from e

    def set(self, cmd: str, value: int) -> None:
        resp = self._query(f"{cmd}={value}")
        if resp.lower().startswith("command error") or "error" in resp.lower():
            raise RuntimeError(f"set {cmd}={value} failed: {resp!r}")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_list(_args):
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No COM ports found.")
        return 1
    print(f"Found {len(ports)} COM port(s) (some may not be choppers):")
    for p in ports:
        print(f"  {p.device}: {p.description}  hwid={p.hwid}")
    print("\nTo identify which port is a chopper, run:")
    print("  chopper_control.py info COM3")
    return 0


def cmd_info(args):
    with Chopper(args.port) as ch:
        rows = [
            ("id (model + firmware)", "id?", None),
            ("enable (0/1)", "enable?", None),
            ("reference", "ref?", None),
            ("reference output", "output?", None),
            ("blade type (index)", "blade?", None),
            ("harmonic multiplier (N)", "nharmonic?", None),
            ("harmonic divider (D)", "dharmonic?", None),
            ("phase (deg)", "phase?", None),
            ("frequency target (Hz)", "freq?", None),
            ("actual blade frequency (Hz)", "refoutfreq?", None),
            ("external ref frequency (Hz)", "input?", None),
            ("ref-out frequency (Hz)", "refoutfreq?", None),
        ]
        for label, cmd, _ in rows:
            try:
                v = ch.query(cmd)
            except Exception as e:
                v = f"ERROR ({e})"
            print(f"  {label:36s} = {v}")
    return 0


def cmd_setup(args):
    # Map blade name → index
    blade_idx = BLADE_INDEX.get(args.blade.upper())
    if blade_idx is None:
        print(f"Unknown blade {args.blade!r}. Choices: {', '.join(BLADE_INDEX)}")
        return 1

    # For MC1F10HP (high-precision) we use the 4-value ref-input map
    pump_ref = REF_INPUT_HIGHPREC["INT-INNER"]   # 1
    probe_ref = REF_INPUT_HIGHPREC["EXT-INNER"]  # 3

    with Chopper(args.pump) as pump:
        pump.set("blade", blade_idx)
        pump.set("ref", pump_ref)
        pump.set("output", 1)         # actual output, so probe locks to blade
        pump.set("freq", args.freq)
        pump.set("enable", 1)
        actual = pump.query("refoutfreq?")
        print(f"Pump  ({args.pump}): blade={args.blade}, ref=INT-INNER, "
              f"freq={args.freq} Hz, ENABLED  actual_freq={actual}")

    time.sleep(0.5)

    with Chopper(args.probe) as probe:
        probe.set("blade", blade_idx)
        probe.set("ref", probe_ref)
        probe.set("nharmonic", args.n)
        probe.set("dharmonic", args.d)
        probe.set("phase", 0)
        probe.set("enable", 1)
        time.sleep(2)
        ext_freq = probe.query("input?")
        actual = probe.query("refoutfreq?")
        print(f"Probe ({args.probe}): blade={args.blade}, ref=EXT-INNER, "
              f"N/D={args.n}/{args.d}, phase=0, ENABLED  "
              f"ext_ref={ext_freq} Hz  actual_freq={actual}")
    return 0


def cmd_phase(args):
    with Chopper(args.port) as ch:
        ch.set("phase", args.phase)
        readback = ch.query("phase?")
    print(f"{args.port}: phase set to {args.phase}°, readback {readback}°")
    return 0


def cmd_enable(args):
    with Chopper(args.port) as ch:
        ch.set("enable", args.value)
    print(f"{args.port}: enable = {args.value}")
    return 0


def cmd_sweep(args):
    with Chopper(args.probe) as ch:
        print(f"Sweeping {args.probe} from {args.from_}° to {args.to}° "
              f"step {args.step}°, dwell {args.dwell}s.")
        print("Watch andor_qt log for contrast.\n")
        print(f"{'time':8s}  {'phase':>5s}  {'readback':>8s}  {'actual_freq':>11s}")
        phase = args.from_
        while phase <= args.to:
            ch.set("phase", phase)
            readback = ch.query("phase?")
            freq = ch.query("refoutfreq?")
            ts = time.strftime("%H:%M:%S")
            print(f"{ts}  {phase:5d}  {readback:>8s}  {freq:>11s}", flush=True)
            time.sleep(args.dwell)
            phase += args.step
    return 0


def cmd_shutdown(args):
    for port in args.ports:
        try:
            with Chopper(port) as ch:
                ch.set("enable", 0)
            print(f"{port}: disabled")
        except Exception as e:
            print(f"{port}: shutdown failed ({e})")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(description="Thorlabs MC2000B control over raw serial.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List available COM ports.")

    p_info = sub.add_parser("info", help="Open a chopper port and print all params.")
    p_info.add_argument("port", help="COM port (e.g. COM3)")

    p_setup = sub.add_parser("setup", help="Configure pump master + probe slave.")
    p_setup.add_argument("--pump", required=True, help="Pump chopper COM port")
    p_setup.add_argument("--probe", required=True, help="Probe chopper COM port")
    p_setup.add_argument("--freq", type=int, default=250, help="Pump freq Hz (default 250)")
    p_setup.add_argument("--blade", default="MC1F10HP",
                         help=f"Blade name (default MC1F10HP). Choices: {', '.join(BLADE_INDEX)}")
    p_setup.add_argument("--n", type=int, default=1, help="Probe harmonic N (default 1)")
    p_setup.add_argument("--d", type=int, default=1, help="Probe harmonic D (default 1)")

    p_phase = sub.add_parser("phase", help="Set phase on one chopper.")
    p_phase.add_argument("port")
    p_phase.add_argument("phase", type=int)

    p_en = sub.add_parser("enable", help="Enable / disable a chopper.")
    p_en.add_argument("port")
    p_en.add_argument("value", type=int, choices=[0, 1])

    p_sw = sub.add_parser("sweep", help="Sweep probe phase across a range.")
    p_sw.add_argument("--probe", required=True)
    p_sw.add_argument("--from", dest="from_", type=int, required=True)
    p_sw.add_argument("--to", type=int, required=True)
    p_sw.add_argument("--step", type=int, default=20)
    p_sw.add_argument("--dwell", type=float, default=3.0)

    p_sd = sub.add_parser("shutdown", help="Disable choppers.")
    p_sd.add_argument("ports", nargs="+")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    handler = {
        "list":     cmd_list,
        "info":     cmd_info,
        "setup":    cmd_setup,
        "phase":    cmd_phase,
        "enable":   cmd_enable,
        "sweep":    cmd_sweep,
        "shutdown": cmd_shutdown,
    }[args.cmd]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
