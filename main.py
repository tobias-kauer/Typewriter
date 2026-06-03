#!/usr/bin/env python3
"""Main program: read keys, process them, and write the result."""

import argparse
import queue
import threading

import autocomplete
import read
import write

AUTOCOMPLETE_START_KEY = "KEY_CODE"
AUTOCOMPLETE_STOP_KEY = "KEY_MODE"


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


def update_prompt_buffer(prompt_buffer, key):
    if key == "KEY_BACKSPACE":
        if prompt_buffer:
            prompt_buffer.pop()

        return

    text = key_to_prompt_text(key)

    if text:
        prompt_buffer.append(text)


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


def stream_autocomplete_to_writer(prompt, write_queue, autocomplete_stop_event):
    try:
        for chunk in autocomplete.generate_text_stream(
            prompt,
            stop_event=autocomplete_stop_event,
        ):
            if autocomplete_stop_event.is_set():
                break

            print(f"AUTOCOMPLETE OUT: {chunk!r}", flush=True)
            enqueue_write_output(write_queue, chunk)

    except autocomplete.AutocompleteError as error:
        print(f"AUTOCOMPLETE ERROR: {error}", flush=True)


def start_autocomplete_thread(prompt, write_queue, autocomplete_stop_event):
    thread = threading.Thread(
        target=stream_autocomplete_to_writer,
        args=(prompt, write_queue, autocomplete_stop_event),
        name="autocomplete-generator",
        daemon=True,
    )
    thread.start()
    return thread


def start_reader_thread(read_queue, stop_event):
    thread = threading.Thread(
        target=read.read_loop,
        args=(read_queue, stop_event),
        name="keyboard-reader",
        daemon=True,
    )
    thread.start()
    return thread


def start_writer_thread(write_queue, stop_event):
    thread = threading.Thread(
        target=write.write_loop,
        args=(write_queue, stop_event),
        name="keyboard-writer",
        daemon=True,
    )
    thread.start()
    return thread


def run_pipeline(read_queue, write_queue, stop_event):
    while not stop_event.is_set():
        try:
            key = read_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        try:
            print(f"READ: {key!r}", flush=True)
            output = process_read_key(key)
            enqueue_write_output(write_queue, output)
        finally:
            read_queue.task_done()


def run_autocomplete_pipeline(read_queue, write_queue, stop_event):
    prompt_buffer = []
    autocomplete_thread = None
    autocomplete_stop_event = threading.Event()

    while not stop_event.is_set():
        if autocomplete_thread is not None and not autocomplete_thread.is_alive():
            autocomplete_thread = None
            autocomplete_stop_event.clear()

        try:
            key = read_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        try:
            print(f"READ: {key!r}", flush=True)

            if autocomplete_thread is not None:
                if key == AUTOCOMPLETE_STOP_KEY:
                    print("AUTOCOMPLETE: stopping", flush=True)
                    autocomplete_stop_event.set()
                    clear_queue(write_queue)
                    autocomplete_thread.join(timeout=1)
                    autocomplete_thread = None
                    autocomplete_stop_event.clear()

                continue

            if key == AUTOCOMPLETE_START_KEY:
                prompt = "".join(prompt_buffer).strip()

                if not prompt:
                    print("AUTOCOMPLETE: prompt is empty", flush=True)
                    continue

                print(f"AUTOCOMPLETE PROMPT: {prompt!r}", flush=True)
                autocomplete_stop_event.clear()
                autocomplete_thread = start_autocomplete_thread(
                    prompt,
                    write_queue,
                    autocomplete_stop_event,
                )
                continue

            update_prompt_buffer(prompt_buffer, key)
            output = process_read_key(key)
            enqueue_write_output(write_queue, output)

        finally:
            read_queue.task_done()


def parse_args():
    parser = argparse.ArgumentParser(description="Typewriter main pipeline.")
    parser.add_argument(
        "--autocomplete",
        action="store_true",
        help="Start Gemma autocomplete with KEY_CODE and stop it with KEY_MODE",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    read_queue = queue.Queue()
    write_queue = queue.Queue()
    stop_event = threading.Event()

    reader_thread = start_reader_thread(read_queue, stop_event)
    writer_thread = start_writer_thread(write_queue, stop_event)

    try:
        print("Main pipeline running. Press Ctrl+C to stop.", flush=True)

        if args.autocomplete:
            print("Autocomplete mode: KEY_CODE starts, KEY_MODE stops.", flush=True)
            run_autocomplete_pipeline(read_queue, write_queue, stop_event)
        else:
            run_pipeline(read_queue, write_queue, stop_event)

    except KeyboardInterrupt:
        print("\nStopping...", flush=True)

    finally:
        stop_event.set()
        write_queue.put(None)
        reader_thread.join(timeout=2)
        writer_thread.join(timeout=2)
        print("Stopped.", flush=True)


if __name__ == "__main__":
    main()
