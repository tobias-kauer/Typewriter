#!/usr/bin/env python3
"""Fast test program: continuously scan all row/column mux channels."""

import select
import sys
import termios
import time
import tty

ROW_EN = 2
ROW_S0 = 3
ROW_S1 = 4
ROW_S2 = 17
ROW_S3 = 5
ROW_SIG = 27

COL_EN = 22
COL_S0 = 10
COL_S1 = 9
COL_S2 = 11
COL_S3 = 6
COL_SIG = 0

SHIFT_PIN = 14

ROW_COUNT = 8
COL_COUNT = 8

TARGET_ROWS = range(ROW_COUNT)
TARGET_COLS = range(COL_COUNT)

DEBOUNCE_DELAY = 0.00002
SAME_PRESS_DELAY = 0.1
SCAN_DELAY = 0.01

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
    ("P", "&", "", "", "", ":", "X", "H"),
    ("O", "%", "", "", "", "", "W", "G"),
    ("N", "+", "", "", "", "", "V", "F"),
    ("L", "\"", "", "", "", "=", "T", "D"),
    ("J", "Y", "", "", "", "(", "R", "B"),
)

ACTIVE_PRESSES = {}

READABLE_KEYS = {
    key
    for keymap in (KEYMAP, KEYMAP_SHIFT)
    for row_keys in keymap
    for key in row_keys
    if key
}

# Debug key aliases used by main.py --debug. These let a normal Mac keyboard
# produce the typewriter-only matrix keys without touching the GPIO hardware.
DEBUG_CONTROL_KEYS = {
    "\x07": "KEY_CODE",  # Ctrl+G starts autocomplete in main.py --autocomplete.
    "\x18": "KEY_MODE",  # Ctrl+X stops autocomplete / starts a new session.
}

DEBUG_ESCAPE_SEQUENCES = {
    "\x1b[3~": "KEY_DELETE",
    "\x1bOP": "KEY_CODE",  # F1, common terminal sequence.
    "\x1b[11~": "KEY_CODE",
    "\x1bOQ": "KEY_MODE",  # F2, common terminal sequence.
    "\x1b[12~": "KEY_MODE",
}


def set_mux_channel(s0, s1, s2, channel, s3=None):
    s0.value = (channel >> 0) & 1
    s1.value = (channel >> 1) & 1
    s2.value = (channel >> 2) & 1

    if s3 is not None:
        s3.value = (channel >> 3) & 1


def disable_muxes():
    ROW_EN_LINE.on()
    COL_EN_LINE.on()


def enable_muxes():
    ROW_EN_LINE.off()
    COL_EN_LINE.off()


def has_connection(row, col):
    disable_muxes()

    set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, row, ROW_S3_LINE)
    set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, col, COL_S3_LINE)

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
    return SHIFT_LINE.value == 1


def is_printable_key(key):
    return key is not None and not key.startswith("KEY_")


def scan_pressed_positions(rows, cols):
    pressed_positions = []

    enable_muxes()

    try:
        for row in rows:
            set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, row, ROW_S3_LINE)
            time.sleep(DEBOUNCE_DELAY)

            for col in cols:
                set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, col, COL_S3_LINE)
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


def read_keys(rows=TARGET_ROWS, cols=TARGET_COLS):
    shifted = shift_is_pressed()
    keys = []

    for row, col in get_new_press_positions(rows, cols):
        key = get_key(row, col, shifted)

        if key is not None:
            keys.append(key)

    return keys


def read_loop(output_queue, stop_event=None, rows=TARGET_ROWS, cols=TARGET_COLS):
    setup_gpio()

    try:
        while stop_event is None or not stop_event.is_set():
            for key in read_keys(rows, cols):
                output_queue.put(key)

            time.sleep(SCAN_DELAY)

    finally:
        cleanup_gpio()


def read_escape_sequence():
    sequence = "\x1b"

    while select.select([sys.stdin], [], [], 0.01)[0]:
        sequence += sys.stdin.read(1)

        if sequence in DEBUG_ESCAPE_SEQUENCES:
            return DEBUG_ESCAPE_SEQUENCES[sequence]

        if len(sequence) >= 6:
            break

    return DEBUG_ESCAPE_SEQUENCES.get(sequence)


def read_terminal_key():
    key = sys.stdin.read(1)

    if key == "":
        raise EOFError

    if key == "\x03":
        raise KeyboardInterrupt

    if key in DEBUG_CONTROL_KEYS:
        return DEBUG_CONTROL_KEYS[key]

    if key in ("\r", "\n"):
        return "KEY_ENTER"

    if key == "\t":
        return "KEY_TAB"

    if key in ("\x7f", "\b"):
        return "KEY_BACKSPACE"

    if key == "\x1b":
        return read_escape_sequence()

    return key


def debug_read_loop(output_queue, stop_event=None):
    """Mock the hardware reader with the computer keyboard.

    This is only used by main.py --debug on a development machine. The normal
    read_loop above still owns all Raspberry Pi GPIO setup and scanning.
    """

    print(
        "Debug reader ready. Type normally. Ctrl+G/F1 = KEY_CODE, "
        "Ctrl+X = KEY_MODE, Ctrl+C = stop.",
        flush=True,
    )

    def read_until_stopped():
        while stop_event is None or not stop_event.is_set():
            if not select.select([sys.stdin], [], [], SCAN_DELAY)[0]:
                continue

            key = read_terminal_key()

            if key is None:
                continue

            if key not in READABLE_KEYS:
                print(f"DEBUG READ: ignoring unmapped key {key!r}", flush=True)
                continue

            output_queue.put(key)

    try:
        run_in_raw_terminal(read_until_stopped)
    except (KeyboardInterrupt, EOFError):
        if stop_event is not None:
            stop_event.set()


def run_in_raw_terminal(callback):
    if not sys.stdin.isatty():
        callback()
        return

    old_settings = termios.tcgetattr(sys.stdin)

    try:
        tty.setcbreak(sys.stdin.fileno())
        callback()
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


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
    from gpiozero import OutputDevice, InputDevice

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
