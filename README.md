# Raspberry Pi Keyboard Matrix Scanner

A minimal Raspberry Pi keyboard matrix scanner using `libgpiod`.

## Files

- `main.py` — simple Pi matrix scan program.
- `requirements.txt` — Python dependency list.

## Requirements

- Raspberry Pi running Raspberry Pi OS
- Python 3.11 or newer

This project uses `libgpiod` for GPIO access. The recommended system packages and Python packages are listed below.

### System packages (apt)

Install the OS-level GPIO packages:

```bash
sudo apt update
sudo apt install python3-libgpiod pigpio python3-pigpio python3-rpi.gpio
```

Start the pigpio daemon if you plan to use `pigpio`:

```bash
sudo pigpiod || sudo systemctl enable --now pigpiod
```

If the service unit is not available, run the daemon manually:

```bash
sudo pigpiod
```

### Python packages (pip)

Install the Python runtime dependencies (use a virtual environment if desired):

```bash
python3 -m pip install -r requirements.txt
```

## Wiring

Update the BCM pin constants in `main.py` if your wiring differs.

## Configuration

Update the scan size in `main.py`:

```python
ROW_COUNT = 16
COL_COUNT = 16
TARGET_ROWS = list(range(ROW_COUNT))
TARGET_COLS = list(range(COL_COUNT))
```

The writer automatically presses `KEY_ENTER` before a row would exceed
`MAX_ROW_CHARS` in `write.py` (default: 65). For direct `write.py` runs, you can
override it with `--max-row-chars`.

## Autocomplete Configuration

The autocomplete feature supports three modes: **local** (Ollama), **server** (OpenAI), and **hybrid** (fallback). API keys are stored in a `.env` file (not tracked by git) to keep secrets secure.

### Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your OpenAI API key:
   ```
   OPENAI_API_KEY=sk-your-actual-api-key-here
   OPENAI_MODEL=gpt-5-mini
   ```

3. The `.env` file is automatically excluded from git (see `.gitignore`).

### Usage

**Interactive mode selection:**
```bash
python3 main.py --autocomplete --debug
```
The system will load your API key from `.env` automatically.

**Command-line mode selection:**
```bash
# Local mode (no API key needed)
python3 main.py --autocomplete --debug

# Server mode (API key from .env)
python3 main.py --autocomplete --debug

# Hybrid mode (API key from .env, falls back to local)
python3 main.py --autocomplete --debug

# Hardware session loop
python3 main.py --autocomplete --sessions

# Debug session loop
python3 main.py --autocomplete --sessions --debug

# Timed hardware session loop
python3 main.py --autocomplete --sessions --timed

# Timed debug session loop
python3 main.py --autocomplete --sessions --timed --debug
```

### Modes

- **local**: Uses Ollama on `localhost:11434` with `gemma3:1b` (no internet required)
- **server**: Uses OpenAI ChatGPT API with API key from `.env`
- **hybrid**: Tries OpenAI with 5-second timeout, falls back to local Ollama on failure
- **sessions**: With `--autocomplete --sessions`, `KEY_MODE` starts a new session and `KEY_CODE` autocompletes only the current session text
- **timed**: With `--autocomplete --sessions --timed`, inactivity triggers autocomplete. The session-end idle timer starts only after `write.py` has finished plotting the queued autocomplete output. Tune the thresholds in `TIMED_AUTOCOMPLETE_IDLE_RULES` and `TIMED_SESSION_END_IDLE_SECONDS` in `main.py`.

## Usage

Run the scanner:

```bash
python3 main.py
```

The program prints any detected connection rows and columns.

## Notes

This script uses direct GPIO access through `libgpiod` and avoids the older `RPi.GPIO` and `pigpio` backends.
