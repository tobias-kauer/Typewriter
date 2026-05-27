# Raspberry Pi Keyboard Matrix Scanner

This project provides a Python keyboard matrix scanner for Raspberry Pi using two 16-channel multiplexers. It is designed to work on modern Raspberry Pi models, including Raspberry Pi 5.

## Files

- `main.py` — Raspberry Pi keyboard matrix scanning program.
- `requirements.txt` — Python dependency list.

## Requirements

- Raspberry Pi running Raspberry Pi OS
- Python 3.11 or newer
- `RPi.GPIO` or `pigpio`

Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Install the pigpio daemon if using the `pigpio` backend:

```bash
sudo apt update
sudo apt install pigpio python3-pigpio
```

Start the daemon manually if the service unit is unavailable:

```bash
sudo pigpiod
```

If your system has the service unit, enable it with:

```bash
sudo systemctl enable --now pigpiod
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

The program prints detected connections to the console:

```text
Scan start
row=0, col=0
row=1, col=3
Scan end
```

Stop the scan with `Ctrl+C`.

## Raspberry Pi 5 Notes

- On Raspberry Pi 5, `RPi.GPIO` may not initialize correctly in some environments.
- This script tries `RPi.GPIO` first and then falls back to `pigpio` if `RPi.GPIO` fails.
- If pigpio is used, ensure the pigpio daemon is running.

## Troubleshooting

If the script reports "Cannot determine SOC peripheral base address", install and use the `pigpio` backend:

```bash
sudo apt install pigpio python3-pigpio
sudo systemctl enable --now pigpiod
python3 main.py
```
