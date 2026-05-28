#!/usr/bin/env python3
"""Write text by briefly bridging row/column mux channels."""

import argparse
import time
from gpiozero import OutputDevice

MUX_EN = 6

ROW_S0 = 7
ROW_S1 = 1
ROW_S2 = 12

COL_S0 = 16
COL_S1 = 20
COL_S2 = 21

SHIFT_PIN = 24
USE_SHIFT_PIN = True

BRIDGE_TIME = 10
INTER_KEY_DELAY = 0.05
SETTLE_DELAY = 0.00002

KEYMAP = (
    ("i", "z", "-", "", "KEY_MODE", "7", "q", "a"),
    ("k", "1", "ß", "", "KEY_BACKSPACE", "9", "s", "c"),
    ("m", "3", "", "", "KEY_DELETE", ",", "u", "e"),
    ("p", "6", " ", "", "", ".", "x", "h"),
    ("o", "5", "KEY_CODE", "", "KEY_TAB", "ö", "w", "g"),
    ("n", "4", "KEY_ENTER", "", "KEY_DOUBLE_ARROW", "ä", "v", "f"),
    ("l", "2", "$", "", "KEY_ROW_DELETE", "0", "t", "d"),
    ("j", "y", "ü", "", "KEY_CRAZY_ARROW", "8", "r", "b"),
)

KEYMAP_SHIFT = (
    ("I", "Z", "_", "", "", "/", "Q", "A"),
    ("K", "!", "?", "", "", ")", "S", "C"),
    ("M", "§", "", "", "", ",", "U", "E"),
    ("P", "&", "", "", "", ".", "X", "H"),
    ("O", "%", "", "", "", "", "W", "G"),
    ("N", "+", "", "", "", "", "V", "F"),
    ("L", "\"", "", "", "", "=", "T", "D"),
    ("J", "Y", "", "", "", "(", "R", "B"),
)


def build_key_positions():
    key_positions = {}

    for row, row_keys in enumerate(KEYMAP):
        for col, key in enumerate(row_keys):
            if key:
                key_positions.setdefault(key, (row, col, False))

    for row, row_keys in enumerate(KEYMAP_SHIFT):
        for col, key in enumerate(row_keys):
            if key:
                key_positions.setdefault(key, (row, col, True))

    return key_positions


KEY_POSITIONS = build_key_positions()


def set_mux_channel(s0, s1, s2, channel):
    if channel < 0 or channel > 7:
        raise ValueError(f"Mux channel must be between 0 and 7, got {channel}")

    s0.value = (channel >> 0) & 1
    s1.value = (channel >> 1) & 1
    s2.value = (channel >> 2) & 1


def high_low(line):
    return "HIGH" if line.value else "LOW"


def print_hold_debug(row, col):
    lines = [
        f"Holding bridge row={row}, col={col}",
        f"ROW S0 GPIO {ROW_S0}: {high_low(ROW_S0_LINE)}",
        f"ROW S1 GPIO {ROW_S1}: {high_low(ROW_S1_LINE)}",
        f"ROW S2 GPIO {ROW_S2}: {high_low(ROW_S2_LINE)}",
        f"COL S0 GPIO {COL_S0}: {high_low(COL_S0_LINE)}",
        f"COL S1 GPIO {COL_S1}: {high_low(COL_S1_LINE)}",
        f"COL S2 GPIO {COL_S2}: {high_low(COL_S2_LINE)}",
        f"MUX EN GPIO {MUX_EN}: {high_low(MUX_EN_LINE)} (LOW = enabled)",
    ]

    if USE_SHIFT_PIN:
        lines.append(f"SHIFT GPIO {SHIFT_PIN}: {high_low(SHIFT_LINE)}")

    print("\n".join(lines), flush=True)


def disable_muxes():
    MUX_EN_LINE.on()


def enable_muxes():
    MUX_EN_LINE.off()


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
    disable_muxes()
    set_shift(shifted)

    set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, row)
    set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, col)

    time.sleep(SETTLE_DELAY)
    enable_muxes()

    try:
        time.sleep(bridge_time)
    finally:
        disable_muxes()
        set_shift(False)
        time.sleep(SETTLE_DELAY)


def get_key_position(key):
    if key not in KEY_POSITIONS:
        raise ValueError(f"No keymap position for {key!r}")

    return KEY_POSITIONS[key]


def write_key(key, bridge_time=BRIDGE_TIME):
    row, col, shifted = get_key_position(key)
    bridge_channels(row, col, bridge_time=bridge_time, shifted=shifted)


def write_letters(text, bridge_time=BRIDGE_TIME, inter_key_delay=INTER_KEY_DELAY):
    for letter in text:
        write_key(letter, bridge_time=bridge_time)
        time.sleep(inter_key_delay)


def write_key_forever(key, bridge_time=BRIDGE_TIME, inter_key_delay=INTER_KEY_DELAY):
    while True:
        write_key(key, bridge_time=bridge_time)
        time.sleep(inter_key_delay)


def hold_channels_enabled(row, col):
    disable_muxes()
    set_shift(False)

    set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, row)
    set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, col)

    time.sleep(SETTLE_DELAY)
    enable_muxes()
    print_hold_debug(row, col)

    while True:
        time.sleep(1)


def setup_gpio():
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

    disable_muxes()
    set_shift(False)


def cleanup_gpio():
    disable_muxes()
    set_shift(False)


def parse_args():
    parser = argparse.ArgumentParser(description="Write text through the mux bridge.")
    parser.add_argument("text", nargs="*", help="Text to write")
    parser.add_argument(
        "--bridge-time",
        type=float,
        default=BRIDGE_TIME,
        help="Seconds each row/column bridge stays enabled",
    )
    parser.add_argument(
        "--key-delay",
        type=float,
        default=INTER_KEY_DELAY,
        help="Seconds to wait between letters",
    )
    parser.add_argument(
        "--repeat-one",
        action="store_true",
        help="Keep writing the first given letter until stopped",
    )
    parser.add_argument(
        "--hold",
        nargs=2,
        type=int,
        metavar=("ROW", "COL"),
        help="Enable one row/column bridge until stopped",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    text = ""

    if not args.hold:
        text = " ".join(args.text) if args.text else input("Text to write: ")

    setup_gpio()

    try:
        if args.hold:
            row, col = args.hold
            hold_channels_enabled(row, col)
        elif args.repeat_one:
            if not text:
                raise ValueError("Give one letter when using --repeat-one")

            write_key_forever(
                text[0],
                bridge_time=args.bridge_time,
                inter_key_delay=args.key_delay,
            )
        else:
            write_letters(
                text,
                bridge_time=args.bridge_time,
                inter_key_delay=args.key_delay,
            )

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        cleanup_gpio()


if __name__ == "__main__":
    main()
