#!/usr/bin/env python3
"""Small Ollama client for local text generation."""

import argparse
import json
import urllib.error
import urllib.request

import write

DEFAULT_MODEL = "gemma3:1b"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_TIMEOUT = 60
TEST_PROMPT = "hey how are you"
ALLOWED_OUTPUT_CHARS = {
    key for key in write.KEY_POSITIONS if len(key) == 1 and not key.startswith("KEY_")
}
BLOCKED_OUTPUT_TOKENS = tuple(
    sorted(
        (key for key in write.KEY_POSITIONS if key.startswith("KEY_")),
        key=len,
        reverse=True,
    )
)


class AutocompleteError(RuntimeError):
    pass


def build_prompt(prompt):
    allowed_symbols = "".join(sorted(ALLOWED_OUTPUT_CHARS))

    return (
        "Continue or complete the following typewriter text. "
        "Return only the text that should be written, without explanations. "
        "Use only these exact output characters: "
        f"{allowed_symbols!r}.\n\n"
        f"{prompt}"
    )


def sanitize_generated_text(text):
    for token in BLOCKED_OUTPUT_TOKENS:
        text = text.replace(token, "")

    return "".join(char for char in text if char in ALLOWED_OUTPUT_CHARS)


def generate_text(
    prompt,
    model=DEFAULT_MODEL,
    ollama_url=DEFAULT_OLLAMA_URL,
    timeout=DEFAULT_TIMEOUT,
):
    request_body = {
        "model": model,
        "prompt": build_prompt(prompt),
        "stream": False,
    }
    request_data = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        ollama_url,
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")

    except urllib.error.URLError as error:
        raise AutocompleteError(
            "Could not reach Ollama. Make sure it is running and that "
            f"{model!r} is available."
        ) from error

    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise AutocompleteError("Ollama returned invalid JSON") from error

    if "error" in payload:
        raise AutocompleteError(payload["error"])

    return sanitize_generated_text(payload.get("response", "")).strip()


def generate_text_stream(
    prompt,
    model=DEFAULT_MODEL,
    ollama_url=DEFAULT_OLLAMA_URL,
    timeout=DEFAULT_TIMEOUT,
    stop_event=None,
):
    request_body = {
        "model": model,
        "prompt": build_prompt(prompt),
        "stream": True,
    }
    request_data = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        ollama_url,
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for line in response:
                if stop_event is not None and stop_event.is_set():
                    break

                if not line:
                    continue

                try:
                    payload = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError as error:
                    raise AutocompleteError("Ollama returned invalid JSON") from error

                if "error" in payload:
                    raise AutocompleteError(payload["error"])

                chunk = payload.get("response", "")

                safe_chunk = sanitize_generated_text(chunk)

                if safe_chunk:
                    yield safe_chunk

                if payload.get("done"):
                    break

    except urllib.error.URLError as error:
        raise AutocompleteError(
            "Could not reach Ollama. Make sure it is running and that "
            f"{model!r} is available."
        ) from error


def test_llm():
    print(f"Prompt: {TEST_PROMPT}")
    print("Response:")
    print(generate_text(TEST_PROMPT))


def parse_args():
    parser = argparse.ArgumentParser(description="Test or use local Gemma autocomplete.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a fixed test prompt to the LLM and print the response",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.test:
        test_llm()
        return

    prompt = input("Prompt: ")
    print(generate_text(prompt))


if __name__ == "__main__":
    main()
