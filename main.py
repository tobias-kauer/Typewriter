#!/usr/bin/env python3
"""Main program: read keys, process them, and write the result."""

import argparse
import queue
import sys
import threading
import time
from datetime import datetime

import autocomplete
import read
import write

AUTOCOMPLETE_START_KEY = "KEY_CODE"
AUTOCOMPLETE_STOP_KEY = "KEY_MODE"
SESSION_START_TEXTS = (
    "Review No. {session} - {timestamp}\n ",
)

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
READ_COLOR = "\033[38;5;245m"
TYPED_COLOR = "\033[38;5;39m"
GENERATED_COLOR = "\033[38;5;114m"
SESSION_COLOR = "\033[38;5;45m"
AUTOCOMPLETE_COLOR = "\033[38;5;221m"
LLM_COLOR = "\033[38;5;183m"
ERROR_COLOR = "\033[38;5;203m"


class TerminalTextDisplay:
    """Terminal-only display for typed text, autocomplete, and LLM status.

    The input/output backend is selected separately. In hardware mode this
    mirrors the typewriter activity in the terminal; in debug mode it shows the
    same activity while read.py/write.py use terminal mocks.
    """

    def __init__(self, output_stream=sys.stdout, use_color=None):
        self.output_stream = output_stream
        self.use_color = output_stream.isatty() if use_color is None else use_color
        self.segments = []
        self.lock = threading.Lock()

    def color(self, text, ansi_color):
        if not self.use_color:
            return text

        return f"{ansi_color}{text}{RESET}"

    def log(self, label, message, color=READ_COLOR):
        with self.lock:
            self._log(label, message, color)

    def read(self, key):
        self.log("READ", repr(key), READ_COLOR)

    def autocomplete_prompt(self, prompt):
        with self.lock:
            self._log("AUTOCOMPLETE PROMPT", repr(prompt), AUTOCOMPLETE_COLOR)
            self._render_text()

    def llm_config(self, mode, model):
        """Display LLM mode and model being used."""
        config_msg = f"mode={mode}, model={model}"
        self.log("LLM CONFIG", config_msg, LLM_COLOR)

    def llm_backend(self, backend):
        """Display which backend is actually processing the prompt."""
        backend_msg = f"using {backend} backend"
        self.log("LLM BACKEND", backend_msg, LLM_COLOR)

    def llm_prompt(self, prompt):
        with self.lock:
            self._block("LLM PROMPT SENT", prompt, LLM_COLOR)

    def llm_reply(self, reply, partial=False):
        label = "LLM RAW REPLY"

        if partial:
            label += " PARTIAL"

        with self.lock:
            self._block(label, reply or "(empty)", LLM_COLOR)

    def llm_response_time(self, seconds, attempt, partial=False):
        message = f"attempt {attempt}: {seconds:.2f}s"

        if partial:
            message += " partial"

        self.log("LLM RESPONSE TIME", message, LLM_COLOR)

    def autocomplete_out(self, chunk):
        with self.lock:
            self._append_text("generated", chunk)
            self._log("AUTOCOMPLETE OUT", repr(chunk), AUTOCOMPLETE_COLOR)
            self._render_text()

    def autocomplete_error(self, error):
        with self.lock:
            self._log("AUTOCOMPLETE ERROR", str(error), ERROR_COLOR)
            self._render_text()

    def autocomplete_status(self, message):
        with self.lock:
            self._log("AUTOCOMPLETE", message, AUTOCOMPLETE_COLOR)
            self._render_text()

    def session_start(self, session_number, start_text):
        with self.lock:
            self.segments = []
            self._log("SESSION", f"start {session_number}", SESSION_COLOR)

            if start_text:
                self._append_text("session", start_text)

            self._render_text()

    def typed_key(self, key):
        text = key_to_prompt_text(key)

        with self.lock:
            if key == "KEY_BACKSPACE":
                self._pop_last_character()
                self._render_text()
            elif text:
                self._append_text("typed", text)
                self._render_text()

    def _log(self, label, message, color):
        styled_label = self.color(label.ljust(20), color)
        print(f"{styled_label} {message}", file=self.output_stream, flush=True)

    def _block(self, label, text, color):
        styled_label = self.color(label, color)
        border = self.color("-" * len(label), DIM)
        print(styled_label, file=self.output_stream)
        print(border, file=self.output_stream)
        print(text, file=self.output_stream)
        print(border, file=self.output_stream, flush=True)

    def _append_text(self, source, text):
        if not text:
            return

        if self.segments and self.segments[-1][0] == source:
            previous_source, previous_text = self.segments[-1]
            self.segments[-1] = (previous_source, previous_text + text)
        else:
            self.segments.append((source, text))

    def _pop_last_character(self):
        while self.segments:
            source, text = self.segments[-1]

            if text:
                text = text[:-1]

            if text:
                self.segments[-1] = (source, text)
                return

            self.segments.pop()

    def _render_text(self):
        print(self.color("TEXT SO FAR", BOLD), file=self.output_stream)

        if not self.segments:
            print(f"  {self.color('(empty)', DIM)}", file=self.output_stream, flush=True)
            print(file=self.output_stream, flush=True)
            return

        rendered = "".join(
            self.color(text, self._segment_color(source))
            for source, text in self.segments
        )
        rendered = rendered.replace("\t", "    ")

        for line in rendered.split("\n"):
            print(f"  {line}", file=self.output_stream)

        print(file=self.output_stream)
        self.output_stream.flush()

    def _segment_color(self, source):
        if source == "typed":
            return TYPED_COLOR

        if source == "generated":
            return GENERATED_COLOR

        return SESSION_COLOR


def generate_autocomplete_response(prompt):
    return autocomplete.generate_text(prompt)


def write_autocomplete_response(write_queue, prompt):
    response = generate_autocomplete_response(prompt)
    enqueue_write_output(write_queue, response)
    return response


def process_read_key(key):
    return key


def key_to_prompt_text(key):
    if key == "KEY_ENTER":
        return "\n"

    if key == "KEY_TAB":
        return "\t"

    if key.startswith("KEY_"):
        return ""

    return key


def append_prompt_text(prompt_buffer, text):
    prompt_buffer.extend(text)


def update_prompt_buffer(prompt_buffer, key):
    if key == "KEY_BACKSPACE":
        if prompt_buffer:
            prompt_buffer.pop()

        return

    text = key_to_prompt_text(key)

    if text:
        append_prompt_text(prompt_buffer, text)


def enqueue_write_output(write_queue, output):
    if output is None:
        return

    if isinstance(output, (list, tuple)):
        for item in output:
            write_queue.put(item)
    else:
        write_queue.put(output)


def clear_queue(target_queue):
    with target_queue.mutex:
        target_queue.queue.clear()


def build_session_start_text(session_number):
    if not SESSION_START_TEXTS:
        return ""

    started_at = datetime.now()
    template = SESSION_START_TEXTS[(session_number - 1) % len(SESSION_START_TEXTS)]
    return template.format(
        session=session_number,
        date=started_at.strftime("%Y-%m-%d"),
        exact_time=started_at.strftime("%H:%M:%S"),
        timestamp=started_at.strftime("%Y-%m-%d %H:%M:%S"),
    )


def stream_autocomplete_to_writer(
    prompt,
    write_queue,
    autocomplete_stop_event,
    debug_display=None,
    generated_text_callback=None,
):
    prompt_attempts = [
        autocomplete.build_prompt(prompt),
        autocomplete.build_retry_prompt(prompt),
    ]

    try:
        emitted_text = False
        raw_reply_parts = []
        attempt_started_at = None
        attempt_number = None

        for attempt_index, prompt_text in enumerate(prompt_attempts):
            raw_reply_parts = []
            attempt_number = attempt_index + 1

            if debug_display is not None:
                debug_display.llm_prompt(prompt_text)

            attempt_started_at = time.monotonic()

            for chunk in autocomplete.generate_text_stream(
                prompt,
                stop_event=autocomplete_stop_event,
                raw_chunk_callback=(
                    raw_reply_parts.append if debug_display is not None else None
                ),
                prompt_text=prompt_text,
                mode=autocomplete.ACTIVE_MODE,
                api_key=autocomplete.OPENAI_API_KEY,
                openai_model=autocomplete.OPENAI_MODEL,
                backend_callback=(
                    debug_display.llm_backend if debug_display is not None else None
                ),
            ):
                if autocomplete_stop_event.is_set():
                    break

                emitted_text = True

                if (
                    generated_text_callback is not None
                    and generated_text_callback(chunk) is False
                ):
                    continue

                if debug_display is not None:
                    debug_display.autocomplete_out(chunk)
                else:
                    print(f"AUTOCOMPLETE OUT: {chunk!r}", flush=True)

                enqueue_write_output(write_queue, chunk)

            if debug_display is not None:
                elapsed = time.monotonic() - attempt_started_at
                debug_display.llm_reply(
                    "".join(raw_reply_parts),
                    partial=autocomplete_stop_event.is_set(),
                )
                debug_display.llm_response_time(
                    elapsed,
                    attempt_number,
                    partial=autocomplete_stop_event.is_set(),
                )

            if emitted_text or autocomplete_stop_event.is_set():
                break

            if attempt_index < len(prompt_attempts) - 1:
                if debug_display is not None:
                    debug_display.autocomplete_status(
                        "no writable continuation, retrying"
                    )
                else:
                    print(
                        "AUTOCOMPLETE: no writable continuation, retrying",
                        flush=True,
                    )

        if not emitted_text and not autocomplete_stop_event.is_set():
            if debug_display is not None:
                debug_display.autocomplete_status("no writable continuation")
            else:
                print("AUTOCOMPLETE: no writable continuation", flush=True)

    except autocomplete.AutocompleteError as error:
        if debug_display is not None and attempt_started_at is not None:
            debug_display.llm_response_time(
                time.monotonic() - attempt_started_at,
                attempt_number,
                partial=True,
            )

        if debug_display is not None and raw_reply_parts:
            debug_display.llm_reply("".join(raw_reply_parts), partial=True)

        if debug_display is not None:
            debug_display.autocomplete_error(error)
        else:
            print(f"AUTOCOMPLETE ERROR: {error}", flush=True)


def start_autocomplete_thread(
    prompt,
    write_queue,
    autocomplete_stop_event,
    debug_display=None,
    generated_text_callback=None,
):
    thread = threading.Thread(
        target=stream_autocomplete_to_writer,
        args=(
            prompt,
            write_queue,
            autocomplete_stop_event,
            debug_display,
            generated_text_callback,
        ),
        name="autocomplete-generator",
        daemon=True,
    )
    thread.start()
    return thread


def start_reader_thread(read_queue, stop_event, debug=False):
    # In debug mode the reader is mocked by read.debug_read_loop, so the Mac
    # keyboard feeds the same queue that the Raspberry Pi matrix normally feeds.
    target = read.debug_read_loop if debug else read.read_loop
    thread = threading.Thread(
        target=target,
        args=(read_queue, stop_event),
        name="keyboard-reader",
        daemon=True,
    )
    thread.start()
    return thread


def start_writer_thread(write_queue, stop_event, debug=False, debug_echo=True):
    # In debug mode the writer is mocked by write.debug_write_loop, so queued
    # letters print to the terminal instead of enabling the mux bridge.
    target = write.debug_write_loop if debug else write.write_loop
    kwargs = {"echo": debug_echo} if debug else {}
    thread = threading.Thread(
        target=target,
        args=(write_queue, stop_event),
        kwargs=kwargs,
        name="keyboard-writer",
        daemon=True,
    )
    thread.start()
    return thread


def run_pipeline(read_queue, write_queue, stop_event, debug_display=None):
    while not stop_event.is_set():
        try:
            key = read_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        try:
            if debug_display is not None:
                debug_display.read(key)
            else:
                print(f"READ: {key!r}", flush=True)

            output = process_read_key(key)
            enqueue_write_output(write_queue, output)

            if debug_display is not None:
                debug_display.typed_key(key)
        finally:
            read_queue.task_done()


def run_autocomplete_pipeline(
    read_queue,
    write_queue,
    stop_event,
    debug_display=None,
    sessions_enabled=False,
):
    prompt_buffer = []
    prompt_buffer_lock = threading.Lock()
    autocomplete_thread = None
    autocomplete_stop_event = threading.Event()
    current_session_number = 0

    def add_generated_text_to_prompt(chunk, session_number=None):
        with prompt_buffer_lock:
            if session_number is not None and session_number != current_session_number:
                return False

            append_prompt_text(prompt_buffer, chunk)

        return True

    def stop_autocomplete(status_message):
        nonlocal autocomplete_stop_event, autocomplete_thread

        if autocomplete_thread is None:
            return

        if debug_display is not None:
            debug_display.autocomplete_status(status_message)
        else:
            print(f"AUTOCOMPLETE: {status_message}", flush=True)

        autocomplete_stop_event.set()
        clear_queue(write_queue)
        autocomplete_thread.join(timeout=1)
        autocomplete_thread = None
        autocomplete_stop_event = threading.Event()

    def start_session():
        nonlocal current_session_number

        current_session_number += 1

        with prompt_buffer_lock:
            prompt_buffer.clear()

        start_text = build_session_start_text(current_session_number)

        if start_text:
            enqueue_write_output(write_queue, start_text)

        if debug_display is not None:
            debug_display.session_start(current_session_number, start_text)
        else:
            print(f"SESSION: start {current_session_number}", flush=True)

    if sessions_enabled:
        start_session()

    while not stop_event.is_set():
        if autocomplete_thread is not None and not autocomplete_thread.is_alive():
            autocomplete_thread = None
            autocomplete_stop_event = threading.Event()

        try:
            key = read_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        try:
            if debug_display is not None:
                debug_display.read(key)
            else:
                print(f"READ: {key!r}", flush=True)

            if sessions_enabled and key == AUTOCOMPLETE_STOP_KEY:
                stop_autocomplete("ending session")
                clear_queue(write_queue)
                start_session()
                continue

            if autocomplete_thread is not None:
                if key == AUTOCOMPLETE_STOP_KEY:
                    stop_autocomplete("stopping")

                continue

            if key == AUTOCOMPLETE_START_KEY:
                with prompt_buffer_lock:
                    prompt = "".join(prompt_buffer).strip()

                if not prompt:
                    if debug_display is not None:
                        debug_display.autocomplete_status("prompt is empty")
                    else:
                        print("AUTOCOMPLETE: prompt is empty", flush=True)

                    continue

                if debug_display is not None:
                    debug_display.autocomplete_prompt(prompt)
                    debug_display.llm_config(autocomplete.ACTIVE_MODE, autocomplete.OPENAI_MODEL)
                else:
                    print(f"AUTOCOMPLETE PROMPT: {prompt!r}", flush=True)

                autocomplete_stop_event.clear()
                if sessions_enabled:
                    generated_text_callback = (
                        lambda chunk, session_number=current_session_number:
                        add_generated_text_to_prompt(chunk, session_number)
                    )
                else:
                    generated_text_callback = add_generated_text_to_prompt

                autocomplete_thread = start_autocomplete_thread(
                    prompt,
                    write_queue,
                    autocomplete_stop_event,
                    debug_display=debug_display,
                    generated_text_callback=generated_text_callback,
                )
                continue

            with prompt_buffer_lock:
                update_prompt_buffer(prompt_buffer, key)

            output = process_read_key(key)
            enqueue_write_output(write_queue, output)

            if debug_display is not None:
                debug_display.typed_key(key)

        finally:
            read_queue.task_done()


def parse_args():
    parser = argparse.ArgumentParser(description="Typewriter main pipeline.")
    parser.add_argument(
        "--autocomplete",
        action="store_true",
        help="Start Gemma autocomplete with KEY_CODE and stop it with KEY_MODE",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Use terminal keyboard/output mocks instead of Raspberry Pi GPIO",
    )
    parser.add_argument(
        "--sessions",
        action="store_true",
        help="Session loop for autocomplete mode",
    )

    args = parser.parse_args()

    if args.sessions and not args.autocomplete:
        parser.error("--sessions is only supported with --autocomplete")

    return args


def main():
    args = parse_args()
    read_queue = queue.Queue()
    write_queue = queue.Queue()
    stop_event = threading.Event()
    terminal_display = TerminalTextDisplay() if args.debug or args.autocomplete else None
    reader_thread = None
    writer_thread = None

    try:
        print("Main pipeline running. Press Ctrl+C to stop.", flush=True)

        if args.debug:
            key_mode_action = (
                "ends the current session"
                if args.sessions
                else "stops autocomplete"
            )
            print(
                "Debug mode: GPIO is not used. "
                f"Ctrl+G/F1 = KEY_CODE, Ctrl+X = KEY_MODE ({key_mode_action}).",
                flush=True,
            )
            print(
                "Terminal display: "
                f"{terminal_display.color('typed text', TYPED_COLOR)} / "
                f"{terminal_display.color('generated text', GENERATED_COLOR)}",
                flush=True,
            )
        elif args.autocomplete:
            print(
                "Hardware mode: using read.py/write.py for keys; "
                "terminal display is active.",
                flush=True,
            )
            print(
                "Terminal display: "
                f"{terminal_display.color('typed text', TYPED_COLOR)} / "
                f"{terminal_display.color('generated text', GENERATED_COLOR)}",
                flush=True,
            )

        reader_thread = start_reader_thread(read_queue, stop_event, debug=args.debug)
        writer_thread = start_writer_thread(
            write_queue,
            stop_event,
            debug=args.debug,
            debug_echo=terminal_display is None,
        )

        if args.autocomplete:
            if args.sessions:
                print(
                    "Autocomplete sessions mode: "
                    "KEY_CODE starts autocomplete, KEY_MODE starts a new session.",
                    flush=True,
                )
            else:
                print("Autocomplete mode: KEY_CODE starts, KEY_MODE stops.", flush=True)

            # Load API key from .env file if available
            autocomplete.load_env()
            run_autocomplete_pipeline(
                read_queue,
                write_queue,
                stop_event,
                debug_display=terminal_display,
                sessions_enabled=args.sessions,
            )
        else:
            run_pipeline(
                read_queue,
                write_queue,
                stop_event,
                debug_display=terminal_display,
            )

    except KeyboardInterrupt:
        print("\nStopping...", flush=True)

    finally:
        stop_event.set()
        write_queue.put(None)

        if reader_thread is not None:
            reader_thread.join(timeout=2)

        if writer_thread is not None:
            writer_thread.join(timeout=2)

        print("Stopped.", flush=True)


if __name__ == "__main__":
    main()
