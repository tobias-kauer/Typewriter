#!/usr/bin/env python3
"""Simple bridge test: sequentially enable every row/column pair."""

import time

MUX_EN = 7

ROW_S0 = 15
ROW_S1 = 18
ROW_S2 = 23

COL_S0 = 24
COL_S1 = 25
COL_S2 = 8

SHIFT_PIN = 1
USE_SHIFT_PIN = True

ROW_COUNT = 8
COL_COUNT = 8

BRIDGE_TIME = 0.05
SETTLE_DELAY = 0.00002
SCAN_DELAY = 0.1


def set_mux_channel(s0, s1, s2, channel):
    if channel < 0 or channel > 7:
        raise ValueError(f"Mux channel must be between 0 and 7, got {channel}")

    s0.value = (channel >> 0) & 1
    s1.value = (channel >> 1) & 1
    s2.value = (channel >> 2) & 1


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


def bridge_channels(row, col, bridge_time=BRIDGE_TIME, shifted=False):
    set_mux_bridge_active(False)

    try:
        set_shift(shifted)
        set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, row)
        set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, col)

        time.sleep(SETTLE_DELAY)
        set_mux_bridge_active(True)
        time.sleep(bridge_time)
    finally:
        set_mux_bridge_active(False)
        set_shift(False)


def setup_gpio():
    from gpiozero import OutputDevice

    global MUX_EN_LINE
    global ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE
    global COL_S0_LINE, COL_S1_LINE, COL_S2_LINE
    global SHIFT_LINE

    MUX_EN_LINE = OutputDevice(MUX_EN, initial_value=True)

    ROW_S0_LINE = OutputDevice(ROW_S0, initial_value=False)
    ROW_S1_LINE = OutputDevice(ROW_S1, initial_value=False)
    ROW_S2_LINE = OutputDevice(ROW_S2, initial_value=False)

    COL_S0_LINE = OutputDevice(COL_S0, initial_value=False)
    COL_S1_LINE = OutputDevice(COL_S1, initial_value=False)
    COL_S2_LINE = OutputDevice(COL_S2, initial_value=False)

    if USE_SHIFT_PIN:
        SHIFT_LINE = OutputDevice(SHIFT_PIN, initial_value=True)

    set_mux_bridge_active(False)
    set_shift(False)
    print("GPIO ready. Bridge scanning all row/column pairs...")


def cleanup_gpio():
    set_mux_bridge_active(False)
    set_shift(False)


def scan_all_bridges():
    for row in range(ROW_COUNT):
        for col in range(COL_COUNT):
            print(f"BRIDGING row={row}, col={col}")
            bridge_channels(row, col, bridge_time=BRIDGE_TIME, shifted=False)
            time.sleep(SCAN_DELAY)


def main():
    setup_gpio()

    try:
        print("Starting bridge test... Press Ctrl+C to stop")
        while True:
            scan_all_bridges()
            print("Completed one pass through all channels")
            print()

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        cleanup_gpio()


if __name__ == "__main__":
    main()
