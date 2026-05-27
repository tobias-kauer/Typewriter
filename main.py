#!/usr/bin/env python3
"""Simple Raspberry Pi keyboard matrix scanner using libgpiod."""

import sys
import time
import argparse

try:
    import gpiod
except ImportError:
    gpiod = None

GPIO_CHIP = "gpiochip0"

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

ROW_COUNT = 16
COL_COUNT = 16
TARGET_ROWS = list(range(ROW_COUNT))
TARGET_COLS = list(range(COL_COUNT))

DEBOUNCE_DELAY = 0.00002
SCAN_DELAY = 1.0


def request_output(chip, pin, initial=0):
    line = chip.get_line(pin)
    line.request(
        consumer="typewriter",
        type=gpiod.LINE_REQ_DIR_OUT,
        default_vals=[initial],
    )
    return line


def request_input_pullup(chip, pin):
    line = chip.get_line(pin)
    line.request(
        consumer="typewriter",
        type=gpiod.LINE_REQ_DIR_IN,
        flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP,
    )
    return line


def set_mux_channel(s0, s1, s2, s3, channel):
    s0.set_value((channel >> 0) & 1)
    s1.set_value((channel >> 1) & 1)
    s2.set_value((channel >> 2) & 1)
    s3.set_value((channel >> 3) & 1)


def disable_muxes():
    ROW_EN_LINE.set_value(1)
    COL_EN_LINE.set_value(1)
    # Try to use libgpiod; if unavailable or chip missing, fall back to dummy lines
    if gpiod is None:
        print("libgpiod Python module not available — running in simulation mode.")
        chip = None
    else:
        try:
            chip = gpiod.Chip(GPIO_CHIP)
        except (FileNotFoundError, OSError):
            print("GPIO chip not found — running in simulation mode.")
            chip = None

def enable_muxes():
    ROW_EN_LINE.set_value(0)
    COL_EN_LINE.set_value(0)


def has_connection(row, col):
    disable_muxes()
    set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, ROW_S3_LINE, row)
    set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, COL_S3_LINE, col)

    time.sleep(DEBOUNCE_DELAY)
    enable_muxes()
    time.sleep(DEBOUNCE_DELAY)

    connected = COL_SIG_LINE.get_value() == 0
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

    chip = gpiod.Chip(GPIO_CHIP)

    ROW_EN_LINE = request_output(chip, ROW_EN, initial=1)
    ROW_S0_LINE = request_output(chip, ROW_S0, initial=0)
    ROW_S1_LINE = request_output(chip, ROW_S1, initial=0)
    ROW_S2_LINE = request_output(chip, ROW_S2, initial=0)
    ROW_S3_LINE = request_output(chip, ROW_S3, initial=0)
    ROW_SIG_LINE = request_output(chip, ROW_SIG, initial=0)

    COL_EN_LINE = request_output(chip, COL_EN, initial=1)
    COL_S0_LINE = request_output(chip, COL_S0, initial=0)
    COL_S1_LINE = request_output(chip, COL_S1, initial=0)
    COL_S2_LINE = request_output(chip, COL_S2, initial=0)
    COL_S3_LINE = request_output(chip, COL_S3, initial=0)
    COL_SIG_LINE = request_input_pullup(chip, COL_SIG)

    disable_muxes()
    ROW_SIG_LINE.set_value(0)
    print("Keyboard matrix scan ready")


def main():
    setup_gpio()
    try:
        while True:
            scan_keyboard_matrix(TARGET_ROWS, TARGET_COLS)
            time.sleep(SCAN_DELAY)
    except KeyboardInterrupt:
        print("Stopped by user")


if __name__ == "__main__":
    main()
