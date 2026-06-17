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
DEFAULT_MAX_OUTPUT_CHARS = 160
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


def build_ollama_connection_error(error, model, ollama_url):
    reason = getattr(error, "reason", error)
    return (
        f"Could not reach Ollama at {ollama_url}: {reason}. "
        "Start Ollama with `ollama serve` or open the Ollama app, then check "
        f"that {model!r} appears in `ollama list`."
    )


def build_prompt(prompt):
    return (
        "You are an autocomplete engine for a typewriter.\n"
        "Continue the existing text naturally with the next few words.\n"
        "Start exactly where the existing text stops.\n"
        "Output only the new continuation text, never the existing text.\n"
        "Do not repeat the existing text.\n"
        "Do not list characters, alphabets, symbols, rules, or explanations.\n"
        "Keep the continuation short.\n\n"
        f"Existing text:\n{prompt}\n\n"
        "Continuation:"
    )


def build_retry_prompt(prompt):
    return (
        "Write only the next new words for this text.\n"
        "Do not copy or restate any part of the existing text.\n"
        "Your answer must begin with the first new character after the existing text.\n"
        "Return a short natural continuation, 1 to 8 words.\n\n"
        f"Existing text that must not be repeated:\n{prompt}\n\n"
        "New continuation only:"
    )


def sanitize_generated_text(text):
    for token in BLOCKED_OUTPUT_TOKENS:
        text = text.replace(token, "")

    return "".join(char for char in text if char in ALLOWED_OUTPUT_CHARS)


def remove_prompt_echo(text, prompt):
    prompt = sanitize_generated_text(prompt).strip()

    if not text or not prompt:
        return text

    compare_text = text.lstrip()
    text_lower = compare_text.lower()
    prompt_lower = prompt.lower()

    if not compare_text:
        return text

    if prompt_lower.startswith(text_lower):
        return ""

    if text_lower.startswith(prompt_lower):
        return compare_text[len(prompt):].lstrip()

    common_length = 0

    for text_char, prompt_char in zip(text_lower, prompt_lower):
        if text_char != prompt_char:
            break

        common_length += 1

    if common_length >= min(8, len(prompt_lower)):
        return compare_text[common_length:].lstrip()

    return text


def clean_generated_text(text, prompt, max_chars=DEFAULT_MAX_OUTPUT_CHARS):
    cleaned = sanitize_generated_text(text)
    cleaned = remove_prompt_echo(cleaned, prompt)
    return cleaned[:max_chars].rstrip()


def generate_text(
    prompt,
    model=DEFAULT_MODEL,
    ollama_url=DEFAULT_OLLAMA_URL,
    timeout=DEFAULT_TIMEOUT,
    prompt_text=None,
):
    request_body = {
        "model": model,
        "prompt": prompt_text if prompt_text is not None else build_prompt(prompt),
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
            build_ollama_connection_error(error, model, ollama_url)
        ) from error

    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise AutocompleteError("Ollama returned invalid JSON") from error

    if "error" in payload:
        raise AutocompleteError(payload["error"])

    return clean_generated_text(payload.get("response", ""), prompt)


def generate_text_stream(
    prompt,
    model=DEFAULT_MODEL,
    ollama_url=DEFAULT_OLLAMA_URL,
    timeout=DEFAULT_TIMEOUT,
    stop_event=None,
    max_chars=DEFAULT_MAX_OUTPUT_CHARS,
    raw_chunk_callback=None,
    prompt_text=None,
):
    request_body = {
        "model": model,
        "prompt": prompt_text if prompt_text is not None else build_prompt(prompt),
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
            raw_text = ""
            emitted_text = ""

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

                raw_chunk = payload.get("response", "")

                if raw_chunk_callback is not None and raw_chunk:
                    raw_chunk_callback(raw_chunk)

                raw_text += raw_chunk

                safe_text = clean_generated_text(
                    raw_text,
                    prompt,
                    max_chars=max_chars,
                )
                safe_chunk = safe_text[len(emitted_text):]

                if safe_chunk:
                    emitted_text = safe_text
                    yield safe_chunk

                if len(emitted_text) >= max_chars:
                    break

                if payload.get("done"):
                    break

    except urllib.error.URLError as error:
        raise AutocompleteError(
            build_ollama_connection_error(error, model, ollama_url)
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
