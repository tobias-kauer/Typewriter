#!/usr/bin/env python3
"""Multiplexer test utility for reader and writer matrix configurations."""

import argparse
import time

# Reader matrix pins for row/column scan tests
ROW_EN = 2
ROW_S0 = 3
ROW_S1 = 4
ROW_S2 = 17
ROW_SIG = 27

COL_EN = 22
COL_S0 = 10
COL_S1 = 9
COL_S2 = 11
COL_SIG = 0

# Writer matrix pins for bridge tests
MUX_EN = 7
WRITE_ROW_S0 = 15
WRITE_ROW_S1 = 18
WRITE_ROW_S2 = 23
WRITE_COL_S0 = 24
WRITE_COL_S1 = 25
WRITE_COL_S2 = 8
SHIFT_PIN = 1
USE_SHIFT_PIN = True

ROW_COUNT = 8
COL_COUNT = 8

DEBOUNCE_DELAY = 0.00002
SCAN_DELAY = 0.01
BRIDGE_TIME = 0.05
BRIDGE_DELAY = 0.1


def set_mux_channel(s0, s1, s2, channel):
    if channel < 0 or channel > 7:
        raise ValueError(f"Mux channel must be between 0 and 7, got {channel}")

    s0.value = (channel >> 0) & 1
    s1.value = (channel >> 1) & 1
    s2.value = (channel >> 2) & 1


# Reader scan functions

def setup_reader_gpio():
    from gpiozero import OutputDevice, InputDevice

    global ROW_EN_LINE, ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, ROW_SIG_LINE
    global COL_EN_LINE, COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, COL_SIG_LINE

    ROW_EN_LINE = OutputDevice(ROW_EN, initial_value=True)
    ROW_S0_LINE = OutputDevice(ROW_S0, initial_value=False)
    ROW_S1_LINE = OutputDevice(ROW_S1, initial_value=False)
    ROW_S2_LINE = OutputDevice(ROW_S2, initial_value=False)
    ROW_SIG_LINE = OutputDevice(ROW_SIG, initial_value=False)

    COL_EN_LINE = OutputDevice(COL_EN, initial_value=True)
    COL_S0_LINE = OutputDevice(COL_S0, initial_value=False)
    COL_S1_LINE = OutputDevice(COL_S1, initial_value=False)
    COL_S2_LINE = OutputDevice(COL_S2, initial_value=False)

    COL_SIG_LINE = InputDevice(COL_SIG, pull_up=True)

    disable_reader_muxes()
    ROW_SIG_LINE.off()

    print(
        f"Reader GPIO ready. Fast-scanning {ROW_COUNT} rows x {COL_COUNT} columns..."
    )


def disable_reader_muxes():
    ROW_EN_LINE.on()
    COL_EN_LINE.on()


def enable_reader_muxes():
    ROW_EN_LINE.off()
    COL_EN_LINE.off()


def cleanup_reader_gpio():
    disable_reader_muxes()
    ROW_SIG_LINE.off()


def scan_reader_channels():
    enable_reader_muxes()
    active_positions = []

    try:
        for row in range(ROW_COUNT):
            set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, row)
            time.sleep(DEBOUNCE_DELAY)

            for col in range(COL_COUNT):
                set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, col)
                time.sleep(DEBOUNCE_DELAY)

                if COL_SIG_LINE.value == 1:
                    active_positions.append((row, col))
                    print(f"ACTIVE: row={row}, col={col}")

    finally:
        disable_reader_muxes()

    return active_positions


# Writer bridge functions

def setup_writer_gpio():
    from gpiozero import OutputDevice

    global MUX_EN_LINE
    global WRITE_ROW_S0_LINE, WRITE_ROW_S1_LINE, WRITE_ROW_S2_LINE
    global WRITE_COL_S0_LINE, WRITE_COL_S1_LINE, WRITE_COL_S2_LINE
    global SHIFT_LINE

    MUX_EN_LINE = OutputDevice(MUX_EN, initial_value=True)

    WRITE_ROW_S0_LINE = OutputDevice(WRITE_ROW_S0, initial_value=False)
    WRITE_ROW_S1_LINE = OutputDevice(WRITE_ROW_S1, initial_value=False)
    WRITE_ROW_S2_LINE = OutputDevice(WRITE_ROW_S2, initial_value=False)

    WRITE_COL_S0_LINE = OutputDevice(WRITE_COL_S0, initial_value=False)
    WRITE_COL_S1_LINE = OutputDevice(WRITE_COL_S1, initial_value=False)
    WRITE_COL_S2_LINE = OutputDevice(WRITE_COL_S2, initial_value=False)

    if USE_SHIFT_PIN:
        SHIFT_LINE = OutputDevice(SHIFT_PIN, initial_value=True)

    set_mux_bridge_active(False)
    set_shift(False)

    print("Writer GPIO ready. Bridge scanning all row/column pairs...")


def set_mux_bridge_active(active):
    if active:
        MUX_EN_LINE.off()
    else:
        MUX_EN_LINE.on()


def set_shift(shifted):
    if not USE_SHIFT_PIN:
        if shifted:
            raise ValueError("Shifted key requested, but USE_SHIFT_PIN is disabled")
        return

    if shifted:
        SHIFT_LINE.off()
    else:
        SHIFT_LINE.on()


def cleanup_writer_gpio():
    set_mux_bridge_active(False)
    set_shift(False)


def bridge_channels(row, col, bridge_time=BRIDGE_TIME):
    set_mux_bridge_active(False)

    try:
        set_shift(False)
        set_mux_channel(WRITE_ROW_S0_LINE, WRITE_ROW_S1_LINE, WRITE_ROW_S2_LINE, row)
        set_mux_channel(WRITE_COL_S0_LINE, WRITE_COL_S1_LINE, WRITE_COL_S2_LINE, col)

        time.sleep(DEBOUNCE_DELAY)
        set_mux_bridge_active(True)
        time.sleep(bridge_time)
    finally:
        set_mux_bridge_active(False)
        set_shift(False)


def scan_writer_bridges():
    for row in range(ROW_COUNT):
        for col in range(COL_COUNT):
            print(f"BRIDGING row={row}, col={col}")
            bridge_channels(row, col)
            time.sleep(BRIDGE_DELAY)


def parse_args():
    parser = argparse.ArgumentParser(description="Run mux tests for reader and writer matrices.")
    parser.add_argument(
        "--mode",
        choices=("scan", "bridge"),
        default="scan",
        help="Choose scan mode for reader matrix or bridge mode for writer matrix.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Override the delay between scans or bridge steps.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.mode == "scan":
        if args.delay is not None:
            global SCAN_DELAY
            SCAN_DELAY = args.delay

        setup_reader_gpio()

        try:
            print("Starting reader mux scan... Press Ctrl+C to stop")
            while True:
                active = scan_reader_channels()
                print(f"Found {len(active)} active connections")
                print()
                time.sleep(SCAN_DELAY)

        except KeyboardInterrupt:
            print("\nStopped by user")

        finally:
            cleanup_reader_gpio()

    else:
        if args.delay is not None:
            global BRIDGE_DELAY
            BRIDGE_DELAY = args.delay

        setup_writer_gpio()

        try:
            print("Starting writer bridge test... Press Ctrl+C to stop")
            while True:
                scan_writer_bridges()
                print("Completed one pass through all channels")
                print()

        except KeyboardInterrupt:
            print("\nStopped by user")

        finally:
            cleanup_writer_gpio()


if __name__ == "__main__":
    main()
