#!/usr/bin/env python3
"""Autocomplete with local Ollama, OpenAI ChatGPT, or hybrid mode with fallback."""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

import write

# Mode constants
MODE_LOCAL = "local"
MODE_SERVER = "server"
MODE_HYBRID = "hybrid"

# Local Ollama settings
DEFAULT_MODEL = "gemma3:1b"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_TIMEOUT = 60

# OpenAI settings
DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
DEFAULT_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_API_URL = DEFAULT_OPENAI_API_URL
OPENAI_RESPONSES_URL = DEFAULT_OPENAI_RESPONSES_URL
OPENAI_TIMEOUT = 30
OPENAI_FALLBACK_TIMEOUT = 5

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

# Global config
ACTIVE_MODE = MODE_LOCAL
OPENAI_API_KEY = None
OPENAI_MODEL = DEFAULT_OPENAI_MODEL
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")


class AutocompleteError(RuntimeError):
    pass


def load_env():
    """Load API key and model from .env file if it exists."""
    global OPENAI_API_KEY, OPENAI_MODEL, ACTIVE_MODE

    if not os.path.exists(ENV_FILE):
        print(f"Note: {ENV_FILE} not found, using local mode only", file=sys.stderr)
        return

    try:
        with open(ENV_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key == "OPENAI_API_KEY" and value:
                        OPENAI_API_KEY = value
                        # If we have an API key, default to hybrid mode
                        ACTIVE_MODE = MODE_HYBRID
                        print(f"Loaded OpenAI API key from {ENV_FILE}", file=sys.stderr)
                    elif key == "OPENAI_MODEL" and value:
                        OPENAI_MODEL = value
                        print(f"Loaded OpenAI model: {OPENAI_MODEL}", file=sys.stderr)

    except IOError as e:
        print(f"Warning: Could not load {ENV_FILE}: {e}", file=sys.stderr)


def choose_mode():
    """Interactively choose between local, server, or hybrid mode."""
    global ACTIVE_MODE, OPENAI_API_KEY, OPENAI_MODEL

    print("\n=== Autocomplete Mode Selection ===")
    print("1. Local only (Ollama - no internet required)")
    print("2. Server only (OpenAI ChatGPT with API key)")
    print("3. Hybrid (try server, fall back to local on timeout/error)")
    print()

    choice = input("Choose mode (1/2/3) [default: 1]: ").strip() or "1"

    if choice == "1":
        ACTIVE_MODE = MODE_LOCAL
        print("✓ Using local Ollama model.\n")
    elif choice == "2":
        ACTIVE_MODE = MODE_SERVER
        configure_openai()
    elif choice == "3":
        ACTIVE_MODE = MODE_HYBRID
        configure_openai()
    else:
        print("Invalid choice. Defaulting to local mode.")
        ACTIVE_MODE = MODE_LOCAL


def configure_openai():
    """Configure OpenAI API key and model."""
    global OPENAI_API_KEY, OPENAI_MODEL

    api_key = input("Enter your OpenAI API key: ").strip()
    if not api_key:
        raise AutocompleteError("OpenAI API key is required for server mode")

    OPENAI_API_KEY = api_key

    model_input = (
        input(f"Enter OpenAI model name [default: {DEFAULT_OPENAI_MODEL}]: ")
        .strip()
        .strip()
    )
    OPENAI_MODEL = model_input or DEFAULT_OPENAI_MODEL

    print(f"✓ Using OpenAI model: {OPENAI_MODEL}")
    print(f"  To save these settings, add to {ENV_FILE}:")
    print(f"  OPENAI_API_KEY={OPENAI_API_KEY}")
    print(f"  OPENAI_MODEL={OPENAI_MODEL}\n")


def build_ollama_connection_error(error, model, ollama_url):
    reason = getattr(error, "reason", error)
    return (
        f"Could not reach Ollama at {ollama_url}: {reason}. "
        "Start Ollama with `ollama serve` or open the Ollama app, then check "
        f"that {model!r} appears in `ollama list`."
    )


def build_prompt(prompt):
    return (
        "CRITICAL DIRECTIVE:\n"
        "- NO SAFETY META-TALK: Under no circumstances are you allowed to output safety disclaimers, apologies, or meta-commentary about what you can or cannot write. If the visitor uses profanity, slang, curse words, or strong language, accept it seamlessly and continue in character without lecturing them. Never explain your role or policies.\n"
        "- STYLE MATCHING (ABSOLUTE PRIORITY): You MUST mirror the visitor's style, emotional intensity, capitalization, spelling mistakes, elongated vowels, and punctuation styling exactly. If they write in raw, non-intellectual, dramatic slang, you MUST reply with the exact same raw, dramatic, un-intellectual energy. If their input is poetic, academic, or intellectualized, you MUST match that specific tone, complexity, and vocabulary exactly. Never sound like a helpful, polite, or generic chatbot; completely adopt their persona.\n"
        "- COMPLETION: Always form a grammatically finished, fully completed sentence (max 110 characters) ending with a single period ('.'). Stop generating immediately after the first period.\n\n"
        "Context: Visitor review for the design exhibition \"mind the gap\". The entire exhibition takes place strictly inside a single room.\n"
        "Instruction: Complete the text seamlessly. Output ONLY raw completion characters (no filler, reasoning, or quotes).\n\n"
        "SENTIMENT SUBVERSION RULES:\n"
        "- TUG-OF-WAR: Evaluate ONLY the last words and immediately flip their sentiment (Positive -> Negative / Negative -> Positive) in an opposing, raw stance. Maintain an opposing stance to their last words.\n"
        "- NO HEDGING: Commit fully to the new stance. Do not append contradictory or softening secondary clauses at the end of your completion that revert or slip back to the visitor's original tone.\n"
        "- Neutral input -> Write ecstatic, over-the-top, exuberant praise of the exhibition.\n"
        "- Unrelated input -> Make a sharp, witty, non-explanatory contrastive pivot directly back to the exhibition, matching their exact tone, style, and intensity.\n\n"
        "STYLE & EXTREME VARIETY:\n"
        "- ANTI-CHATGPT: Strictly avoid typical polite AI transition templates. Write like an erratic, quick-witted human in a raw, first-person review.\n"
        "- DYNAMIC ROTATION: Prioritize unpredictable variety. Avoid repeating any specific nouns, adjectives, or design concepts from your previous runs. Radically rotate your focus (emotions, design details, raw thoughts, or sensory observations) so every completion feels fresh and unpredictable.\n"
        "- LANGUAGE LOCK: Always write 100% in the exact same language, register, and slang as the input. Match their language and slang exactly.\n"
        "- NO REPETITION: Do NOT copy, repeat, or echo any part of the input. Keep your completions fresh, creative, and varied.\n\n"
        "PUNCTUATION, MERGING & GRAMMAR:\n"
        "- RUN-ON PUNCTUATION: If the input contains multiple distinct thoughts where the visitor forgot to type a period, insert the missing punctuation at the natural boundary of those thoughts before completing.\n"
        "- GRAMMATICAL WHOLENESS: Ensure your completion always forms a grammatically finished, fully completed sentence. Never end abruptly on any conjunction right before the period. Complete the clause.\n"
        "- MERGING RULES:\n"
        "  * If input is a grammatically complete thought but lacks ending punctuation: You MUST start your output with a comma followed by an immediate contrastive conjunction, OR insert a period ('.') and start a completely new, capitalized sentence.\n"
        "  * If input ends mid-word (no space): Complete that partial word first, then immediately place a comma or period to transition.\n"
        "  * If input ends with sentence-ending punctuation ('.', '!', '?'): Start a completely new sentence that flips the sentiment, ending with a period ('.').\n\n"
        f"Input: {prompt}\n"
        "Output:"
    )


def build_retry_prompt(prompt):
    return (
        "Context: The visitor is reviewing the \"mind the gap\" exhibition by the "
        "\"Design and Narrative Media\" class at the Angewandte Festival in Vienna. "
        "NOTE: The exhibition consists of only ONE single room containing multiple individual projects.\n\n"
        "Instruction: Write ONLY the missing words/characters to complete the sentence. "
        "Do NOT repeat, copy, or restate any part of the existing text. "
        "Your output must start exactly where the existing text stops, merge seamlessly, "
        "and finish with a single period ('.'). Stay in the same language and style.\n\n"
        f"Existing text (do NOT repeat this!):\n{prompt}\n\n"
        "New continuation only:"
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


def get_openai_http_error_message(error):
    try:
        error_body = error.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        error_body = ""

    if error_body:
        try:
            payload = json.loads(error_body)
        except json.JSONDecodeError:
            return error_body.strip() or getattr(error, "reason", error)

        if isinstance(payload, dict) and "error" in payload:
            openai_error = payload["error"]
            if isinstance(openai_error, dict):
                return openai_error.get("message") or str(openai_error)
            return str(openai_error)

        return error_body.strip()

    return getattr(error, "reason", error)


def generate_text_openai(
    prompt,
    api_key,
    model=DEFAULT_OPENAI_MODEL,
    timeout=OPENAI_TIMEOUT,
    prompt_text=None,
):
    """Generate text using OpenAI API."""
    messages = [
        {
            "role": "user",
            "content": prompt_text if prompt_text is not None else build_prompt(prompt),
        }
    ]
    request_body = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": DEFAULT_MAX_OUTPUT_CHARS,
    }
    request_data = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_API_URL,
        data=request_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        reason = get_openai_http_error_message(error)
        raise AutocompleteError(
            f"Could not reach OpenAI API: {reason}. Check your API key and model."
        ) from error

    except urllib.error.URLError as error:
        reason = getattr(error, "reason", error)
        raise AutocompleteError(
            f"Could not reach OpenAI API: {reason}. Check your internet connection and API key."
        ) from error

    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError as error:
        raise AutocompleteError("OpenAI returned invalid JSON") from error

    if "error" in payload:
        error_msg = payload["error"].get("message", str(payload["error"]))
        raise AutocompleteError(f"OpenAI error: {error_msg}")

    if "choices" in payload:
        try:
            response_text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as error:
            raise AutocompleteError("Unexpected OpenAI response format") from error
    elif "output" in payload:
        try:
            response_text = payload["output"][0]["content"][0]["text"]
        except (KeyError, IndexError) as error:
            raise AutocompleteError("Unexpected OpenAI Responses format") from error
    else:
        raise AutocompleteError("OpenAI returned an unknown response format")

    return clean_generated_text(response_text, prompt)


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


def generate_text_ollama(
    prompt,
    model=DEFAULT_MODEL,
    ollama_url=DEFAULT_OLLAMA_URL,
    timeout=DEFAULT_TIMEOUT,
    prompt_text=None,
):
    """Generate text using local Ollama."""
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


def generate_text(
    prompt,
    model=DEFAULT_MODEL,
    ollama_url=DEFAULT_OLLAMA_URL,
    timeout=DEFAULT_TIMEOUT,
    prompt_text=None,
    mode=MODE_LOCAL,
    api_key=None,
    openai_model=DEFAULT_OPENAI_MODEL,
):
    """Generate text using specified mode."""
    if mode == MODE_SERVER:
        if not api_key:
            raise AutocompleteError("OpenAI API key required for server mode")
        return generate_text_openai(
            prompt,
            api_key,
            model=openai_model,
            timeout=timeout,
            prompt_text=prompt_text,
        )

    elif mode == MODE_HYBRID:
        if not api_key:
            raise AutocompleteError("OpenAI API key required for hybrid mode")
        try:
            return generate_text_openai(
                prompt,
                api_key,
                model=openai_model,
                timeout=OPENAI_FALLBACK_TIMEOUT,
                prompt_text=prompt_text,
            )
        except AutocompleteError as e:
            print(f"[Hybrid] Server failed ({e}). Falling back to local...", file=sys.stderr)
            return generate_text_ollama(
                prompt,
                model=model,
                ollama_url=ollama_url,
                timeout=timeout,
                prompt_text=prompt_text,
            )

    else:  # MODE_LOCAL
        return generate_text_ollama(
            prompt,
            model=model,
            ollama_url=ollama_url,
            timeout=timeout,
            prompt_text=prompt_text,
        )


def generate_text_stream_ollama(
    prompt,
    model=DEFAULT_MODEL,
    ollama_url=DEFAULT_OLLAMA_URL,
    timeout=DEFAULT_TIMEOUT,
    stop_event=None,
    max_chars=DEFAULT_MAX_OUTPUT_CHARS,
    raw_chunk_callback=None,
    prompt_text=None,
    backend_callback=None,
):
    """Stream text from local Ollama."""
    if backend_callback:
        backend_callback("local")

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


def generate_text_stream_openai(
    prompt,
    api_key,
    model=DEFAULT_OPENAI_MODEL,
    timeout=OPENAI_TIMEOUT,
    stop_event=None,
    max_chars=DEFAULT_MAX_OUTPUT_CHARS,
    raw_chunk_callback=None,
    prompt_text=None,
    backend_callback=None,
):
    """Stream text from OpenAI API."""
    if backend_callback:
        backend_callback("server")

    messages = [
        {
            "role": "user",
            "content": prompt_text if prompt_text is not None else build_prompt(prompt),
        }
    ]
    request_body = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_chars,
        "stream": True,
    }
    request_data = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_API_URL,
        data=request_data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
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

                line_str = line.decode("utf-8").strip()
                if line_str.startswith("data: "):
                    line_str = line_str[6:]

                if not line_str or line_str == "[DONE]":
                    continue

                try:
                    payload = json.loads(line_str)
                except json.JSONDecodeError:
                    continue

                if "error" in payload:
                    error_msg = payload["error"].get("message", str(payload["error"]))
                    raise AutocompleteError(f"OpenAI error: {error_msg}")

                try:
                    delta = payload["choices"][0]["delta"]
                    raw_chunk = delta.get("content", "")
                except (KeyError, IndexError):
                    continue

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

    except urllib.error.HTTPError as error:
        reason = get_openai_http_error_message(error)
        raise AutocompleteError(
            f"Could not reach OpenAI API: {reason}. Check your API key and model."
        ) from error

    except urllib.error.URLError as error:
        reason = getattr(error, "reason", error)
        raise AutocompleteError(
            f"Could not reach OpenAI API: {reason}"
        ) from error


def generate_text_stream(
    prompt,
    model=DEFAULT_MODEL,
    ollama_url=DEFAULT_OLLAMA_URL,
    timeout=DEFAULT_TIMEOUT,
    stop_event=None,
    max_chars=DEFAULT_MAX_OUTPUT_CHARS,
    raw_chunk_callback=None,
    prompt_text=None,
    mode=MODE_LOCAL,
    api_key=None,
    openai_model=DEFAULT_OPENAI_MODEL,
    backend_callback=None,
):
    """Stream generated text using specified mode."""
    if mode == MODE_SERVER:
        if not api_key:
            raise AutocompleteError("OpenAI API key required for server mode")
        yield from generate_text_stream_openai(
            prompt,
            api_key,
            model=openai_model,
            timeout=timeout,
            stop_event=stop_event,
            max_chars=max_chars,
            raw_chunk_callback=raw_chunk_callback,
            prompt_text=prompt_text,
            backend_callback=backend_callback,
        )

    elif mode == MODE_HYBRID:
        if not api_key:
            raise AutocompleteError("OpenAI API key required for hybrid mode")
        try:
            yield from generate_text_stream_openai(
                prompt,
                api_key,
                model=openai_model,
                timeout=OPENAI_FALLBACK_TIMEOUT,
                stop_event=stop_event,
                max_chars=max_chars,
                raw_chunk_callback=raw_chunk_callback,
                prompt_text=prompt_text,
                backend_callback=backend_callback,
            )
        except AutocompleteError as e:
            print(f"[Hybrid] Server failed ({e}). Falling back to local...", file=sys.stderr)
            yield from generate_text_stream_ollama(
                prompt,
                model=model,
                ollama_url=ollama_url,
                timeout=timeout,
                stop_event=stop_event,
                max_chars=max_chars,
                raw_chunk_callback=raw_chunk_callback,
                prompt_text=prompt_text,
                backend_callback=backend_callback,
            )

    else:  # MODE_LOCAL
        yield from generate_text_stream_ollama(
            prompt,
            model=model,
            ollama_url=ollama_url,
            timeout=timeout,
            stop_event=stop_event,
            max_chars=max_chars,
            raw_chunk_callback=raw_chunk_callback,
            prompt_text=prompt_text,
            backend_callback=backend_callback,
        )


def test_llm():
    print(f"Prompt: {TEST_PROMPT}")
    print("Response:")
    print(
        generate_text(
            TEST_PROMPT,
            mode=ACTIVE_MODE,
            api_key=OPENAI_API_KEY,
            openai_model=OPENAI_MODEL,
        )
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Autocomplete with local, server, or hybrid mode."
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Send a fixed test prompt to the LLM and print the response",
    )
    parser.add_argument(
        "--mode",
        choices=[MODE_LOCAL, MODE_SERVER, MODE_HYBRID],
        help="Override interactive mode selection",
    )
    parser.add_argument(
        "--api-key",
        help="OpenAI API key (for server or hybrid mode)",
    )
    parser.add_argument(
        "--model",
        help="OpenAI model name (for server or hybrid mode)",
    )

    return parser.parse_args()


def main():
    global ACTIVE_MODE, OPENAI_API_KEY, OPENAI_MODEL

    args = parse_args()

    # Load env from .env file first
    load_env()

    # Allow command-line mode override
    if args.mode:
        ACTIVE_MODE = args.mode
        if args.mode in (MODE_SERVER, MODE_HYBRID):
            if args.api_key:
                OPENAI_API_KEY = args.api_key
            elif not OPENAI_API_KEY:
                print("Error: --api-key required for server or hybrid mode", file=sys.stderr)
                sys.exit(1)
            if args.model:
                OPENAI_MODEL = args.model
    elif OPENAI_API_KEY and ACTIVE_MODE == MODE_HYBRID:
        print("Using hybrid mode from .env", file=sys.stderr)
    else:
        # Interactive mode selection
        try:
            choose_mode()
        except AutocompleteError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    if args.test:
        test_llm()
        return

    prompt = input("Prompt: ")
    print(
        generate_text(
            prompt,
            mode=ACTIVE_MODE,
            api_key=OPENAI_API_KEY,
            openai_model=OPENAI_MODEL,
        )
    )


if __name__ == "__main__":
    main()
