# OptoSigma GSC-02 / GSC-02C + OSMS-YAW — Python RS232 Reference

**Hardware:** OSMS-40YAW / OSMS-60YAW rotation stage + GSC-02 or GSC-02C two-axis controller
**Interface:** RS232C only (no USB/GPIB/Ethernet)

---

## 1. Serial Connection

```python
import serial

ser = serial.Serial(
    port='/dev/ttyUSB0',   # macOS: /dev/cu.usbserial-*, Windows: 'COM3'
    baudrate=9600,          # match DIP switch setting (see below)
    bytesize=8,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    rtscts=True,            # REQUIRED: hardware flow control (RTS/CTS)
    timeout=5
)
```

**Connector:** D-sub 9-pin **female** on controller, **inch** screw threads.
Cable: 9-pin D-SUB **straight** (male↔female).

| Pin | Signal || Pin | Signal |
|-----|--------||-----|--------|
| 2   | TxD    || 6   | DTR    |
| 3   | RxD    || 7   | CTS    |
| 4   | DSR    || 8   | RTS    |
| 5   | SG     ||     |        |

**Baud rate** is set by DIP switches SW1 + SW2:

| SW2 | SW1 | Baud rate |
|-----|-----|-----------|
| ON  | ON  | 2400      |
| ON  | OFF | 4800      |
| OFF | ON  | **9600** (factory default) |
| OFF | OFF | 19200     |

---

## 2. General Command Principles

- All commands: ASCII, terminated with **`CR+LF`** (`\r\n`)
- **Most commands return no response** — use `Q:` or `!:` to confirm state
- `Q:`, `!:`, and `?:` always return data
- Movement commands (`M:`, `A:`, `J:`) are queued; the **`G:` command executes them**
- Axis parameter `n`: `1` = axis 1, `2` = axis 2, `W` = both axes
- While **BUSY**, only `L:`, `Q:`, `!:`, `?:` are accepted — all others return NG

```python
def send(cmd: str):
    ser.write((cmd + '\r\n').encode('ascii'))

def query(cmd: str) -> str:
    ser.write((cmd + '\r\n').encode('ascii'))
    return ser.readline().decode('ascii').strip()
```

---

## 3. Command Reference

### Motion Commands

| Command | Syntax | Description | Example |
|:--------|:-------|:------------|:--------|
| **Home** | `H:nm` | Return to mechanical origin. `n`=axis, `m`=direction (+/−). Fixed speeds: S=500, F=5000 pps, R=200 ms. | `H:1−` (axis 1, CW — correct for YAW) |
| **Relative move** | `M:nmPx` | Queue relative move. `n`=axis, `m`=direction, `x`=pulses (0–16,777,214). Must follow with `G:`. | `M:1+P1000` |
| **Absolute move** | `A:nmPx` | Queue absolute move to pulse coordinate. **GSC-02C only.** Must follow with `G:`. | `A:1+P10000` |
| **Jog** | `J:nm` | Queue continuous motion at start speed (S). Runs until `L:` or limit hit. Must follow with `G:`. | `J:W−+` |
| **Drive** | `G:` | Execute the queued `M:`, `A:`, or `J:` command. | `G:` |
| **Stop** | `L:n` | Decelerate and stop axis `n`. Does **not** stop `H:` — use `L:W` or `L:E`. | `L:W` |
| **Emergency stop** | `L:E` | Immediate stop, all axes, no deceleration. | `L:E` |
| **Set logical origin** | `R:n` | Zero the coordinate counter at current position. No motion. | `R:W` |

### Configuration Commands

| Command | Syntax | Description | Example |
|:--------|:-------|:------------|:--------|
| **Speed settings** | `D:nSsF fRr` | Set start speed S (pps), max speed F (pps), accel/decel time R (ms). F must be ≥ S. R=0 → constant speed. | `D:1S500F5000R200` |
| **Motor excitation** | `C:nm` | `m=0` free motor (manual rotation ok), `m=1` hold motor. | `C:10` (free axis 1) |

**Speed ranges:** 1–20,000 pps (GSC-02), 1–30,000 pps (GSC-02C). Default on power-up: S=500, F=5000, R=200.

**Both-axis speed example:** `D:WS100F1000R200S100F1000R200` (axis 1 params then axis 2 params)

### Status & Query Commands

| Command | Returns | Description |
|:--------|:--------|:------------|
| `!:` | `B` or `R` | Quick busy check. `B`=busy, `R`=ready. |
| `Q:` | see below | Full position + status string. |
| `?:V` | e.g. `V2.00` | Firmware version. |
| `?:N` | e.g. `GSC-02C` | Device name. GSC-02C only. |
| `?:D1` | e.g. `S500F5000R200` | Current speed settings for axis 1. GSC-02C only. |

**`Q:` response format:** `pos1, pos2, ACK1, ACK2, ACK3`

```
Q:
→  -        0,+        0,K,K,R
```

Positions are 10-character fixed-width (sign left-aligned, digits right-aligned).

| Field | Values | Meaning |
|:------|:-------|:--------|
| ACK1 | `K` / `X` | K = last command OK; X = command/parameter error |
| ACK2 | `K` / `L` / `M` / `W` | K = normal stop; L = axis 1 at limit; M = axis 2 at limit; W = both at limit |
| ACK3 | `B` / `R` | B = busy; R = ready |

```python
def get_status():
    resp = query('Q:')
    parts = resp.split(',')
    return {
        'pos1': int(parts[0]),
        'pos2': int(parts[1]),
        'cmd_ok':  parts[2].strip() == 'K',
        'limit':   parts[3].strip(),  # K / L / M / W
        'busy':    parts[4].strip() == 'B',
    }

def is_busy() -> bool:
    return query('!:') == 'B'

def wait_done(poll: float = 0.05):
    import time
    while is_busy():
        time.sleep(poll)
```

---

## 4. GSC-02C System Type B (Advanced)

The GSC-02C defaults to System Type A (same behaviour as GSC-02). Type B enables software-configurable settings that override DIP switches.

```
SYS:1    Switch to System Type B  (requires power cycle to take effect)
SYS:0    Switch back to Type A
```

Key Type B commands:

| Command | Syntax | Description |
|:--------|:-------|:------------|
| **ACK responses** | `ACK:1` / `ACK:0` | `1`=MAIN: controller replies `OK`/`NG` to every command. `0`=SUB: silent (default). |
| **Step count** | `S:nd` | `d=1` full step, `d=2` half step (default). |
| **Homing method** | `ORG:na` | `0`=off, `1`=MINI, `2`=CENTER, `3`=ORGS, `4`=NORM, `5`=MARK. |
| **Direction flip** | `DR:na` | `0`=POS (normal), `1`=NEG (reverse + direction). |
| **Limit sensor logic** | `LSL:na` | `0`=Normal close, `1`=Normal open. |
| **ORG speed** | `B:nSsFfRr` | Set homing speeds (same format as `D:`). |

With `ACK:1` enabled, every command returns `OK` or `NG` — makes error handling much simpler than polling `Q:`.

---

## 5. Stage Specifications (OSMS-YAW)

| Parameter | OSMS-40YAW | OSMS-60YAW |
|:----------|:-----------|:-----------|
| Motor | 5-phase stepping, 0.72° step | same |
| Gear ratio | Worm gear 1:144 | same |
| **Resolution — half step** | **0.0025°/pulse** | same |
| Resolution — full step | 0.005°/pulse | same |
| **Pulses per degree** | **400 pulses/°** | same |
| Max speed | 30°/s | same |
| Travel | CCW (+ dir) to ∞; hard stop at −2.5° CW | same |
| Positioning accuracy | 0.1° | 0.1° |
| Repeatability | 0.02° | 0.02° |
| Backlash | 0.1° | 0.1° |
| Lost motion | 0.05° | 0.05° |
| Homing sensors | CW limit only — **no origin or NEAR sensor** | same |
| Limit sensor logic | Normally closed | same |

> **Conversion:** `degrees = pulses × 0.0025` (half-step, default mode)

---

## 6. DIP Switch Settings

| SW | Function | ON | OFF |
|:---|:---------|:---|:----|
| 1 + 2 | Baud rate | (see §1 table) | |
| 3 | Homing method | MARK | **MINI** ← use for YAW |
| 4 | Limit sensor logic | Normal open | **Normal close** ← YAW |
| 5 | Axes to home | Axis 1 only | Both axes |

**OSMS-YAW required settings:** SW3 = OFF (MINI), SW4 = OFF (Normal close).

---

## 7. Gotchas and Critical Notes

1. **`M:`/`A:`/`J:` require `G:`** — these commands only queue a move; nothing happens until `G:` is sent. Send `G:` immediately after with no other commands in between.

2. **While BUSY, most commands are silently ignored** (or return NG in Type B). Only `L:`, `Q:`, `!:`, `?:` work. Always wait for READY before sending motion commands.

3. **Homing (`H:`) cannot be stopped with `L:1` or `L:2`** — you must use `L:W` or `L:E`.

4. **OSMS-YAW has no origin sensor** — only a CW limit sensor. MINI homing uses it as the reference: stage hits CW limit, backs off 1000 pulses, touches limit again at slow speed, backs off 1000 pulses → that point is position 0. Expect ~2–3 seconds for homing.

5. **Home in the CW (−) direction**: `H:1-`. Using `+` will jog CCW indefinitely until the CCW limit (which doesn't exist on YAW), or until you stop it.

6. **Hardware flow control (`rtscts=True`) is mandatory.** Without it, commands sent in quick succession will be silently dropped or corrupted — no error will be raised by pyserial.

7. **No response to most commands** — never assume success. After any move, check `Q:` or `!:` to confirm position and status.

8. **Motor free (`C:n0`) disables all subsequent motion** until re-held with `C:n1`. The controller will silently reject move commands while excitation is off.

9. **Position after home = 0 pulses = 0°.** The CW hard limit sits at ~−1000 pulses (−2.5°). Do not command moves past this.

10. **`SYS:` type change requires a power cycle.** Sending `SYS:1` takes effect only after power off/on.

---

## 8. Complete Python Driver

```python
import serial
import time


class GSC02:
    """
    Driver for OptoSigma / SIGMAKOKI GSC-02 / GSC-02C stage controller.
    Communicates over RS232C. Compatible with both model generations.
    """

    PULSES_PER_DEGREE = 400  # half-step default: 0.0025°/pulse → 400 pulses/°

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0):
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            rtscts=True,        # required: hardware flow control
            timeout=timeout,
        )

    def close(self):
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------ low level

    def _send(self, cmd: str):
        self.ser.write((cmd + '\r\n').encode('ascii'))

    def _query(self, cmd: str) -> str:
        self.ser.write((cmd + '\r\n').encode('ascii'))
        return self.ser.readline().decode('ascii').strip()

    # ------------------------------------------------------------------ status

    def version(self) -> str:
        return self._query('?:V')

    def is_busy(self) -> bool:
        return self._query('!:') == 'B'

    def wait(self, poll: float = 0.05):
        while self.is_busy():
            time.sleep(poll)

    def status(self) -> dict:
        """Return dict with integer positions and decoded ACK flags."""
        resp = self._query('Q:')
        parts = resp.split(',')
        return {
            'pos1':    int(parts[0]),
            'pos2':    int(parts[1]),
            'cmd_ok':  parts[2].strip() == 'K',
            'limit':   parts[3].strip(),   # K / L / M / W
            'busy':    parts[4].strip() == 'B',
        }

    # ------------------------------------------------------------------ motion

    def home(self, axis: int | str = 1, direction: str = '-'):
        """
        Return to mechanical origin.
        For OSMS-YAW always use direction='-' (CW, toward limit sensor).
        Blocks until homing completes.
        """
        self._send(f'H:{axis}{direction}')
        self.wait()

    def move_relative(self, axis: int | str, pulses: int, direction: str = '+'):
        """Relative move. Positive pulses = CCW. Blocks until complete."""
        self._send(f'M:{axis}{direction}P{abs(pulses)}')
        self._send('G:')
        self.wait()

    def move_absolute(self, axis: int | str, pulses: int, direction: str = '+'):
        """Absolute move to pulse coordinate. GSC-02C only. Blocks until complete."""
        self._send(f'A:{axis}{direction}P{abs(pulses)}')
        self._send('G:')
        self.wait()

    def jog_start(self, axis: int | str, direction: str = '+'):
        """Begin continuous jog at start speed. Call stop() to halt."""
        self._send(f'J:{axis}{direction}')
        self._send('G:')

    def stop(self, axis: int | str = 'W'):
        """Decelerate and stop. Does not work during H: — use emergency_stop()."""
        self._send(f'L:{axis}')

    def emergency_stop(self):
        """Immediate stop all axes. Works during homing."""
        self._send('L:E')

    def set_origin(self, axis: int | str = 'W'):
        """Zero the logical coordinate at current position. No motion."""
        self._send(f'R:{axis}')

    # ------------------------------------------------------------------ config

    def set_speed(self, axis: int | str, s_pps: int, f_pps: int, r_ms: int):
        """Set start speed, max speed, and accel/decel time for one or both axes."""
        self._send(f'D:{axis}S{s_pps}F{f_pps}R{r_ms}')

    def free_motor(self, axis: int | str = 'W'):
        """De-energise motor — allows manual rotation. Disables move commands."""
        if axis == 'W':
            self._send('C:W00')
        else:
            self._send(f'C:{axis}0')

    def hold_motor(self, axis: int | str = 'W'):
        """Re-energise motor after free_motor()."""
        if axis == 'W':
            self._send('C:W11')
        else:
            self._send(f'C:{axis}1')

    # ------------------------------------------------------------------ degree helpers (OSMS-YAW)

    def move_degrees(self, axis: int, degrees: float):
        """
        Rotate by angle in degrees.
        Positive = CCW (+direction), negative = CW (−direction).
        """
        direction = '+' if degrees >= 0 else '-'
        pulses = round(abs(degrees) * self.PULSES_PER_DEGREE)
        self.move_relative(axis, pulses, direction)

    def position_degrees(self, axis: int = 1) -> float:
        """Return current axis position in degrees."""
        return self.status()[f'pos{axis}'] / self.PULSES_PER_DEGREE


# ------------------------------------------------------------------ usage example

if __name__ == '__main__':
    with GSC02(port='/dev/cu.usbserial-0001', baudrate=9600) as ctrl:
        print('Firmware:', ctrl.version())

        # Home axis 1 toward CW limit (correct for OSMS-YAW)
        print('Homing...')
        ctrl.home(axis=1, direction='-')
        print('Homed. Status:', ctrl.status())

        # Set operating speed
        ctrl.set_speed(axis=1, s_pps=500, f_pps=3000, r_ms=200)

        # Move 45° CCW
        ctrl.move_degrees(axis=1, degrees=45.0)
        print(f'Position: {ctrl.position_degrees(1):.4f}°')

        # Move back to origin
        ctrl.move_degrees(axis=1, degrees=-45.0)
```
