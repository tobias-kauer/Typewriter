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

## Usage

Run the scanner:

```bash
python3 main.py
```

The program prints any detected connection rows and columns.

## Notes

This script uses direct GPIO access through `libgpiod` and avoids the older `RPi.GPIO` and `pigpio` backends.
