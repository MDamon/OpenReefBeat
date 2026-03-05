"""Display clean cycle + test."""
import gc
import time
from picographics import PicoGraphics, DISPLAY_INKY_FRAME_7 as DISPLAY

gc.collect()
graphics = PicoGraphics(DISPLAY)
WIDTH, HEIGHT = graphics.get_bounds()
print("Bounds: {}x{}".format(WIDTH, HEIGHT))

# Clean cycle — alternate black/white to reset e-ink
print("Cleaning display...")
graphics.set_pen(0)  # black
graphics.clear()
graphics.update()
time.sleep(2)

graphics.set_pen(1)  # white
graphics.clear()
graphics.update()
time.sleep(2)

# Now render test
print("Rendering test...")
graphics.set_pen(1)
graphics.clear()

graphics.set_pen(0)
graphics.set_font("bitmap8")

# Simple text at various positions - use measured width for wrap
text1 = "Hello World"
graphics.text(text1, 16, 50, WIDTH - 16, scale=3)

text2 = "Temperature: 79.3F"
graphics.text(text2, 16, 100, WIDTH - 16, scale=3)

# Boxes with no text
graphics.set_pen(5)  # should be blue on our panel
graphics.rectangle(16, 200, 200, 60)

graphics.set_pen(3)  # should be red on our panel
graphics.rectangle(250, 200, 200, 60)

graphics.set_pen(6)  # should be green
graphics.rectangle(484, 200, 200, 60)

print("Final update...")
graphics.update()
print("Done! Check display.")
