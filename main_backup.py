#!/usr/bin/env python3
"""Main program: read keys, process them, and write the result."""

import queue
import threading

import read
import write


def process_read_key(key):
    return key


def enqueue_write_output(write_queue, output):
    if output is None:
        return

    if isinstance(output, (list, tuple)):
        for item in output:
            write_queue.put(item)
    else:
        write_queue.put(output)


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


def main():
    read_queue = queue.Queue()
    write_queue = queue.Queue()
    stop_event = threading.Event()

    reader_thread = start_reader_thread(read_queue, stop_event)
    writer_thread = start_writer_thread(write_queue, stop_event)

    try:
        print("Main pipeline running. Press Ctrl+C to stop.", flush=True)
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
