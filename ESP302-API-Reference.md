# Newport ESP302 Motion Controller — Python API Reference

> Generated from: ESP302 Programmer's Manual (EDH0414En1017), ESP302 Command Interface Manual, ESP302 User Interface Manual
> Purpose: Reference for Claude Code working on Python applications controlling delay stages via ESP302

---

## 1. Communication Interfaces

### RS-232C (Serial)
- **Port**: COMM. 15-pin Sub-D connector on rear panel
- **Fixed settings**: 8 data bits, no parity, 1 stop bit
- **Handshake**: CTS/RTS hardware flow control (required — the controller de-asserts CTS when its buffer is full)
- **Typical baud rates**: Configurable via front panel

```python
import serial

ser = serial.Serial(
    port='/dev/ttyUSB0',   # or 'COM3' on Windows
    baudrate=19200,        # match controller setting
    bytesize=serial.EIGHTBITS,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    rtscts=True,           # CRITICAL: hardware flow control
    timeout=2.0
)
```

### TCP/IP Ethernet
- **HOST port**: Default IP `192.168.0.254`, configurable via front panel or web interface
- **REMOTE port**: Fixed IP `192.168.254.254`
- **Port 5001**: Telnet — send raw ASCII commands (use for plain Python socket communication)
- **Port 5002**: Newport MKS Command Interface library (official Python/C# wrapper — see Section 2)

```python
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('192.168.0.254', 5001))
sock.settimeout(2.0)
```

---

## 2. Newport MKS Python Wrapper Library (Port 5002)

Newport provides an official Python/C# wrapper library (`MKS ESP302 Command Interface V1.0.x`) accessed via **TCP port 5002** (not 5001). This is an alternative to raw ASCII — use one or the other, not both simultaneously.

### Connection
```python
# Python prototype (Newport library)
[ ] OpenInstrument(address, port, timeout)     # port must be 5002
[ ] CloseInstrument()
[errstring] SetTimeout(sendingTimeout_ms, readingTimeout_ms)
[response, errstring] WriteToInstrument(command)  # raw ASCII passthrough
[LibraryVersionString] GetLibraryVersion()
```

### Naming Convention
- **Setter commands** match the 2-letter mnemonic: `AC(axisNumber, value)`, `PA(axisNumber, position)`
- **Getter commands** append `_Get`: `AC_Get(axisNumber)`, `TP_Get(axisNumber)`, `MD_Get(axisNumber)`
- **Return values**: `[value, errstring]` for getters; `[errstring]` for setters (no output)
- **Error**: returns `0` on success, `-1` on failure

### Key Wrapped Functions
```python
# Power
[errstring] MO(axisNumber)
[errstring] MF(axisNumber)
[isOn, errstring] MO_Get(axisNumber)       # 1=ON, 0=OFF

# Motion
[errstring] PA(axisNumber, positionValue)
[errstring] PR(axisNumber, positionValue)
[errstring] ST(axisNumber)
[errstring] AB()                            # no axis number — all axes

# Wait
[errstring] WS(axisNumber, delayMs)
[errstring] WT(delayMs)

# Query position/status
[position, errstring] TP_Get(axisNumber)    # actual position (no ? needed)
[isDone, errstring] MD_Get(axisNumber)      # 1=done, 0=moving
[position, errstring] PA_Get(axisNumber)    # desired position
[vel, errstring] VA_Get(axisNumber)

# Trajectory
[errstring] VA(axisNumber, velocity)
[errstring] AC(axisNumber, acceleration)
[accel, errstring] AC_Get(axisNumber)
[maxVel, errstring] VU_Get(axisNumber)

# Homing
[errstring] OR(axisNumber, homeMode)
[errstring] SH(axisNumber, presetPosition)

# Errors
[code, timestamp, msg, errstring] TB_Get()
[code, errstring] TE_Get()

# Limits
[errstring] SL(axisNumber, leftLimit)
[errstring] SR(axisNumber, rightLimit)
```

> **When to use the wrapper vs raw ASCII:**
> - Wrapper (port 5002): cleaner Python interface, synchronous calls, good for simple scripts
> - Raw ASCII (port 5001 or serial): lower latency, more control, works without Newport library installed, required for RS-232

---

## 3. Command Syntax (Raw ASCII)

### Format
```
xxAAnnn<CR>
```
- `xx` = axis number (integer, 1–3). Required for axis-specific commands. Omit only where explicitly documented.
- `AA` = two-letter ASCII mnemonic (case-insensitive)
- `nnn` = parameter(s). Multiple params are **comma-separated**.
- Terminator: **carriage return `\r` (ASCII 13)**. Commands without `\r` are not executed.

### Query syntax
Append `?` instead of a parameter to read current value:
```
1VA?    → returns current velocity of axis 1
1TP     → returns current position of axis 1 (no ? needed)
```

### Multiple commands on one line
Separate with semicolons — executed as a near-simultaneous batch:
```
1MO;1VA10;1AC5;1PA25.0\r
```
Max 80 characters per command line.

### Responses
- All controller responses are terminated with `\r\n` (CR LF)
- Commands with no return value produce no output
- Query commands return a value followed by `\r\n`

### Python send/receive pattern
```python
def send_cmd(conn, cmd: str) -> None:
    """Send a command (no response expected)."""
    conn.write(f"{cmd}\r".encode())   # serial
    # or: conn.sendall(f"{cmd}\r".encode())  # socket

def query(conn, cmd: str) -> str:
    """Send a query and return the stripped response."""
    send_cmd(conn, cmd)
    response = conn.readline()         # serial
    # or: response = _recv_until_crlf(conn)  # socket
    return response.decode().strip()

def check_error(conn) -> tuple[int, str]:
    """Read oldest error from FIFO. Returns (code, message)."""
    raw = query(conn, "TB")            # "code, timestamp, MESSAGE"
    parts = raw.split(",", 2)
    code = int(parts[0].strip())
    msg = parts[2].strip() if len(parts) > 2 else ""
    return code, msg
```

---

## 3. Essential Commands for Delay Stage Control

### Motor Power
| Command | Syntax | Description |
|---------|--------|-------------|
| `MO` | `xxMO` | Motor ON — **must be called before any motion** |
| `MF` | `xxMF` | Motor OFF — controlled power-off |
| `MK` | `xxMK` | Motor Kill — power OFF **and** clears home origin (requires re-homing) |
| `MO?` | `xxMO?` | Query power state: `1`=ON, `0`=OFF |

> **CAUTION**: If motor was powered off by a fault, fix the fault before `MO`.

### Homing
| Command | Syntax | Description |
|---------|--------|-------------|
| `OR` | `xxORnn` | Search for Home. `nn`=0–6 mode (see below). Must call after power-on. |
| `OM` | `xxOMnn` | Pre-set home search mode without running it |
| `OH` | `xxOHnn` | Set home search high speed (units/s) |
| `OL` | `xxOLnn` | Set home search low speed (units/s) |
| `SH` | `xxSHnn` | Set position value assigned at home (default `0`) |
| `DH` | `xxDH` | Define current position as home (no hardware search) |

**Home search modes (OR):**
- `0` = Find +0 position count (software zero, no switch)
- `1` = Find Home switch + Index signal ← most common for stages with home switch
- `2` = Find Home switch only
- `3` = Find positive hardware limit
- `4` = Find negative hardware limit
- `5` = Find positive limit + index
- `6` = Find negative limit + index

> **IMPORTANT**: Run `OR` once every time the controller powers on or resets. Position is retained when motor is OFF but lost on full reset/power cycle.

```python
def home_axis(conn, axis: int, mode: int = 1):
    send_cmd(conn, f"{axis}MO")         # motor on
    send_cmd(conn, f"{axis}SH0")        # home = position 0
    send_cmd(conn, f"{axis}OR{mode}")   # execute home search
    wait_for_stop(conn, axis)           # block until done
```

### Motion Commands
| Command | Syntax | Description |
|---------|--------|-------------|
| `PA` | `xxPAnn` | Move to **absolute** position `nn` (in configured units) |
| `PR` | `xxPRnn` | Move **relative** to current position by `nn` |
| `MV` | `xxMVnn` | Move indefinitely in direction `+` or `-` |
| `ST` | `xxST` | Stop motion (uses programmed deceleration) |
| `AB` | `AB` | **Emergency abort ALL axes** (e-stop, powers off by default) |
| `MT` | `xxMT+/-` | Move to hardware travel limit (disables software limits first with `ZS`) |

> **CRITICAL**: The ESP302 does **not** wait for one move to finish before starting the next. Always use `WS` (wait for stop) to synchronize between moves.

```python
# WRONG — axis 2 move starts immediately while axis 1 is still moving
send_cmd(conn, "1PA30.0")
send_cmd(conn, "2PA-10.0")

# CORRECT
send_cmd(conn, "1PA30.0")
send_cmd(conn, "1WS")       # block until axis 1 stops
send_cmd(conn, "2PA-10.0")
send_cmd(conn, "2WS")
```

### Wait / Synchronization
| Command | Syntax | Description |
|---------|--------|-------------|
| `WS` | `xxWSnn` | Wait for axis `xx` to stop. `nn`=additional delay in ms after stop. If `xx` omitted, waits for ALL axes. |
| `WP` | `xxWPnn` | Wait until axis `xx` reaches position `nn` (trigger mid-move) |
| `WT` | `WTnn` | Unconditional wait for `nn` milliseconds (0–60000 ms) |

> `WS` in **immediate (command) mode** blocks the serial port — the host cannot send/receive while waiting. For Python polling, use `MD?` instead.

```python
def wait_for_stop(conn, axis: int, poll_interval: float = 0.05):
    """Non-blocking poll alternative to WS for use in Python."""
    while True:
        done = query(conn, f"{axis}MD?")
        if done.strip() == "1":
            break
        time.sleep(poll_interval)
```

### Velocity, Acceleration, Deceleration
| Command | Syntax | Description |
|---------|--------|-------------|
| `VA` | `xxVAnn` | Set velocity (units/s). Change takes effect immediately, even mid-move. |
| `AC` | `xxACnn` | Set acceleration AND deceleration (units/s²) |
| `AG` | `xxAGnn` | Set deceleration independently (overrides AC for decel) |
| `VU?` | `xxVU?` | Read maximum allowed velocity (read-only, set in config file) |
| `AU?` | `xxAU?` | Read maximum allowed acceleration/deceleration |
| `VA?` | `xxVA?` | Read current velocity setting |
| `AC?` | `xxAC?` | Read current acceleration setting |

> Avoid changing velocity/acceleration during the acceleration or deceleration phase. Change only when stationary or at constant speed.

```python
def configure_axis(conn, axis: int, velocity: float, accel: float):
    send_cmd(conn, f"{axis}VA{velocity}")
    send_cmd(conn, f"{axis}AC{accel}")
```

### Position & Status Queries
| Command | Syntax | Returns | Description |
|---------|--------|---------|-------------|
| `TP` | `xxTP` | float | Read **actual** position (instantaneous encoder position) |
| `DP?` | `xxDP?` | float | Read **desired** position (where controller thinks it's going) |
| `TV` | `xxTV` | float | Read actual velocity |
| `MD?` | `xxMD?` | `0` or `1` | Motion done? `1`=done, `0`=in progress |
| `MF?` | `xxMF?` | `0` or `1` | Motor power state |
| `TS` | `xxTS` or `xxTS1` | ASCII char(s) | Axis status (`xxTS`) or driver status (`xxTS1`). No `?` form. |
| `TP` (no axis) | `TP` | floats | Position of all axes, comma-separated |

#### Decoding `xxTS` (axis status)
Response is **two ASCII characters** — each byte is a bitmask:

Byte 1 (status):
- Bit 0: `0`=axis connected, `1`=not connected
- Bit 1: `0`=motor OFF, `1`=motor ON
- Bit 2: `0`=not moving, `1`=in motion
- Bit 4: `0`=home origin done, `1`=NOT done (note: inverted!)

Byte 2 (faults):
- Bit 0: Following error
- Bit 1: Motor fault
- Bit 2: Negative limit reached
- Bit 3: Positive limit reached

```python
def parse_axis_status(raw: str) -> dict:
    b1 = ord(raw[0])
    b2 = ord(raw[1]) if len(raw) > 1 else 0
    return {
        "connected":     not bool(b1 & 0x01),
        "motor_on":      bool(b1 & 0x02),
        "in_motion":     bool(b1 & 0x04),
        "homed":         not bool(b1 & 0x10),  # bit 4 inverted
        "following_err": bool(b2 & 0x01),
        "motor_fault":   bool(b2 & 0x02),
        "neg_limit":     bool(b2 & 0x04),
        "pos_limit":     bool(b2 & 0x08),
    }
```

### Error Handling
| Command | Syntax | Returns | Description |
|---------|--------|---------|-------------|
| `TB` | `TB` | `code, timestamp, MESSAGE` | Read oldest error from FIFO (10 deep), removes it |
| `TE?` | `TE?` | int | Read oldest error code only, removes it |
| `TE1` | `TE1` | int | Peek at oldest error without removing it |
| `TE2` | `TE2` | int | Count of errors in FIFO |

> Errors are axis-specific: codes 100–199 = Axis 1, 200–299 = Axis 2, 300–399 = Axis 3. Code `0` = no error.

**Key error codes:**
| Code | Meaning |
|------|---------|
| `0` | No error |
| `6` | Command does not exist |
| `7` | Parameter out of range |
| `9` | Axis number out of range |
| `37` | Axis number missing |
| `38` | Command parameter missing |
| `x01` | Parameter out of range (axis-specific) |
| `x03` | Following error threshold exceeded |
| `x04` | Positive hardware limit hit |
| `x05` | Negative hardware limit hit |
| `x06` | Positive software limit hit |
| `x07` | Negative software limit hit |
| `x08` | Motor/stage not connected |
| `x10` | Maximum velocity exceeded |
| `x11` | Maximum acceleration exceeded |
| `x13` | Motor not enabled (forgot `MO`) |
| `x20` | Homing aborted |

```python
def drain_errors(conn) -> list[tuple[int, str]]:
    """Read all errors from FIFO."""
    errors = []
    while True:
        n = int(query(conn, "TE2"))   # count in buffer
        if n == 0:
            break
        raw = query(conn, "TB")
        parts = raw.split(",", 2)
        code = int(parts[0].strip())
        msg = parts[2].strip() if len(parts) > 2 else ""
        errors.append((code, msg))
    return errors
```

### Axis Configuration (Delay Stage Setup)
| Command | Syntax | Description |
|---------|--------|-------------|
| `SN` | `xxSNnn` | Set displacement units: `0`=encoder counts, `1`=motor steps, `2`=mm, `3`=µm, `4`=inches, `5`=milli-inches |
| `SU` | `xxSUnn` | Set encoder resolution (units per encoder count) |
| `SL` | `xxSLnn` | Set negative (left) software travel limit |
| `SR` | `xxSRnn` | Set positive (right) software travel limit |
| `ID` | `xxID` | Read stage model and serial number |
| `VE?` | `VE?` | Read firmware version |
| `ZU` | `ZU` | Get ESP system configuration (which axes have drivers detected) |

### Travel Limits
```python
# Set software limits INSIDE hardware limits — never rely on hardware limit switches in normal operation
send_cmd(conn, f"{axis}SL{negative_limit}")   # e.g., "1SL-75.0"
send_cmd(conn, f"{axis}SR{positive_limit}")   # e.g., "1SR75.0"
```

---

## 5. Delay Stage — Typical Python Initialization Sequence

```python
import serial
import time

def init_esp302(port: str, axis: int, velocity: float, accel: float,
                soft_limit_neg: float, soft_limit_pos: float):
    ser = serial.Serial(port=port, baudrate=19200, bytesize=8,
                        parity='N', stopbits=1, rtscts=True, timeout=2.0)

    # 1. Check firmware
    ser.write(b"VE?\r")
    print("Firmware:", ser.readline().decode().strip())

    # 2. Enable motor
    ser.write(f"{axis}MO\r".encode())
    time.sleep(0.1)

    # 3. Set units (mm for a linear delay stage)
    ser.write(f"{axis}SN2\r".encode())

    # 4. Set motion parameters
    ser.write(f"{axis}VA{velocity}\r".encode())
    ser.write(f"{axis}AC{accel}\r".encode())

    # 5. Set software limits
    ser.write(f"{axis}SL{soft_limit_neg}\r".encode())
    ser.write(f"{axis}SR{soft_limit_pos}\r".encode())

    # 6. Home the axis
    ser.write(f"{axis}SH0\r".encode())   # home position = 0 mm
    ser.write(f"{axis}OR1\r".encode())   # home search: switch + index

    # 7. Wait for homing to complete (poll MD?)
    while True:
        ser.write(f"{axis}MD?\r".encode())
        if ser.readline().decode().strip() == "1":
            break
        time.sleep(0.1)

    # 8. Verify position
    ser.write(f"{axis}TP\r".encode())
    print("Position after home:", ser.readline().decode().strip())

    # 9. Check for errors
    ser.write(b"TE2\r")
    n_errors = int(ser.readline().decode().strip())
    if n_errors > 0:
        ser.write(b"TB\r")
        print("Error:", ser.readline().decode().strip())

    return ser


def move_to(ser, axis: int, position: float, wait: bool = True):
    """Move to absolute position in configured units."""
    ser.write(f"{axis}PA{position}\r".encode())
    if wait:
        while True:
            ser.write(f"{axis}MD?\r".encode())
            if ser.readline().decode().strip() == "1":
                break
            time.sleep(0.05)


def move_relative(ser, axis: int, delta: float, wait: bool = True):
    """Move relative to current position."""
    ser.write(f"{axis}PR{delta}\r".encode())
    if wait:
        while True:
            ser.write(f"{axis}MD?\r".encode())
            if ser.readline().decode().strip() == "1":
                break
            time.sleep(0.05)


def get_position(ser, axis: int) -> float:
    ser.write(f"{axis}TP\r".encode())
    return float(ser.readline().decode().strip())


def emergency_stop(ser):
    """Stop ALL axes immediately (e-stop)."""
    ser.write(b"AB\r")
```

---

## 6. Critical Gotchas & Sequencing Rules

### 1. Motor must be ON before any move
Error `x13 MOTOR NOT ENABLED` if you forget `MO`. Always check with `MO?` before commanding motion.

### 2. No implicit wait between commands
The controller executes commands sequentially from its buffer WITHOUT waiting for motion to finish. Use `WS` (blocks serial) or poll `MD?` in Python.

### 3. WS blocks the serial port in immediate mode
When used interactively (not inside a stored program), `WS` suspends ALL command processing. Use `MD?` polling from Python instead for non-blocking operation.

### 4. Home every power cycle
Run `OR` once per power-on or hardware reset. Motor-off does NOT lose position. Full power-cycle DOES.

### 5. MK vs MF
- `MF` = soft power off, position/home origin retained
- `MK` = kills motor AND clears home origin — requires re-homing before next use

### 6. AB (abort) affects ALL axes
`AB` has no axis parameter — it always stops everything. Default behavior is to cut motor power. Configure per-axis behavior with `ZE`.

### 7. Successive relative moves accumulate rounding error
If using `PR` repeatedly, small rounding errors accumulate. Prefer `PA` (absolute) for precision.

### 8. Acceleration changes mid-move
`VA` and `AC` take effect immediately even during motion. Avoid changing them during accel/decel phases.

### 9. Software limits must be set INSIDE hardware limits
The controller doesn't know the physical hardware limits. Use `SL`/`SR` to set software limits that keep the stage safely away from end-stops.

### 10. Response termination
Commands always **send** `\r` (CR). Controller always **responds** with `\r\n` (CR LF). Use `readline()` on serial.

### 11. TS status byte is ASCII
`xxTS` returns ASCII characters whose binary values encode status bits. Use `ord(char)` and bitmasking in Python — do not try to parse as a number directly.

### 12. Error FIFO is 10 deep, destructive read
`TB` and `TE?` both remove the error from the buffer after reading. Use `TE2` to count before draining.

### 13. For delay stages: time ↔ position conversion
For a linear delay stage, 1 mm of travel = ~6.67 ps of optical delay (double-pass: 2 × 1mm / c ≈ 6.67 ps).
```python
C_MM_PER_PS = 0.29979  # mm per picosecond (speed of light)

def delay_ps_to_mm(delay_ps: float, reference_mm: float = 0.0) -> float:
    """Convert desired optical delay in ps to stage position in mm."""
    return reference_mm + (delay_ps * C_MM_PER_PS) / 2  # /2 for double-pass

def mm_to_delay_ps(position_mm: float, reference_mm: float = 0.0) -> float:
    return (position_mm - reference_mm) * 2 / C_MM_PER_PS
```

---

## 7. Firmware & Controller Info

```
VE?     → ESP302 Snapshot version (main firmware string)
VE1     → MotionKernel version
VE2     → Host version
ZU      → Detect which axes have drivers connected (hex bitmask: bit0=axis1, bit1=axis2, bit2=axis3)
RS      → Full hardware reset (takes up to 20 seconds — stops all axes, powers off, reboots)
```

---

## 8. Ethernet Connection Notes (Raw ASCII, Port 5001)

For TCP/IP via port 5001 (Telnet-style):

```python
import socket

class ESP302Ethernet:
    def __init__(self, host: str, port: int = 5001, timeout: float = 2.0):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.sock.settimeout(timeout)
        self._buf = b""

    def send_cmd(self, cmd: str):
        self.sock.sendall(f"{cmd}\r".encode())

    def query(self, cmd: str) -> str:
        self.send_cmd(cmd)
        return self._readline()

    def _readline(self) -> str:
        while b"\r\n" not in self._buf:
            self._buf += self.sock.recv(1024)
        line, self._buf = self._buf.split(b"\r\n", 1)
        return line.decode().strip()

    def close(self):
        self.sock.close()
```
