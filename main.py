#!/usr/bin/env python3
"""Keyboard matrix scan for Raspberry Pi using two 16-channel muxes."""

import sys
import time


class GPIOBackendError(RuntimeError):
    pass


class GPIOBase:
    BCM = None
    IN = None
    OUT = None
    HIGH = 1
    LOW = 0
    PUD_OFF = None
    PUD_DOWN = None
    PUD_UP = None

    def setmode(self, mode):
        raise NotImplementedError

    def setwarnings(self, flag):
        raise NotImplementedError

    def setup(self, pin, mode, initial=None, pull_up_down=None):
        raise NotImplementedError

    def output(self, pin, value):
        raise NotImplementedError

    def input(self, pin):
        raise NotImplementedError

    def cleanup(self):
        raise NotImplementedError


class RPiGPIOBackend(GPIOBase):
    def __init__(self):
        try:
            import RPi.GPIO as real_gpio
        except ImportError as exc:
            raise GPIOBackendError("RPi.GPIO is not installed") from exc

        self.gpio = real_gpio
        self.BCM = real_gpio.BCM
        self.IN = real_gpio.IN
        self.OUT = real_gpio.OUT
        self.HIGH = real_gpio.HIGH
        self.LOW = real_gpio.LOW
        self.PUD_OFF = real_gpio.PUD_OFF
        self.PUD_DOWN = real_gpio.PUD_DOWN
        self.PUD_UP = real_gpio.PUD_UP

    def setmode(self, mode):
        self.gpio.setmode(mode)

    def setwarnings(self, flag):
        self.gpio.setwarnings(flag)

    def setup(self, pin, mode, initial=None, pull_up_down=None):
        if pull_up_down is not None:
            self.gpio.setup(pin, mode, pull_up_down=pull_up_down)
        elif initial is not None:
            self.gpio.setup(pin, mode, initial=initial)
        else:
            self.gpio.setup(pin, mode)

    def output(self, pin, value):
        self.gpio.output(pin, value)

    def input(self, pin):
        return self.gpio.input(pin)

    def cleanup(self):
        self.gpio.cleanup()


class PigpioBackend(GPIOBase):
    def __init__(self):
        try:
            import pigpio
        except ImportError as exc:
            raise GPIOBackendError("pigpio Python package is not installed") from exc

        self.pigpio = pigpio
        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise GPIOBackendError("pigpio daemon is not running; start it with `sudo pigpiod`")

        self.BCM = "BCM"
        self.IN = pigpio.INPUT
        self.OUT = pigpio.OUTPUT
        self.HIGH = 1
        self.LOW = 0
        self.PUD_OFF = pigpio.PUD_OFF
        self.PUD_DOWN = pigpio.PUD_DOWN
        self.PUD_UP = pigpio.PUD_UP

    def setmode(self, mode):
        if mode != self.BCM:
            raise ValueError("Pigpio backend only supports BCM numbering")

    def setwarnings(self, flag):
        pass

    def setup(self, pin, mode, initial=None, pull_up_down=None):
        self.pi.set_mode(pin, mode)
        if pull_up_down is not None:
            self.pi.set_pull_up_down(pin, pull_up_down)
        if initial is not None and mode == self.OUT:
            self.pi.write(pin, initial)

    def output(self, pin, value):
        self.pi.write(pin, value)

    def input(self, pin):
        return self.pi.read(pin)

    def cleanup(self):
        self.pi.stop()


def create_gpio_driver():
    try:
        backend = RPiGPIOBackend()
        backend.setmode(backend.BCM)
        backend.setwarnings(False)
        return backend
    except GPIOBackendError as exc:
        print(f"RPi.GPIO backend unavailable: {exc}")

    try:
        backend = PigpioBackend()
        backend.setmode(backend.BCM)
        backend.setwarnings(False)
        print("Using pigpio backend")
        return backend
    except GPIOBackendError as exc:
        print(f"pigpio backend unavailable: {exc}")

    raise SystemExit(
        "No supported GPIO backend available. Install RPi.GPIO or pigpio and run on Raspberry Pi with the correct permissions."
    )


GPIO = create_gpio_driver()

# Raspberry Pi BCM pin numbers for the row and column muxes.
# Replace these with the GPIO pins you actually wired on your Pi.
ROW_EN = 2
ROW_S0 = 3
ROW_S1 = 4
ROW_S2 = 5
ROW_S3 = 6
ROW_SIG = 7

COL_EN = 8
COL_S0 = 9
COL_S1 = 10
COL_S2 = 11
COL_S3 = 12
COL_SIG = 13

# Select the range of rows/columns to scan.
ROW_COUNT = 16
COL_COUNT = 16
TARGET_ROWS = list(range(ROW_COUNT))
TARGET_COLS = list(range(COL_COUNT))

DEBOUNCE_DELAY = 0.00002  # 20 microseconds
SCAN_DELAY = 1.0  # seconds between scans


def set_mux_channel(s0, s1, s2, s3, channel):
    GPIO.output(s0, (channel >> 0) & 1)
    GPIO.output(s1, (channel >> 1) & 1)
    GPIO.output(s2, (channel >> 2) & 1)
    GPIO.output(s3, (channel >> 3) & 1)


def disable_muxes():
    GPIO.output(ROW_EN, GPIO.HIGH)
    GPIO.output(COL_EN, GPIO.HIGH)


def enable_muxes():
    GPIO.output(ROW_EN, GPIO.LOW)
    GPIO.output(COL_EN, GPIO.LOW)


def float_signal_pins():
    GPIO.setup(ROW_SIG, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(COL_SIG, GPIO.IN)


def press_signal_pins():
    GPIO.setup(ROW_SIG, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(COL_SIG, GPIO.OUT, initial=GPIO.LOW)


def prepare_scan_signals():
    GPIO.setup(ROW_SIG, GPIO.OUT, initial=GPIO.LOW)
    GPIO.setup(COL_SIG, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def select_row_and_column(row, col):
    set_mux_channel(ROW_S0, ROW_S1, ROW_S2, ROW_S3, row)
    set_mux_channel(COL_S0, COL_S1, COL_S2, COL_S3, col)


def has_connection(row, col):
    disable_muxes()
    select_row_and_column(row, col)
    prepare_scan_signals()

    time.sleep(DEBOUNCE_DELAY)
    enable_muxes()
    time.sleep(DEBOUNCE_DELAY)

    connected = GPIO.input(COL_SIG) == GPIO.LOW

    disable_muxes()
    float_signal_pins()
    return connected


def scan_keyboard_matrix(rows, cols):
    found_any = False
    print("Scan start")

    for row in rows:
        for col in cols:
            if has_connection(row, col):
                found_any = True
                print(f"row={row}, col={col}")

    if not found_any:
        print("No connections detected")

    print("Scan end")


def setup_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    for pin in [
        ROW_EN,
        ROW_S0,
        ROW_S1,
        ROW_S2,
        ROW_S3,
        ROW_SIG,
        COL_EN,
        COL_S0,
        COL_S1,
        COL_S2,
        COL_S3,
        COL_SIG,
    ]:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    disable_muxes()
    float_signal_pins()
    select_row_and_column(TARGET_ROWS[0], TARGET_COLS[0])
    print("Keyboard matrix scan ready")


def cleanup_gpio():
    disable_muxes()
    float_signal_pins()
    GPIO.cleanup()


def main():
    setup_gpio()
    try:
        while True:
            scan_keyboard_matrix(TARGET_ROWS, TARGET_COLS)
            time.sleep(SCAN_DELAY)
    except KeyboardInterrupt:
        print("Stopping scan")
    finally:
        cleanup_gpio()


if __name__ == "__main__":
    main()
