#!/usr/bin/env python3
"""Main program: read keys, process them, and write the result."""

import argparse
import json
import os
import queue
import sys
import threading
import time
from datetime import datetime

import autocomplete
import read
import write

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_ARCHIVE_FILE = os.path.join(BASE_DIR, "sessions_archive.json")

AUTOCOMPLETE_START_KEY = "KEY_CODE"
AUTOCOMPLETE_STOP_KEY = "KEY_MODE"
SESSION_START_TEXTS = (
    "",
)
SESSION_END_TEXTS = (
    "KEY_ENTER KEY_ENTER (Review No. {session} - {timestamp}) KEY_ENTER KEY_ENTER KEY_ENTER KEY_ENTER KEY_ENTER KEY_ENTER KEY_ENTER",
)
TIMED_AUTOCOMPLETE_IDLE_RULES = (
    (1, 2.0),
    (50, 2.0),
    (200, 1.0),
    (500, 1.0),
    (750, 0.5),
)
TIMED_SESSION_END_IDLE_SECONDS = 15.0

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
        self.session_char_count = 0
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
            self.session_char_count = 0
            self._log("SESSION", f"start {session_number}", SESSION_COLOR)

            if start_text:
                self._append_text("session", start_text)

            self._render_text()

    def session_end(self, session_number, end_text):
        with self.lock:
            self._log("SESSION", f"end {session_number}", SESSION_COLOR)

            if end_text:
                self._append_text("session", end_text)

            self._render_text()

    def set_session_char_count(self, char_count):
        with self.lock:
            self.session_char_count = char_count

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
        print(
            f"  {self.color('session chars:', SESSION_COLOR)} "
            f"{self.session_char_count}",
            file=self.output_stream,
        )

        if not self.segments:
            print(f"  {self.color('(empty)', DIM)}", file=self.output_stream, flush=True)
            print(file=self.output_stream, flush=True)
            return

        rendered = "".join(
            self.color(self._display_text(text), self._segment_color(source))
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

    def _display_text(self, text):
        rendered_tokens = []

        for token in write.parse_key_tokens(text):
            if token == "KEY_ENTER":
                rendered_tokens.append("\n")
            elif token == "KEY_TAB":
                rendered_tokens.append("\t")
            elif token.startswith("KEY_"):
                continue
            else:
                rendered_tokens.append(token)

        return "".join(rendered_tokens)


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


def count_written_text_chars(text):
    return sum(1 for char in text if char not in "\n\r")


def timed_autocomplete_idle_seconds(written_chars):
    idle_seconds = None

    for min_chars, seconds in TIMED_AUTOCOMPLETE_IDLE_RULES:
        if written_chars >= min_chars:
            idle_seconds = seconds

    return idle_seconds


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
        cleared_items = len(target_queue.queue)
        target_queue.queue.clear()

        if hasattr(target_queue, "unfinished_tasks"):
            target_queue.unfinished_tasks = max(
                0,
                target_queue.unfinished_tasks - cleared_items,
            )

            if target_queue.unfinished_tasks == 0:
                target_queue.all_tasks_done.notify_all()


def queue_has_unfinished_work(target_queue):
    return getattr(target_queue, "unfinished_tasks", 0) > 0


def is_manual_autocomplete_key(key):
    return key in (AUTOCOMPLETE_START_KEY, AUTOCOMPLETE_STOP_KEY)


def empty_session_archive():
    return {"sessions": []}


def write_session_archive(archive, archive_file=SESSION_ARCHIVE_FILE):
    temp_file = f"{archive_file}.tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)
        f.write("\n")

    os.replace(temp_file, archive_file)


def load_session_archive(archive_file=SESSION_ARCHIVE_FILE):
    if not os.path.exists(archive_file):
        archive = empty_session_archive()
        write_session_archive(archive, archive_file=archive_file)
        return archive

    with open(archive_file, "r", encoding="utf-8") as f:
        archive = json.load(f)

    if not isinstance(archive, dict) or not isinstance(archive.get("sessions"), list):
        raise ValueError(f"{archive_file} must contain a JSON object with a sessions list")

    return archive


def next_session_number_from_archive(archive):
    last_session_number = 0

    for session in archive["sessions"]:
        if not isinstance(session, dict):
            continue

        session_number = session.get("session_number")

        if isinstance(session_number, int):
            last_session_number = max(last_session_number, session_number)

    return last_session_number + 1


def append_session_to_archive(
    archive,
    session_number,
    text,
    archive_file=SESSION_ARCHIVE_FILE,
):
    archive["sessions"].append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "session_number": session_number,
            "text": text,
        }
    )
    write_session_archive(archive, archive_file=archive_file)


def build_session_start_text(session_number):
    return build_session_marker_text(SESSION_START_TEXTS, session_number)


def build_session_end_text(session_number):
    return build_session_marker_text(SESSION_END_TEXTS, session_number)


def build_session_marker_text(templates, session_number):
    if not templates:
        return ""

    started_at = datetime.now()
    template = templates[(session_number - 1) % len(templates)]
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
    timed_enabled=False,
    session_archive=None,
    first_session_number=1,
    session_archive_file=SESSION_ARCHIVE_FILE,
):
    prompt_buffer = []
    prompt_buffer_lock = threading.Lock()
    autocomplete_thread = None
    autocomplete_stop_event = threading.Event()
    current_session_number = first_session_number - 1
    session_written_chars = 0
    session_saved = True
    last_user_write_at = None
    last_autocomplete_written_at = None
    waiting_for_autocomplete_write = False
    user_wrote_since_last_autocomplete = False

    def add_generated_text_to_prompt(chunk, session_number=None):
        nonlocal session_written_chars

        with prompt_buffer_lock:
            if session_number is not None and session_number != current_session_number:
                return False

            append_prompt_text(prompt_buffer, chunk)
            session_written_chars += count_written_text_chars(chunk)

        update_display_char_count()
        return True

    def update_display_char_count():
        if debug_display is not None:
            debug_display.set_session_char_count(session_written_chars)

    def current_session_text():
        with prompt_buffer_lock:
            return "".join(prompt_buffer)

    def save_current_session():
        nonlocal session_saved

        if (
            not sessions_enabled
            or session_archive is None
            or session_saved
            or current_session_number < first_session_number
        ):
            return

        append_session_to_archive(
            session_archive,
            current_session_number,
            current_session_text(),
            archive_file=session_archive_file,
        )
        session_saved = True

        if debug_display is not None:
            debug_display.autocomplete_status(
                f"saved session {current_session_number}"
            )
        else:
            print(f"SESSION: saved {current_session_number}", flush=True)

    def finish_current_session():
        if current_session_number < first_session_number:
            return

        save_current_session()
        end_text = build_session_end_text(current_session_number)

        if end_text:
            enqueue_write_output(write_queue, end_text)

        if debug_display is not None:
            debug_display.session_end(current_session_number, end_text)
        else:
            print(f"SESSION: end {current_session_number}", flush=True)

    def stop_autocomplete(status_message):
        nonlocal autocomplete_stop_event, autocomplete_thread
        nonlocal last_autocomplete_written_at, waiting_for_autocomplete_write

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
        last_autocomplete_written_at = None
        waiting_for_autocomplete_write = False

    def start_session(write_end_text=True):
        nonlocal current_session_number, session_written_chars
        nonlocal session_saved
        nonlocal last_user_write_at, last_autocomplete_written_at
        nonlocal waiting_for_autocomplete_write
        nonlocal user_wrote_since_last_autocomplete

        if write_end_text:
            finish_current_session()

        current_session_number += 1

        with prompt_buffer_lock:
            prompt_buffer.clear()

        session_written_chars = 0
        session_saved = False
        last_user_write_at = None
        last_autocomplete_written_at = None
        waiting_for_autocomplete_write = False
        user_wrote_since_last_autocomplete = False

        start_text = build_session_start_text(current_session_number)

        if start_text:
            enqueue_write_output(write_queue, start_text)

        if debug_display is not None:
            debug_display.session_start(current_session_number, start_text)
        else:
            print(f"SESSION: start {current_session_number}", flush=True)

    def note_user_write(key):
        nonlocal session_written_chars, last_user_write_at
        nonlocal user_wrote_since_last_autocomplete

        if key == "KEY_BACKSPACE":
            last_user_write_at = time.monotonic()
            user_wrote_since_last_autocomplete = True
            return

        text = key_to_prompt_text(key)

        if not text:
            return

        session_written_chars += count_written_text_chars(text)
        last_user_write_at = time.monotonic()
        user_wrote_since_last_autocomplete = True
        update_display_char_count()

    def finish_autocomplete_if_done():
        nonlocal autocomplete_thread, autocomplete_stop_event
        nonlocal waiting_for_autocomplete_write

        if autocomplete_thread is None or autocomplete_thread.is_alive():
            return

        autocomplete_thread = None
        autocomplete_stop_event = threading.Event()

        if timed_enabled:
            waiting_for_autocomplete_write = True

    def start_post_autocomplete_idle_if_writer_done():
        nonlocal waiting_for_autocomplete_write, last_autocomplete_written_at

        if not timed_enabled or not waiting_for_autocomplete_write:
            return

        if queue_has_unfinished_work(write_queue):
            return

        waiting_for_autocomplete_write = False
        last_autocomplete_written_at = time.monotonic()

    def start_autocomplete_from_prompt(reason=None):
        nonlocal autocomplete_thread, autocomplete_stop_event
        nonlocal last_autocomplete_written_at, waiting_for_autocomplete_write
        nonlocal user_wrote_since_last_autocomplete

        with prompt_buffer_lock:
            prompt = "".join(prompt_buffer).strip()

        if not prompt:
            if debug_display is not None:
                debug_display.autocomplete_status("prompt is empty")
            else:
                print("AUTOCOMPLETE: prompt is empty", flush=True)

            if timed_enabled:
                user_wrote_since_last_autocomplete = False

            return False

        if reason:
            if debug_display is not None:
                debug_display.autocomplete_status(reason)
            else:
                print(f"AUTOCOMPLETE: {reason}", flush=True)

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

        if timed_enabled:
            user_wrote_since_last_autocomplete = False
            last_autocomplete_written_at = None
            waiting_for_autocomplete_write = False

        return True

    def run_timed_actions():
        if not timed_enabled or autocomplete_thread is not None:
            return

        start_post_autocomplete_idle_if_writer_done()

        now = time.monotonic()

        if last_autocomplete_written_at is not None:
            idle_after_autocomplete = now - last_autocomplete_written_at

            if (
                not user_wrote_since_last_autocomplete
                and idle_after_autocomplete >= TIMED_SESSION_END_IDLE_SECONDS
            ):
                if debug_display is not None:
                    debug_display.autocomplete_status("timed session end")
                else:
                    print("AUTOCOMPLETE: timed session end", flush=True)

                clear_queue(write_queue)
                start_session()
                return

        if not user_wrote_since_last_autocomplete or last_user_write_at is None:
            return

        idle_seconds = timed_autocomplete_idle_seconds(session_written_chars)
        if idle_seconds is None:
            return

        if now - last_user_write_at >= idle_seconds:
            start_autocomplete_from_prompt(
                "timed autocomplete after "
                f"{idle_seconds:.0f}s idle and {session_written_chars} chars"
            )

    if sessions_enabled:
        start_session(write_end_text=False)

    try:
        while not stop_event.is_set():
            finish_autocomplete_if_done()
            run_timed_actions()

            try:
                key = read_queue.get(timeout=0.1)
            except queue.Empty:
                finish_autocomplete_if_done()
                run_timed_actions()
                continue

            try:
                if debug_display is not None:
                    debug_display.read(key)
                else:
                    print(f"READ: {key!r}", flush=True)

                if timed_enabled and is_manual_autocomplete_key(key):
                    if debug_display is not None:
                        debug_display.autocomplete_status(
                            f"{key} ignored in timed mode"
                        )
                    else:
                        print(
                            f"AUTOCOMPLETE: {key} ignored in timed mode",
                            flush=True,
                        )

                    continue

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
                    start_autocomplete_from_prompt()
                    continue

                with prompt_buffer_lock:
                    update_prompt_buffer(prompt_buffer, key)
                note_user_write(key)

                output = process_read_key(key)
                enqueue_write_output(write_queue, output)

                if debug_display is not None:
                    debug_display.typed_key(key)

            finally:
                read_queue.task_done()
    finally:
        save_current_session()


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
    parser.add_argument(
        "--timed",
        action="store_true",
        help="Automatically trigger autocomplete/session changes after inactivity",
    )

    args = parser.parse_args()

    if args.sessions and not args.autocomplete:
        parser.error("--sessions is only supported with --autocomplete")
    if args.timed and not (args.autocomplete and args.sessions):
        parser.error("--timed is only supported with --autocomplete --sessions")

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
            if args.timed:
                print(
                    "Debug mode: GPIO is not used. "
                    "Ctrl+G/F1 and Ctrl+X are ignored in timed mode.",
                    flush=True,
                )
            else:
                key_mode_action = (
                    "ends the current session"
                    if args.sessions
                    else "stops autocomplete"
                )
                print(
                    "Debug mode: GPIO is not used. "
                    f"Ctrl+G/F1 = KEY_CODE, Ctrl+X = KEY_MODE "
                    f"({key_mode_action}).",
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

        session_archive = None
        first_session_number = 1

        if args.autocomplete:
            # Load API key from .env file if available.
            autocomplete.load_env()

            if args.sessions:
                session_archive = load_session_archive()
                first_session_number = next_session_number_from_archive(
                    session_archive
                )
                print(
                    "Session archive: "
                    f"{SESSION_ARCHIVE_FILE} "
                    f"(next session {first_session_number})",
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
            if args.timed:
                print(
                    "Autocomplete timed sessions mode: "
                    "idle time starts autocomplete and ends sessions automatically.",
                    flush=True,
                )
            elif args.sessions:
                print(
                    "Autocomplete sessions mode: "
                    "KEY_CODE starts autocomplete, KEY_MODE starts a new session.",
                    flush=True,
                )
            else:
                print("Autocomplete mode: KEY_CODE starts, KEY_MODE stops.", flush=True)

            run_autocomplete_pipeline(
                read_queue,
                write_queue,
                stop_event,
                debug_display=terminal_display,
                sessions_enabled=args.sessions,
                timed_enabled=args.timed,
                session_archive=session_archive,
                first_session_number=first_session_number,
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
