from gpiozero import OutputDevice, InputDevice

from time import sleep

# GPIO pins

OUT_PIN = 17

IN_PIN = 27

# Configure pins

output_pin = OutputDevice(OUT_PIN)

input_pin = InputDevice(IN_PIN)

print("Setting GPIO17 HIGH and reading GPIO27")

try:

    while True:

        # Set output HIGH

        output_pin.on()

        # Read input

        value = input_pin.value

        print(f"GPIO27 state: {value}")

        sleep(1)

except KeyboardInterrupt:

    output_pin.off()

    print("Stopped")