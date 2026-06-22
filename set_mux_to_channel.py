#!/usr/bin/env python3
"""Interactive test utility: set all mux selector lines to one channel and enable them."""

import argparse
import sys
import time

from gpiozero import OutputDevice

# Reader matrix pins
ROW_EN = 2
ROW_S0 = 3
ROW_S1 = 4
ROW_S2 = 17
COL_EN = 22
COL_S0 = 10
COL_S1 = 9
COL_S2 = 11

# Writer matrix pins
MUX_EN = 7
WRITE_ROW_S0 = 15
WRITE_ROW_S1 = 18
WRITE_ROW_S2 = 23
WRITE_COL_S0 = 24
WRITE_COL_S1 = 25
WRITE_COL_S2 = 8
SHIFT_PIN = 1
USE_SHIFT_PIN = True

CHANNEL_MIN = 0
CHANNEL_MAX = 7


def parse_args():
    parser = argparse.ArgumentParser(
        description="Set all mux channels to a user-selected channel and enable them."
    )
    parser.add_argument(
        "--mode",
        choices=("reader", "writer", "both"),
        default="both",
        help="Which mux system to test.",
    )
    return parser.parse_args()


def setup_reader_gpio():
    global ROW_EN_LINE, ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE
    global COL_EN_LINE, COL_S0_LINE, COL_S1_LINE, COL_S2_LINE

    ROW_EN_LINE = OutputDevice(ROW_EN, initial_value=True)
    ROW_S0_LINE = OutputDevice(ROW_S0, initial_value=False)
    ROW_S1_LINE = OutputDevice(ROW_S1, initial_value=False)
    ROW_S2_LINE = OutputDevice(ROW_S2, initial_value=False)

    COL_EN_LINE = OutputDevice(COL_EN, initial_value=True)
    COL_S0_LINE = OutputDevice(COL_S0, initial_value=False)
    COL_S1_LINE = OutputDevice(COL_S1, initial_value=False)
    COL_S2_LINE = OutputDevice(COL_S2, initial_value=False)

    print("Reader GPIO ready.")


def cleanup_reader_gpio():
    ROW_EN_LINE.on()
    COL_EN_LINE.on()


def setup_writer_gpio():
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

    print("Writer GPIO ready.")


def cleanup_writer_gpio():
    MUX_EN_LINE.on()
    if USE_SHIFT_PIN:
        SHIFT_LINE.on()


def set_mux_channel(s0, s1, s2, channel):
    s0.value = (channel >> 0) & 1
    s1.value = (channel >> 1) & 1
    s2.value = (channel >> 2) & 1


def format_pin_state(pin_name, pin_device):
    return f"{pin_name}={'HIGH' if pin_device.value else 'LOW'}"


def enable_reader_muxes(channel):
    set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, channel)
    set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, channel)
    ROW_EN_LINE.off()
    COL_EN_LINE.off()

    print(f"Reader mux enabled on channel {channel}")
    print(
        "Reader pin states:",
        format_pin_state("ROW_EN", ROW_EN_LINE),
        format_pin_state("ROW_S0", ROW_S0_LINE),
        format_pin_state("ROW_S1", ROW_S1_LINE),
        format_pin_state("ROW_S2", ROW_S2_LINE),
        format_pin_state("COL_EN", COL_EN_LINE),
        format_pin_state("COL_S0", COL_S0_LINE),
        format_pin_state("COL_S1", COL_S1_LINE),
        format_pin_state("COL_S2", COL_S2_LINE),
    )


def enable_writer_muxes(channel):
    set_mux_channel(WRITE_ROW_S0_LINE, WRITE_ROW_S1_LINE, WRITE_ROW_S2_LINE, channel)
    set_mux_channel(WRITE_COL_S0_LINE, WRITE_COL_S1_LINE, WRITE_COL_S2_LINE, channel)
    if USE_SHIFT_PIN:
        SHIFT_LINE.on()
    MUX_EN_LINE.off()

    print(f"Writer mux enabled on channel {channel}")
    print(
        "Writer pin states:",
        format_pin_state("MUX_EN", MUX_EN_LINE),
        format_pin_state("ROW_S0", WRITE_ROW_S0_LINE),
        format_pin_state("ROW_S1", WRITE_ROW_S1_LINE),
        format_pin_state("ROW_S2", WRITE_ROW_S2_LINE),
        format_pin_state("COL_S0", WRITE_COL_S0_LINE),
        format_pin_state("COL_S1", WRITE_COL_S1_LINE),
        format_pin_state("COL_S2", WRITE_COL_S2_LINE),
        format_pin_state("SHIFT", SHIFT_LINE) if USE_SHIFT_PIN else "SHIFT=unused",
    )


def interactive_loop(mode):
    prompt = (
        "Enter channel 0-7 to set all mux selectors, or 'q' to quit: "
    )

    while True:
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            return

        if not line:
            continue

        if line.lower() in ("q", "quit", "exit"):
            print("Exiting.")
            return

        if not line.isdigit():
            print("Please enter a number between 0 and 7.")
            continue

        channel = int(line)

        if channel < CHANNEL_MIN or channel > CHANNEL_MAX:
            print("Channel must be between 0 and 7.")
            continue

        if mode in ("reader", "both"):
            enable_reader_muxes(channel)

        if mode in ("writer", "both"):
            enable_writer_muxes(channel)

        print("All mux outputs set. Change channel or press q to stop.")


def main():
    args = parse_args()

    try:
        if args.mode in ("reader", "both"):
            setup_reader_gpio()

        if args.mode in ("writer", "both"):
            setup_writer_gpio()

        print(f"Mode: {args.mode}")
        interactive_loop(args.mode)

    finally:
        if args.mode in ("reader", "both"):
            cleanup_reader_gpio()

        if args.mode in ("writer", "both"):
            cleanup_writer_gpio()


if __name__ == "__main__":
    main()
