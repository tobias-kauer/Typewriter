#!/usr/bin/env python3
"""Write text by briefly bridging row/column mux channels."""

import argparse
import queue
import select
import sys
import termios
import time
import tty

MUX_EN = 7

ROW_S0 = 15
ROW_S1 = 18
ROW_S2 = 23
ROW_S3 = 12

COL_S0 = 24
COL_S1 = 25
COL_S2 = 8
COL_S3 = 16

SHIFT_PIN = 1
USE_SHIFT_PIN = True

BRIDGE_TIME = 0.05
INTER_KEY_DELAY = 0.05
SETTLE_DELAY = 0.002
# Time for row/column select lines to settle before enabling the mux bridge.
MUX_CHANNEL_DELAY = 0.1
IDLE_POLL_DELAY = 0.01

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
SPECIAL_KEYS = tuple(
    sorted(
        (key for key in KEY_POSITIONS if key.startswith("KEY_")),
        key=len,
        reverse=True,
    )
)
SPECIAL_KEY_SEPARATORS = {" ", "\t", "\n", "\r", ","}


class NullOutput:
    def write(self, text):
        del text

    def flush(self):
        pass


NULL_OUTPUT = NullOutput()


def set_mux_channel(s0, s1, s2, channel, s3=None):
    if channel < 0 or channel > 15:
        raise ValueError(f"Mux channel must be between 0 and 15, got {channel}")

    s0.value = (channel >> 0) & 1
    s1.value = (channel >> 1) & 1
    s2.value = (channel >> 2) & 1

    if s3 is not None:
        s3.value = (channel >> 3) & 1


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


def wait_with_mux_idle(seconds):
    set_mux_bridge_active(False)
    set_shift(False)

    if seconds > 0:
        time.sleep(seconds)


def bridge_channels(
    row,
    col,
    bridge_time=BRIDGE_TIME,
    shifted=False,
    mux_channel_delay=MUX_CHANNEL_DELAY,
):
    set_mux_bridge_active(False)

    try:
        set_shift(shifted)

        set_mux_channel(ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, row, ROW_S3_LINE)
        set_mux_channel(COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, col, COL_S3_LINE)

        time.sleep(mux_channel_delay)
        set_mux_bridge_active(True)
        time.sleep(bridge_time)
    finally:
        wait_with_mux_idle(SETTLE_DELAY)


def get_key_position(key):
    if key not in KEY_POSITIONS:
        raise ValueError(f"No keymap position for {key!r}")

    return KEY_POSITIONS[key]


def write_key(key, bridge_time=BRIDGE_TIME, mux_channel_delay=MUX_CHANNEL_DELAY):
    row, col, shifted = get_key_position(key)
    bridge_channels(
        row,
        col,
        bridge_time=bridge_time,
        shifted=shifted,
        mux_channel_delay=mux_channel_delay,
    )


def special_key_at(text, index):
    for special_key in SPECIAL_KEYS:
        if text.startswith(special_key, index):
            return special_key

    return None


def next_non_separator_is_special_key(text, index):
    while index < len(text) and text[index] in SPECIAL_KEY_SEPARATORS:
        index += 1

    return special_key_at(text, index) is not None


def parse_key_tokens(text):
    tokens = []
    index = 0

    while index < len(text):
        matching_key = special_key_at(text, index)

        if text[index] in SPECIAL_KEY_SEPARATORS:
            previous_was_special = bool(tokens and tokens[-1] in SPECIAL_KEYS)

            if previous_was_special or next_non_separator_is_special_key(text, index):
                index += 1
                continue

        if matching_key is not None:
            tokens.append(matching_key)
            index += len(matching_key)
        else:
            tokens.append(text[index])
            index += 1

    return tokens


def write_tokens(
    tokens,
    bridge_time=BRIDGE_TIME,
    inter_key_delay=INTER_KEY_DELAY,
    mux_channel_delay=MUX_CHANNEL_DELAY,
):
    try:
        wait_with_mux_idle(SETTLE_DELAY)

        for index, token in enumerate(tokens):
            write_key(
                token,
                bridge_time=bridge_time,
                mux_channel_delay=mux_channel_delay,
            )

            if index < len(tokens) - 1:
                wait_with_mux_idle(inter_key_delay)

    finally:
        wait_with_mux_idle(SETTLE_DELAY)


def write_letters(
    text,
    bridge_time=BRIDGE_TIME,
    inter_key_delay=INTER_KEY_DELAY,
    mux_channel_delay=MUX_CHANNEL_DELAY,
):
    write_tokens(
        parse_key_tokens(text),
        bridge_time=bridge_time,
        inter_key_delay=inter_key_delay,
        mux_channel_delay=mux_channel_delay,
    )


def write_queue_item(
    item,
    bridge_time=BRIDGE_TIME,
    inter_key_delay=INTER_KEY_DELAY,
    mux_channel_delay=MUX_CHANNEL_DELAY,
):
    if item is None:
        return

    if isinstance(item, (list, tuple)):
        tokens = item
    elif item in KEY_POSITIONS:
        tokens = [item]
    else:
        tokens = parse_key_tokens(str(item))

    write_tokens(
        tokens,
        bridge_time=bridge_time,
        inter_key_delay=inter_key_delay,
        mux_channel_delay=mux_channel_delay,
    )


def debug_write_token(token, output_stream=sys.stdout):
    """Print one queued key token instead of driving the Raspberry Pi GPIO pins."""

    if token == "KEY_ENTER":
        output_stream.write("\n")
    elif token == "KEY_TAB":
        output_stream.write("\t")
    elif token.startswith("KEY_"):
        output_stream.write(f"[{token}]")
    else:
        output_stream.write(token)


def debug_write_queue_item(item, output_stream=sys.stdout):
    if item is None:
        return

    if isinstance(item, (list, tuple)):
        tokens = item
    elif item in KEY_POSITIONS:
        tokens = [item]
    else:
        tokens = parse_key_tokens(str(item))

    for token in tokens:
        debug_write_token(token, output_stream=output_stream)

    output_stream.flush()


def debug_write_loop(input_queue, stop_event=None, bridge_time=BRIDGE_TIME, echo=True):
    """Mock the hardware writer with terminal output.

    This is only used by main.py --debug on a development machine. The normal
    write_loop above still owns the active-low mux enable pin and GPIO bridge.
    """

    del bridge_time

    if echo:
        print("Debug writer ready. Output will be printed here.", flush=True)

    while stop_event is None or not stop_event.is_set() or not input_queue.empty():
        try:
            item = input_queue.get(timeout=IDLE_POLL_DELAY)
        except queue.Empty:
            continue

        try:
            if item is None:
                if stop_event is not None:
                    stop_event.set()

                break

            debug_write_queue_item(
                item,
                output_stream=sys.stdout if echo else NULL_OUTPUT,
            )

        finally:
            if hasattr(input_queue, "task_done"):
                input_queue.task_done()


def write_loop(
    input_queue,
    stop_event=None,
    bridge_time=BRIDGE_TIME,
    mux_channel_delay=MUX_CHANNEL_DELAY,
):
    setup_gpio()

    try:
        while stop_event is None or not stop_event.is_set() or not input_queue.empty():
            wait_with_mux_idle(0)

            try:
                item = input_queue.get(timeout=IDLE_POLL_DELAY)
            except queue.Empty:
                continue

            try:
                if item is None:
                    if stop_event is not None:
                        stop_event.set()

                    break

                write_queue_item(
                    item,
                    bridge_time=bridge_time,
                    mux_channel_delay=mux_channel_delay,
                )

            finally:
                if hasattr(input_queue, "task_done"):
                    input_queue.task_done()

    finally:
        cleanup_gpio()


def write_key_forever(
    key,
    bridge_time=BRIDGE_TIME,
    inter_key_delay=INTER_KEY_DELAY,
    mux_channel_delay=MUX_CHANNEL_DELAY,
):
    while True:
        write_key(
            key,
            bridge_time=bridge_time,
            mux_channel_delay=mux_channel_delay,
        )
        wait_with_mux_idle(inter_key_delay)


def read_terminal_key():
    key = sys.stdin.read(1)

    if key == "\x03":
        raise KeyboardInterrupt

    if key in ("\r", "\n"):
        return "KEY_ENTER"

    if key == "\t":
        return "KEY_TAB"

    if key in ("\x7f", "\b"):
        return "KEY_BACKSPACE"

    if key == "\x1b":
        if select.select([sys.stdin], [], [], 0)[0]:
            sequence = key + sys.stdin.read(1)

            if select.select([sys.stdin], [], [], 0)[0]:
                sequence += sys.stdin.read(1)

            if sequence == "\x1b[3":
                if select.select([sys.stdin], [], [], 0)[0]:
                    sequence += sys.stdin.read(1)

            if sequence == "\x1b[3~":
                return "KEY_DELETE"

        return None

    return key


def listen_for_keypresses(
    bridge_time=BRIDGE_TIME,
    mux_channel_delay=MUX_CHANNEL_DELAY,
):
    print("Listening. Press Ctrl+C to stop.")

    while True:
        wait_with_mux_idle(0)

        if not select.select([sys.stdin], [], [], IDLE_POLL_DELAY)[0]:
            continue

        key = read_terminal_key()

        if key is None:
            continue

        if key not in KEY_POSITIONS:
            print(f"Ignoring unmapped key: {key!r}")
            continue

        write_key(
            key,
            bridge_time=bridge_time,
            mux_channel_delay=mux_channel_delay,
        )


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


def setup_gpio():
    from gpiozero import OutputDevice

    global MUX_EN_LINE
    global ROW_S0_LINE, ROW_S1_LINE, ROW_S2_LINE, ROW_S3_LINE
    global COL_S0_LINE, COL_S1_LINE, COL_S2_LINE, COL_S3_LINE
    global SHIFT_LINE

    MUX_EN_LINE = OutputDevice(MUX_EN, initial_value=True)
    set_mux_bridge_active(False)

    ROW_S0_LINE = OutputDevice(ROW_S0, initial_value=False)
    ROW_S1_LINE = OutputDevice(ROW_S1, initial_value=False)
    ROW_S2_LINE = OutputDevice(ROW_S2, initial_value=False)
    ROW_S3_LINE = OutputDevice(ROW_S3, initial_value=False)

    COL_S0_LINE = OutputDevice(COL_S0, initial_value=False)
    COL_S1_LINE = OutputDevice(COL_S1, initial_value=False)
    COL_S2_LINE = OutputDevice(COL_S2, initial_value=False)
    COL_S3_LINE = OutputDevice(COL_S3, initial_value=False)

    if USE_SHIFT_PIN:
        SHIFT_LINE = OutputDevice(SHIFT_PIN, initial_value=True)

    set_mux_bridge_active(False)
    set_shift(False)


def cleanup_gpio():
    set_mux_bridge_active(False)
    set_shift(False)


def parse_args():
    parser = argparse.ArgumentParser(description="Listen for keypresses and write them.")
    parser.add_argument("text", nargs="*", help="Optional text to write once before listening")
    parser.add_argument(
        "--list-special-keys",
        action="store_true",
        help="Print matrix key names like KEY_BACKSPACE and exit",
    )
    parser.add_argument(
        "--show-tokens",
        action="store_true",
        help="Print the parsed key tokens and exit without using GPIO",
    )
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
        "--mux-channel-delay",
        type=float,
        default=MUX_CHANNEL_DELAY,
        help="Seconds to wait after selecting mux channels before enabling the bridge",
    )
    parser.add_argument(
        "--repeat-one",
        action="store_true",
        help="Keep writing the first given letter until stopped",
    )
    parser.add_argument(
        "--keep-high",
        action="store_true",
        help="Only keep GPIO 6 HIGH without listening",
    )
    parser.add_argument(
        "--write-once",
        action="store_true",
        help="Write the given text once and exit instead of listening",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.list_special_keys:
        print("\n".join(SPECIAL_KEYS))
        return

    if args.show_tokens:
        text = " ".join(args.text) if args.text else input("Text to write: ")
        print(parse_key_tokens(text))
        return

    setup_gpio()

    try:
        if args.keep_high:
            print(f"GPIO {MUX_EN} is HIGH. Press Ctrl+C to stop.")

            while True:
                wait_with_mux_idle(1)

        text = " ".join(args.text)

        if args.repeat_one:
            tokens = parse_key_tokens(text)

            if not tokens:
                raise ValueError("Give one letter when using --repeat-one")

            write_key_forever(
                tokens[0],
                bridge_time=args.bridge_time,
                inter_key_delay=args.key_delay,
                mux_channel_delay=args.mux_channel_delay,
            )

        if text:
            write_letters(
                text,
                bridge_time=args.bridge_time,
                inter_key_delay=args.key_delay,
                mux_channel_delay=args.mux_channel_delay,
            )

            if args.write_once:
                return

        run_in_raw_terminal(
            lambda: listen_for_keypresses(
                bridge_time=args.bridge_time,
                mux_channel_delay=args.mux_channel_delay,
            )
        )

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        cleanup_gpio()


if __name__ == "__main__":
    main()
