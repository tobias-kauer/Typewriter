# Raspberry Pi Keyboard Matrix Scanner

This project provides a Python-based scanner for a keyboard matrix connected through two 16-channel multiplexers. It is intended for Raspberry Pi 5 hardware and uses `RPi.GPIO` to control the row and column selector pins.

## Files

- `main.py` — Raspberry Pi keyboard matrix scanning program.
- `requirements.txt` — Python dependency list.

## Requirements

- Raspberry Pi running Raspberry Pi OS
- Python 3.11 or newer
- `RPi.GPIO` installed

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## GPIO Wiring

Update the BCM pin constants in `main.py` to match your wiring before running:

- `ROW_EN`, `ROW_S0`, `ROW_S1`, `ROW_S2`, `ROW_S3`, `ROW_SIG`
- `COL_EN`, `COL_S0`, `COL_S1`, `COL_S2`, `COL_S3`, `COL_SIG`

These pins correspond to the mux enable and select lines for the row and column multiplexers.

## Configuration

Control the scan dimensions in `main.py`:

```python
ROW_COUNT = 16
COL_COUNT = 16
TARGET_ROWS = list(range(ROW_COUNT))
TARGET_COLS = list(range(COL_COUNT))
```

Modify `TARGET_ROWS` and `TARGET_COLS` to scan only a subset of the matrix.

## Usage

Run the scanner with:

```bash
python3 main.py
```

The program prints detected connections to the console, for example:

```text
Scan start
row=0, col=0
row=1, col=3
Scan end
```

Stop the scan with `Ctrl+C`.

## Notes

- The script configures the row signal as output and the column signal as input with pull-up, then checks for LOW on the selected column.
- Ensure your multiplexer modules are compatible with the GPIO voltage levels on the Raspberry Pi.
