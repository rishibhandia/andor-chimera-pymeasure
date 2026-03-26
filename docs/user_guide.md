# Andor Chimera Spectrometer — User Guide

## 1. Overview

Andor Chimera is a Qt-based GUI for controlling an Andor Newton DU970P EMCCD camera and Kymera spectrograph, with integrated transient absorption (TA) pump-probe measurement capabilities. The software controls:

- **Andor Newton DU970P** EMCCD camera (1600 x 200 pixels)
- **Andor Kymera** spectrograph (2 gratings)
- **Newport ESP302** delay stage controller
- **NI PCIe-6353** DAQ for chopper phase reading

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
- [ ] Laser is running (1 kHz rep rate)
- [ ] Chopper controller is running (250 Hz)

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
| **Exposure time** | Integration time per frame | 0.1 s (realtime), 0.002 s (TA chopper_2x2) |
| **VS speed** | Vertical shift speed (row transfer rate) | Index 0 (4.68 us) for 500 Hz operation |
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

The spectrum plot updates in real time. Use this mode to:
- Align the optical path
- Check signal levels
- Verify spectrograph wavelength calibration

## 5. Transient Absorption (TA) Scans

### 5.1 Overview

A TA scan measures the change in optical density (Delta-OD) as a function of pump-probe time delay. The delay stage position is scanned while acquiring pump-on/pump-off spectrum pairs at each position.

### 5.2 Configuring the Delay Scan

The TA panel has three tabs for specifying delay stage positions. All positions are entered in **micrometres (um)**.

#### Linear Tab

Specify a uniform scan range:

| Field | Description | Example |
|-------|-------------|---------|
| **Start position** | First stage position in um | -57000 |
| **End position** | Last stage position in um | -55800 |
| **Step size** | Distance between points in um | 3 |

The equivalent time delay in picoseconds is shown below the fields.

A 3 um step corresponds to approximately 20 fs of optical delay.

#### Log Tab

Specify logarithmically spaced positions. Useful for covering a wide time range efficiently:

| Field | Description | Example |
|-------|-------------|---------|
| **Start position** | First stage position in um (must give positive ps) | 15 |
| **End position** | Last stage position in um | 15000 |
| **Points/decade** | Number of points per decade | 5 |

**Note:** Log spacing is applied in the time (ps) domain. Both start and end must correspond to positive delay values.

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

Multiple `range()` expressions can be combined on separate lines. This is the most flexible way to define a custom scan pattern with different step sizes in different regions.

### 5.3 Scan Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| **ESP302 axis** | Which axis on the Newport ESP302 controller | 2 |
| **Averages per point** | Number of pump-on/pump-off pairs per delay | 100 |
| **Number of scans** | How many complete scan repetitions | 1 |
| **Acquisition mode** | boxcar, shot_to_shot, or chopper_2x2 | chopper_2x2 |
| **Scan direction** | Forward only, or alternating (forward/reverse) | forward |
| **Sample name** | Name tag saved in the data file | — |

### 5.4 Acquisition Modes

#### chopper_2x2 (Recommended)

This is the primary acquisition mode for pump-probe measurements.

**How it works:**
- The Coherent Astrella SDG generates a 500 Hz camera trigger (hardware divide-by-2 of the 1 kHz laser rep rate)
- Each camera frame integrates 2 laser shots
- The NI DAQ reads the chopper phase from P0.0 for each laser shot
- Frames where both shots have the same chopper state are kept: [1,1] = pump-on, [0,0] = pump-off
- Frames at chopper transitions ([1,0] or [0,1]) are discarded
- Pump-on and pump-off frames are paired to compute Delta-I/I0

**Camera settings for chopper_2x2** (auto-configured when mode is selected):
- Trigger mode: Fast External
- Exposure time: 2 ms
- VS speed: Index 0 (4.68 us) — required for 500 Hz frame rate

**External trigger checkbox:** Check this when the SDG provides the 500 Hz trigger directly. The NI DAQ counter is not started — only the phase reader (P0.0) is used.

#### boxcar

Software alternation: first frame = pump-on, second = pump-off. No hardware phase tagging. Less robust than chopper_2x2 but does not require NI DAQ.

### 5.5 Running a Scan

1. Configure delay range, averages, and acquisition mode
2. (Optional) Set a sample name and enable HDF5 saving
3. Click **Start Scan**
4. The status bar shows progress: current delay point, matched pairs, and discard rate
5. Live plots update: Delta-OD spectrum, kinetic trace at the probe wavelength, and heatmap
6. Click **Abort Scan** to stop early

### 5.6 Interpreting the Status Bar

During acquisition, the status bar shows:

```
Scan 1/1 -- pt 15/401  [ACQUIRING]  -379.98 ps  pairs: 85/100  discarded: 0  (100% valid)
```

- **pairs: 85/100** — 85 of 100 required pump-on/pump-off pairs collected so far
- **discarded: 0** — frames at chopper transitions that were thrown away
- **100% valid** — fraction of acquired frames that contributed to pairs (100% = no discards)

### 5.7 Data Output

#### HDF5 File

Enable "Save HDF5 data file" and select a directory. The file contains:
- Wavelength axis
- Delta-OD spectra for every delay point and scan
- Scan metadata (sample name, parameters)

#### Individual Spectra

Enable "Save individual spectra" to write a text file per delay point (2-column: wavelength, Delta-OD).

## 6. Hardware Wiring (BNC-2110)

The NI PCIe-6353 DAQ is connected via a BNC-2110 breakout box. The following connections are required for chopper_2x2 mode:

| BNC-2110 Connector | NI Terminal | Direction | Signal |
|---------------------|-------------|-----------|--------|
| PFI0 (dedicated BNC) | PFI0 | INPUT | 1 kHz laser sync clock |
| PFI12 (dedicated BNC) | PFI12 (pin 2) | INPUT | 500 Hz SDG output (camera trigger) |
| User 2 BNC | P0.0 (port0/line0) | INPUT | Chopper controller phase output |

The **SDG** (Coherent Astrella Synchronization and Delay Generator) divides the 1 kHz laser rep rate by 2 to produce a 500 Hz camera trigger. This signal goes to:
- PFI12 on the NI DAQ (for phase reading clock reference)
- Camera Ext Trigger SMB input (to trigger each frame)

**P0.0** receives the chopper controller output: HIGH (1) when the chopper is open (pump-on), LOW (0) when closed (pump-off). This is sampled at 1 kHz (clocked by PFI0).

### 6.1 Thorlabs MC2000B Chopper Controller

The chopper is a Thorlabs MC2000B optical chopper operating at 250 Hz (1 kHz laser / 4).

**REF OUT signal:** HIGH when the blade is **open** (beam passes = pump-on), LOW when **blocked** (pump-off). This output connects to User 2 BNC (P0.0) on the BNC-2110.

**MC2000B settings:**
- Frequency: 250 Hz (internal or external reference)
- REF OUT: connected to BNC-2110 User 2 (P0.0)
- Phase: adjustable on the front panel (see Section 6.2)

### 6.2 Chopper Phase Adjustment

The chopper phase must be set so that transitions do not coincide with the SDG trigger edges. If you see a high discard rate (>10%):

1. Open the MC2000B front panel phase adjustment
2. Shift by 90 degrees (1 ms = 1/4 of the 4 ms chopper period)
3. A correctly phased chopper yields ~0% discards

**Why this matters:** The SDG fires at 500 Hz. Each frame integrates 2 laser shots. If the chopper transitions during a frame, the two shots have different pump states ([1,0] or [0,1]) and the frame is discarded. Shifting the phase by 90 degrees places transitions midway between SDG edges, so both shots in every frame have the same pump state.

## 7. Troubleshooting

### Camera Error 20992 (DRV_ACQUIRING)

The camera was not properly shut down (e.g., the program was killed during acquisition). **Fix:** Close all Python processes and restart the program.

### "chopper_2x2: N frames acquired without completing M pairs"

The acquisition loop hit its safety limit without collecting enough pairs. Causes:
- Chopper not running or not connected to P0.0
- Chopper phase aligned with SDG edges (all frames are transitions) — adjust phase by 90 degrees
- SDG 500 Hz trigger not connected to the camera Ext Trigger input

### Camera Won't Cool

- Verify the cooler is toggled ON in the temperature control panel
- Check that the camera fan is running
- Allow 5-10 minutes for stabilization

### Stage Not Moving

- Verify the ESP302 is powered on and the correct axis is selected (default: axis 2)
- Check that the stage has been homed since power-on (`xxOR1` command)
- Verify serial connection (RS-232, `rtscts=True`)

### Program Hangs on Startup

- Another instance may be holding the camera. Kill all Python processes first.
- The camera DLL is single-instance — only one program can control it at a time.
