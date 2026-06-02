#!/usr/bin/env python3
"""Set the mux enable line HIGH for testing."""

import time
from gpiozero import OutputDevice

MUX_EN = 6


def main():
    mux_enable = OutputDevice(MUX_EN, initial_value=True)
    mux_enable.on()

    print(f"GPIO {MUX_EN} is HIGH. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopped by user")

    finally:
        mux_enable.on()


if __name__ == "__main__":
    main()