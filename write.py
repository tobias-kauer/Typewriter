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

BRIDGE_TIME = 0.05
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


def wait_with_muxes_disabled(seconds):
    disable_muxes()
    set_shift(False)

    if seconds > 0:
        time.sleep(seconds)


def bridge_channels(row, col, bridge_time=BRIDGE_TIME, shifted=False):
    disable_muxes()

    try:
        set_shift(shifted)

        set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, row)
        set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, col)

        time.sleep(SETTLE_DELAY)
        enable_muxes()
        time.sleep(bridge_time)
    finally:
        wait_with_muxes_disabled(SETTLE_DELAY)


def get_key_position(key):
    if key not in KEY_POSITIONS:
        raise ValueError(f"No keymap position for {key!r}")

    return KEY_POSITIONS[key]


def write_key(key, bridge_time=BRIDGE_TIME):
    row, col, shifted = get_key_position(key)
    bridge_channels(row, col, bridge_time=bridge_time, shifted=shifted)


def write_letters(text, bridge_time=BRIDGE_TIME, inter_key_delay=INTER_KEY_DELAY):
    try:
        wait_with_muxes_disabled(SETTLE_DELAY)

        for index, letter in enumerate(text):
            write_key(letter, bridge_time=bridge_time)

            if index < len(text) - 1:
                wait_with_muxes_disabled(inter_key_delay)

    finally:
        wait_with_muxes_disabled(SETTLE_DELAY)


def write_key_forever(key, bridge_time=BRIDGE_TIME, inter_key_delay=INTER_KEY_DELAY):
    while True:
        write_key(key, bridge_time=bridge_time)
        wait_with_muxes_disabled(inter_key_delay)


def keep_muxes_disabled_forever():
    print(f"Done writing. GPIO {MUX_EN} is HIGH. Press Ctrl+C to stop.")

    while True:
        wait_with_muxes_disabled(1)


def setup_gpio():
    global MUX_EN_LINE
    global ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE
    global COL_S0_LINE, COL_S1_LINE, COL_S2_LINE
    global SHIFT_LINE

    MUX_EN_LINE = OutputDevice(MUX_EN, initial_value=True)
    MUX_EN_LINE.on()

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
        "--keep-high",
        action="store_true",
        help="Keep the program alive after writing so GPIO 6 stays driven HIGH",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    setup_gpio()

    try:
        text = " ".join(args.text) if args.text else input("Text to write: ")

        if args.repeat_one:
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

            if args.keep_high:
                keep_muxes_disabled_forever()

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        cleanup_gpio()


if __name__ == "__main__":
    main()
