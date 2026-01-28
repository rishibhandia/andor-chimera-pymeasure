"""Test script for Andor instrument wrappers.

Run with: uv run python tests/test_andor_instrument.py

This script tests the PyMeasure instrument wrappers for:
- AndorCamera (FVB and 2D image acquisition)
- AndorSpectrograph (grating, wavelength, calibration)

Use ANDOR_MOCK=1 environment variable to run without hardware.
"""

import logging
import os
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
log = logging.getLogger(__name__)


def test_camera():
    """Test the AndorCamera instrument wrapper."""
    from andor_pymeasure.instruments.andor_camera import AndorCamera

    print("\n" + "=" * 60)
    print("Testing AndorCamera")
    print("=" * 60)

    cam = AndorCamera()

    try:
        print("\n1. Initializing camera...")
        cam.initialize()
        print(f"   Detector: {cam.xpixels}x{cam.ypixels}")
        print(f"   Pixel size: {cam.info.pixel_width}x{cam.info.pixel_height}um")
        print(f"   Serial: {cam.info.serial_number}")

        print(f"\n2. Temperature: {cam.temperature:.1f}C ({cam.temperature_status})")

        print("\n3. Testing FVB acquisition...")
        cam.set_exposure(0.1)
        data = cam.acquire_fvb()
        print(f"   FVB spectrum shape: {data.shape}")
        print(f"   Min: {data.min():.1f}, Max: {data.max():.1f}, Mean: {data.mean():.1f}")

        print("\n4. Testing 2D image acquisition...")
        cam.set_exposure(0.1)
        image = cam.acquire_image(hbin=1, vbin=1)
        print(f"   Image shape: {image.shape}")
        print(f"   Min: {image.min():.1f}, Max: {image.max():.1f}")

        print("\n5. Testing binned 2D acquisition...")
        image_binned = cam.acquire_image(hbin=2, vbin=2)
        print(f"   Binned image shape: {image_binned.shape}")

        print("\n[PASS] Camera tests completed successfully")

    except Exception as e:
        print(f"\n[FAIL] Camera test failed: {e}")
        raise

    finally:
        print("\n6. Shutting down camera...")
        cam.shutdown()
        print("   Camera shutdown complete")


def test_spectrograph():
    """Test the AndorSpectrograph instrument wrapper."""
    from andor_pymeasure.instruments.andor_spectrograph import AndorSpectrograph

    print("\n" + "=" * 60)
    print("Testing AndorSpectrograph")
    print("=" * 60)

    spec = AndorSpectrograph()

    try:
        print("\n1. Initializing spectrograph...")
        spec.initialize()
        print(f"   Serial: {spec.info.serial_number}")
        print(f"   Number of gratings: {spec.info.num_gratings}")
        for g in spec.info.gratings:
            print(f"   Grating {g.index}: {g.lines_per_mm} l/mm, {g.blaze}")
            print(f"      Wavelength range: {g.wavelength_min:.1f} - {g.wavelength_max:.1f} nm")

        print(f"\n2. Current grating: {spec.grating}")
        print(f"   Current wavelength: {spec.wavelength:.1f} nm")

        print("\n3. Testing wavelength change...")
        wl_min, wl_max = spec.get_wavelength_limits()
        print(f"   Wavelength limits: {wl_min:.1f} - {wl_max:.1f} nm")
        target_wl = (wl_min + wl_max) / 2
        print(f"   Setting wavelength to {target_wl:.1f} nm...")
        spec.wavelength = target_wl
        print(f"   New wavelength: {spec.wavelength:.1f} nm")

        print("\n4. Testing calibration...")
        # Use typical CCD pixel count
        num_pixels = 1024
        calibration = spec.get_calibration(num_pixels, pixel_width=16.0)
        print(f"   Calibration shape: {calibration.shape}")
        print(f"   Wavelength range: {calibration[0]:.2f} - {calibration[-1]:.2f} nm")
        print(f"   Dispersion: {(calibration[-1] - calibration[0]) / num_pixels:.4f} nm/pixel")

        print("\n[PASS] Spectrograph tests completed successfully")

    except Exception as e:
        print(f"\n[FAIL] Spectrograph test failed: {e}")
        raise

    finally:
        print("\n5. Shutting down spectrograph...")
        spec.shutdown()
        print("   Spectrograph shutdown complete")


def test_combined():
    """Test camera and spectrograph together."""
    from andor_pymeasure.instruments.andor_camera import AndorCamera
    from andor_pymeasure.instruments.andor_spectrograph import AndorSpectrograph

    print("\n" + "=" * 60)
    print("Testing Combined Camera + Spectrograph")
    print("=" * 60)

    cam = AndorCamera()
    spec = AndorSpectrograph()

    try:
        print("\n1. Initializing both devices...")
        cam.initialize()
        spec.initialize()

        print(f"\n2. Camera: {cam.xpixels}x{cam.ypixels}")
        print(f"   Spectrograph: {spec.info.num_gratings} gratings")

        print("\n3. Getting wavelength calibration for camera detector...")
        calibration = spec.get_calibration(cam.xpixels, cam.info.pixel_width)
        print(f"   Calibration for {cam.xpixels} pixels:")
        print(f"   {calibration[0]:.2f} - {calibration[-1]:.2f} nm")

        print("\n4. Acquiring spectrum with calibration...")
        cam.set_exposure(0.1)
        spectrum = cam.acquire_fvb()
        print(f"   Spectrum: {len(spectrum)} points")
        print(f"   Wavelength range: {calibration[0]:.2f} - {calibration[-1]:.2f} nm")

        print("\n[PASS] Combined tests completed successfully")

    except Exception as e:
        print(f"\n[FAIL] Combined test failed: {e}")
        raise

    finally:
        print("\n5. Shutting down...")
        cam.shutdown()
        spec.shutdown()
        print("   Shutdown complete")


def main():
    """Run all tests."""
    mock_mode = os.environ.get("ANDOR_MOCK", "0") == "1"
    if mock_mode:
        print("Running in MOCK mode (no hardware)")
        print("Note: Mock mode for PyMeasure instruments not yet implemented")
        print("Set ANDOR_MOCK=0 to test with real hardware")
        return

    print("=" * 60)
    print("Andor Instrument Tests")
    print("=" * 60)

    try:
        # Test camera
        test_camera()

        # Test spectrograph
        test_spectrograph()

        # Test combined
        test_combined()

        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
