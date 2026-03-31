# Andor Chimera Spectrometer — User Guide

## 1. Overview

Andor Chimera is a Qt-based GUI for controlling an Andor Newton DU970P EMCCD camera and Kymera spectrograph, with integrated transient absorption (TA) pump-probe measurement capabilities. The software controls:

- **Andor Newton DU970P** EMCCD camera (1600 x 200 pixels)
- **Andor Kymera** spectrograph (2 gratings)
- **Newport ESP302** delay stage controller
- **NI PCIe-6353** DAQ for chopper phase reading
- **Thorlabs MC2000B** optical chopper (250 Hz, 10-slot blade)

## 2. Getting Started

### 2.1 Launching the Program

From a terminal in the project directory:

```bash
uv run python -m andor_qt
```

The program will:
1. Load configuration
2. Initialize the camera (~5 s)
3. Initialize the spectrograph (~5 s)
4. Initialize motion controllers (~1 s)
5. Display "Hardware ready" in the main window

### 2.2 Mock Mode (No Hardware)

For testing without connected hardware:

```bash
uv run python -m andor_qt --mock
```

Or set the environment variable `ANDOR_MOCK=1`.

### 2.3 Startup Checklist

Before starting the program with real hardware:

- [ ] Camera power is on
- [ ] Spectrograph power is on
- [ ] ESP302 delay stage controller is on and homed
- [ ] NI DAQ BNC-2110 cables are connected (see Section 6)
- [ ] Camera Fire output wired to User 1 BNC (PFI13)
- [ ] Chopper REF OUT wired to User 2 BNC (P0.0)
- [ ] Laser is running (1 kHz rep rate)
- [ ] SDG 500 Hz output connected to camera Ext Trigger and PFI12
- [ ] Chopper controller is running (250 Hz, locked to SDG)

## 3. Camera & Spectrograph

### 3.1 Temperature Control

The Newton camera requires cooling for low-noise operation.

1. The cooler turns on automatically at startup (target: -80 C)
2. Wait for the temperature status to show **Stabilized** before acquiring data
3. Cooling typically takes 5-10 minutes from room temperature

**Important:** Always allow the camera to warm up before closing the program. The shutdown dialog handles this automatically. Do not force-quit unless necessary.

### 3.2 Spectrograph Settings

- **Grating**: Select from the grating dropdown. The Kymera has 2 gratings.
- **Center wavelength**: Set the center wavelength in nm. The spectrograph will move the turret.

### 3.3 Camera Settings

The camera settings panel appears in both the Realtime window and the TA scan configuration:

| Setting | Description | Typical Value |
|---------|-------------|---------------|
| **Trigger mode** | Internal (free-run) or Fast External (hardware trigger) | Internal for realtime, Fast External for TA |
| **Exposure time** | Integration time per frame | 0.1 s (realtime), 0.4 ms (TA chopper_2x2) |
| **VS speed** | Vertical shift speed (row transfer rate) | Index 0 (4.9 us) for 500 Hz operation |
| **HS speed** | Horizontal readout speed | 3 MHz (fastest), 50 kHz (lowest noise) |
| **EM gain** | Electron-multiplying gain (1-1000) | Only for EM amplifier mode |
| **Pre-amp gain** | Pre-amplifier gain | x1, x2, or x4 |

## 4. Realtime Acquisition

The Realtime window provides continuous live acquisition for alignment and setup.

1. Open the Realtime window from the main menu
2. Select acquisition mode (FVB for spectra, Image for 2D)
3. Set exposure time
4. Click **Start** to begin continuous acquisition
5. Click **Stop** to halt

Use this mode to align the optical path, check signal levels, and verify spectrograph wavelength calibration.

## 5. Transient Absorption (TA)

### 5.1 Overview

A TA scan measures the change in optical density (Delta-OD) as a function of pump-probe time delay. The delay stage position is scanned while acquiring pump-on/pump-off spectrum pairs at each position.

The TA panel has two main modes:

- **Scan mode**: Automated scan through a list of delay stage positions
- **Monitor mode**: Continuous acquisition at the current position for signal optimization

### 5.2 Monitor Mode

Monitor mode runs continuous acquisition cycles at the current stage position. Use this to optimize signal before running a full scan.

1. Set camera settings (trigger mode, exposure, VS/HS speed)
2. Set the number of averages per cycle
3. Click **Monitor** to start continuous acquisition
4. The live display shows: raw pump/ref spectra, delta-I/I0, and kinetic trace
5. Use the jog buttons to move the delay stage while monitoring
6. Click **Stop** to halt

**Dark frame**: Click **Acquire Dark** to take a dark frame (block the probe beam first). This is automatically subtracted from all subsequent acquisitions. Click **Clear Dark** to remove.

**External trigger**: Check "External trigger (SDG)" when the SDG provides the 500 Hz camera trigger directly. This prevents the NI DAQ counter from being started (which would conflict with the Camera Fire signal on PFI13).

### 5.3 Configuring the Delay Scan

The TA panel has three tabs for specifying delay stage positions. All positions are entered in **micrometres (um)**.

#### Linear Tab

Specify a uniform scan range:

| Field | Description | Example |
|-------|-------------|---------|
| **Start position** | First stage position in um | -57000 |
| **End position** | Last stage position in um | -55800 |
| **Step size** | Distance between points in um | 3 |

A 3 um step corresponds to approximately 20 fs of optical delay.

#### Log Tab

Specify logarithmically spaced positions (in the time domain):

| Field | Description | Example |
|-------|-------------|---------|
| **Start position** | First stage position in um | 15 |
| **End position** | Last stage position in um | 15000 |
| **Points/decade** | Number of points per decade | 5 |

#### Manual Tab

Enter stage positions directly using Python `range()` syntax or plain numbers:

```
# Scan -57000 to -56000 um in 3 um steps
range(-57000, -56000, 3)

# Then scan -56000 to -50000 um in 10 um steps
range(-56000, -50000, 10)

# Individual positions
-49000, -48000

# Comments starting with # are ignored
```

### 5.4 Scan Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| **ESP302 axis** | Which axis on the Newport ESP302 controller | 2 |
| **Averages per point** | Number of pump-on/pump-off pairs per delay | 100 |
| **Number of scans** | How many complete scan repetitions | 1 |
| **Acquisition mode** | boxcar, shot_to_shot, chopper_2x2, or static_onoff | chopper_2x2 |
| **Scan direction** | Forward only, or alternating (forward/reverse) | forward |
| **Sample name** | Name tag saved in the data file | -- |

### 5.5 Acquisition Modes

#### chopper_2x2 (Recommended)

Hardware-synchronized pump-probe acquisition using NI DAQ phase tagging.

**How it works:**
- The SDG generates a 500 Hz camera trigger (divide-by-2 of the 1 kHz laser)
- Each camera frame integrates 2 laser shots (`shots_per_frame=2`)
- The NI DAQ reads the chopper phase from P0.0 for each laser shot (clocked by PFI0 at 1 kHz)
- Frames where both shots have the same chopper state are kept: [1,1] = pump-on, [0,0] = pump-off
- Frames at chopper transitions ([1,0] or [0,1]) are discarded
- Pump-on and pump-off frames are paired to compute Delta-I/I0

**Tag-to-frame synchronization:** The phase reader uses the Camera Fire output (PFI13) as its NI DAQ start trigger. The reader arms but does not sample P0.0 until the camera actually starts exposing, guaranteeing that tag[0] corresponds to frame[0]. This makes the pump-ON/OFF assignment deterministic across camera restarts.

**Camera settings** (auto-configured when mode is selected):
- Trigger mode: Fast External
- Exposure time: 0.4 ms
- VS speed: Index 0 (4.9 us) — required for 500 Hz frame rate
- HS speed: Index 0 (3 MHz)
- Overlap mode: enabled (required for 500 Hz)

**External trigger checkbox:** Check this when the SDG provides the 500 Hz trigger directly to the camera. The NI DAQ counter is not started — only the phase reader (P0.0) is used.

#### static_onoff

Two-pass acquisition for situations where a mechanical chopper is not available:

1. **Pass 1 (Pump ON):** Scan all delay positions with pump beam unblocked
2. **User prompt:** Block the pump beam manually
3. **Pass 2 (Pump OFF):** Repeat all delay positions with pump blocked
4. Delta-OD = -log10(pump_spectrum / ref_spectrum)

Also available as single-phase buttons in monitor mode (Acquire Pump ON / Acquire Pump OFF).

#### boxcar

Software alternation: first frame = pump-on, second = pump-off. No hardware phase tagging. Less robust than chopper_2x2 but does not require NI DAQ.

#### shot_to_shot

1 kHz single-shot acquisition using isolated crop mode for sub-millisecond readout. Each frame gets one P0.0 tag. Requires crop mode compatible camera settings.

### 5.6 Running a Scan

1. Configure delay range, averages, and acquisition mode
2. (Optional) Set a sample name and enable HDF5 saving
3. Click **Start Scan**
4. The status bar shows progress: current delay point, matched pairs, ETA, and discard rate
5. Live plots update: Delta-OD spectrum, kinetic trace, and heatmap
6. Click **Abort Scan** to stop early
7. Click **Pause** / **Resume** to temporarily halt

### 5.7 Data Output

#### HDF5 File

Enable "Save HDF5 data file" and select a directory. The file contains:
- Wavelength axis
- Delta-OD spectra for every delay point and scan
- Scan metadata (sample name, parameters)

#### Individual Spectra

Enable "Save individual spectra" to write text files per delay point:
- `scan000_pos+1234.5um.txt` — Delta-OD spectrum (wavelength, value)
- `scan000_pos+1234.5um_pump.txt` — Mean pump-on spectrum
- `scan000_pos+1234.5um_ref.txt` — Mean pump-off spectrum
- `scan000_pos+1234.5um_pump_std.txt` — Pump standard deviation
- `scan000_pos+1234.5um_ref_std.txt` — Ref standard deviation

## 6. Hardware Wiring (BNC-2110)

The NI PCIe-6353 DAQ is connected via a BNC-2110 breakout box.

### 6.1 Required Connections

| BNC-2110 Connector | NI Terminal | Direction | Signal |
|---------------------|-------------|-----------|--------|
| (dedicated BNC) | PFI0 | INPUT | 1 kHz laser sync (phase reader sample clock) |
| (dedicated BNC) | PFI12 (pin 2) | INPUT | SDG 500 Hz (camera trigger + chopper REF IN) |
| User 1 BNC | PFI13 (pin 40) | INPUT | Camera Fire output (phase reader start trigger) |
| User 2 BNC | P0.0 (port0/line0) | INPUT | Chopper REF OUT (pump phase tags) |

### 6.2 Camera Connections

| Camera Connector | Destination | Signal |
|-----------------|-------------|--------|
| Ext Trigger SMB | SDG 500 Hz (direct BNC) | External trigger input |
| Fire output (I/O connector) | BNC-2110 User 1 BNC | TTL HIGH during exposure |

### 6.3 Signal Chain

```
Laser 1 kHz  -->  PFI0 (phase reader clock)
             -->  SDG (external reference)

SDG 500 Hz   -->  Camera Ext Trigger SMB (direct BNC)
             -->  PFI12 (NI DAQ input)
             -->  Chopper REF IN (chopper locks to SDG, runs at 250 Hz)

Camera Fire  -->  PFI13 (User 1 BNC) -- phase reader start trigger

Chopper REF OUT (250 Hz)  -->  P0.0 (User 2 BNC) -- pump phase tags
```

### 6.4 Why Camera Fire on PFI13?

The phase reader samples P0.0 at 1 kHz (clocked by PFI0) to determine the chopper state for each laser shot. Without the Fire trigger, the phase reader and camera start independently, creating a random offset between tags and frames that causes the pump-ON/OFF assignment to flip ~50% of the time on restart.

With the Camera Fire output as the phase reader's NI DAQ start trigger, the reader waits until the camera actually begins its first exposure before sampling. This guarantees tag[0] = chopper state during frame[0], making the assignment deterministic (tested 20/20 stable across restarts).

**CRITICAL:** The counter output CTR1 is hardwired to PFI13 on PCIe-6353. If the NI DAQ counter trigger generator is used (NIDAQChopper500Hz), it would conflict with the Camera Fire input. Always check "External trigger (SDG)" when using the Fire trigger approach.

### 6.5 Thorlabs MC2000B Chopper Controller

| Setting | Value |
|---------|-------|
| **Blade** | MC1F10HP (10-slot high precision) |
| **REF IN** | External, from SDG 500 Hz |
| **Harmonic** | N=1, D=2 (divides SDG by 2 = 250 Hz chopper) |
| **REF OUT** | INNER -- tracks actual blade position of inner slots |

**P0.0 = HIGH when blade is open** (beam passes through). The polarity is fixed by hardware and does not change between sessions.

### 6.6 Chopper Phase Adjustment

The chopper phase must be set so that transitions do not coincide with the SDG trigger edges. If you see a high discard rate (>10%):

1. Open the MC2000B front panel phase adjustment
2. Shift by 90 degrees (1 ms = 1/4 of the 4 ms chopper period)
3. A correctly phased chopper yields ~0% discards

## 7. Troubleshooting

### Camera Error 20992 (DRV_NOT_AVAILABLE)

Another program is holding the camera. Close all Python processes and restart:

```bash
powershell.exe -Command "Stop-Process -Name python -Force -ErrorAction SilentlyContinue"
sleep 3
uv run python -m andor_qt
```

### "chopper_2x2: no frames in cycle"

- Check that SDG 500 Hz is connected to camera Ext Trigger SMB
- Check that PFI0 (1 kHz laser sync) is connected
- Verify the chopper is running and P0.0 shows alternating signal

### High Discard Rate (>10%)

- Adjust chopper phase by 90 degrees (see Section 6.6)
- Check that `shots_per_frame` matches your trigger rate (2 for 500 Hz camera / 250 Hz chopper)

### Pump ON/OFF Assignment Flips

- Verify Camera Fire output is wired to User 1 BNC (PFI13)
- Ensure "External trigger (SDG)" is checked in the UI
- If Fire output is not available, the assignment may flip on each monitor restart (50/50)

### Camera Won't Cool

- Verify the cooler is toggled ON in the temperature control panel
- Check that the camera fan is running
- Allow 5-10 minutes for stabilization

### Stage Not Moving

- Verify the ESP302 is powered on and the correct axis is selected (default: axis 2)
- Check that the stage has been homed since power-on
- Verify serial connection (RS-232, `rtscts=True`)

### Program Hangs on Startup

- Another instance may be holding the camera. Kill all Python processes first.
- The camera DLL is single-instance -- only one program can control it at a time.
