#!/usr/bin/env python3
"""Small Ollama client for local text generation."""

import json
import urllib.error
import urllib.request

DEFAULT_MODEL = "gemma3:1b"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_TIMEOUT = 60


class AutocompleteError(RuntimeError):
    pass


def build_prompt(prompt):
    return (
        "Continue or complete the following typewriter text. "
        "Return only the text that should be written, without explanations.\n\n"
        f"{prompt}"
    )


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

    return payload.get("response", "").strip()


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

                if chunk:
                    yield chunk

                if payload.get("done"):
                    break

    except urllib.error.URLError as error:
        raise AutocompleteError(
            "Could not reach Ollama. Make sure it is running and that "
            f"{model!r} is available."
        ) from error


def main():
    prompt = input("Prompt: ")
    print(generate_text(prompt))


if __name__ == "__main__":
    main()
