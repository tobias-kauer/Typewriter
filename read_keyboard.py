#!/usr/bin/env python3
"""Fast test program: continuously scan all row/column mux channels."""

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

SHIFT_PIN = 13

ROW_COUNT = 8
COL_COUNT = 8

TARGET_ROWS = range(ROW_COUNT)
TARGET_COLS = range(COL_COUNT)

DEBOUNCE_DELAY = 0.00002
SAME_PRESS_DELAY = 0.25

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

ACTIVE_PRESSES = {}


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

    set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, ROW_S3_LINE, row)
    set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, COL_S3_LINE, col)

    time.sleep(DEBOUNCE_DELAY)
    enable_muxes()
    time.sleep(DEBOUNCE_DELAY)

    connected = COL_SIG_LINE.value == 1

    disable_muxes()

    return connected


def get_key(row, col, shifted=False):
    if row < 0 or row >= len(KEYMAP):
        return None

    if col < 0 or col >= len(KEYMAP[row]):
        return None

    if shifted:
        shift_key = KEYMAP_SHIFT[row][col]

        if shift_key:
            return shift_key

    return KEYMAP[row][col] or None


def shift_is_pressed():
    return SHIFT_LINE.value == 0


def is_printable_key(key):
    return key is not None and not key.startswith("KEY_")


def scan_pressed_positions(rows, cols):
    pressed_positions = []

    enable_muxes()

    try:
        for row in rows:
            set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, ROW_S3_LINE, row)
            time.sleep(DEBOUNCE_DELAY)

            for col in cols:
                set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, COL_S3_LINE, col)
                time.sleep(DEBOUNCE_DELAY)

                if COL_SIG_LINE.value == 1:
                    pressed_positions.append((row, col))

    finally:
        disable_muxes()

    return pressed_positions


def get_new_press_positions(rows, cols):
    now = time.monotonic()
    pressed_positions = scan_pressed_positions(rows, cols)
    pressed_set = set(pressed_positions)
    new_positions = []

    for position in pressed_positions:
        if position not in ACTIVE_PRESSES:
            new_positions.append(position)

        ACTIVE_PRESSES[position] = now

    for position, last_seen in list(ACTIVE_PRESSES.items()):
        if position not in pressed_set and now - last_seen >= SAME_PRESS_DELAY:
            del ACTIVE_PRESSES[position]

    return new_positions


def read_letters_as_string(rows=TARGET_ROWS, cols=TARGET_COLS):
    shifted = shift_is_pressed()
    letters = []

    for row, col in get_new_press_positions(rows, cols):
        key = get_key(row, col, shifted)

        if is_printable_key(key):
            letters.append(key)

    return "".join(letters)


def print_key_for_connection(row, col, shifted=False):
    key = get_key(row, col, shifted)

    if key is None:
        print(f"CONNECTED row={row}, col={col} -> no mapped key")
        return

    print(f"CONNECTED row={row}, col={col} -> {key}")


def scan_connections(rows, cols):
    shifted = shift_is_pressed()

    for row, col in get_new_press_positions(rows, cols):
        print_key_for_connection(row, col, shifted=shifted)


def setup_gpio():
    global ROW_EN_LINE, ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, ROW_S3_LINE
    global COL_EN_LINE, COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, COL_S3_LINE
    global ROW_SIG_LINE, COL_SIG_LINE, SHIFT_LINE

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
    SHIFT_LINE = InputDevice(SHIFT_PIN, pull_up=True)

    disable_muxes()
    ROW_SIG_LINE.off()

    print(
        f"GPIO ready. Fast-scanning {ROW_COUNT} rows x {COL_COUNT} columns..."
        f" Shift on GPIO {SHIFT_PIN} is active when grounded."
    )


def cleanup_gpio():
    disable_muxes()
    ROW_SIG_LINE.off()


def main():
    setup_gpio()

    try:
        while True:
            scan_connections(TARGET_ROWS, TARGET_COLS)

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        cleanup_gpio()


if __name__ == "__main__":
    main()
