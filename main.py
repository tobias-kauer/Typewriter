#!/usr/bin/env python3
"""Simple Raspberry Pi keyboard matrix scanner using gpiozero."""

import time
from gpiozero import OutputDevice, InputDevice

ROW_EN = 2
ROW_S0 = 3
ROW_S1 = 4
ROW_S2 = 5
ROW_S3 = 6
ROW_SIG = 26

COL_EN = 17
COL_S0 = 27
COL_S1 = 22
COL_S2 = 10
COL_S3 = 9
COL_SIG = 11

ROW_COUNT = 16
COL_COUNT = 16

TARGET_ROWS = list(range(ROW_COUNT))
TARGET_COLS = list(range(COL_COUNT))

DEBOUNCE_DELAY = 0.00002
SCAN_DELAY = 1.0


def set_mux_channel(s0, s1, s2, s3, channel):
    s0.value = (channel >> 0) & 1
    s1.value = (channel >> 1) & 1
    s2.value = (channel >> 2) & 1
    s3.value = (channel >> 3) & 1


def disable_muxes():
    ROW_EN_LINE.on()
    COL_EN_LINE.on()


def enable_muxes():
    ROW_EN_LINE.off()
    COL_EN_LINE.off()


def has_connection(row, col):
    disable_muxes()

    set_mux_channel(
        ROW_S0_LINE,
        ROW_S1_LINE,
        ROW_S2_LINE,
        ROW_S3_LINE,
        row,
    )

    set_mux_channel(
        COL_S0_LINE,
        COL_S1_LINE,
        COL_S2_LINE,
        COL_S3_LINE,
        col,
    )

    time.sleep(DEBOUNCE_DELAY)

    enable_muxes()

    time.sleep(DEBOUNCE_DELAY)

    connected = COL_SIG_LINE.value == 1

    disable_muxes()

    return connected


def scan_keyboard_matrix(rows, cols):
    print("Scan start")
    found_any = False

    for row in rows:
        for col in cols:
            if has_connection(row, col):
                found_any = True
                print(f"row={row}, col={col}")

    if not found_any:
        print("No connections detected")

    print("Scan end")


def setup_gpio():
    global ROW_EN_LINE, ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, ROW_S3_LINE
    global COL_EN_LINE, COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, COL_S3_LINE
    global ROW_SIG_LINE, COL_SIG_LINE

    ROW_EN_LINE = OutputDevice(ROW_EN, initial_value=True)
    ROW_S0_LINE = OutputDevice(ROW_S0, initial_value=False)
    ROW_S1_LINE = OutputDevice(ROW_S1, initial_value=False)
    ROW_S2_LINE = OutputDevice(ROW_S2, initial_value=False)
    ROW_S3_LINE = OutputDevice(ROW_S3, initial_value=False)

    ROW_SIG_LINE = OutputDevice(ROW_SIG, initial_value=False)

    COL_EN_LINE = OutputDevice(COL_EN, initial_value=True)
    COL_S0_LINE = OutputDevice(COL_S0, initial_value=False)
    COL_S1_LINE = OutputDevice(COL_S1, initial_value=False)
    COL_S2_LINE = OutputDevice(COL_S2, initial_value=False)
    COL_S3_LINE = OutputDevice(COL_S3, initial_value=False)

    COL_SIG_LINE = InputDevice(COL_SIG, pull_up=True)

    disable_muxes()
    ROW_SIG_LINE.off()

    print("Keyboard matrix scan ready")


def cleanup_gpio():
    disable_muxes()
    ROW_SIG_LINE.off()


def main():
    setup_gpio()

    try:
        while True:
            scan_keyboard_matrix(TARGET_ROWS, TARGET_COLS)
            time.sleep(SCAN_DELAY)

    except KeyboardInterrupt:
        print("Stopped by user")

    finally:
        cleanup_gpio()


if __name__ == "__main__":
    main()