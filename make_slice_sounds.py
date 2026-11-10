"""Generate ten short, original blade-swipe sound effects for the timer."""

import math
import random
import struct
import wave
from pathlib import Path


RATE = 24000
folder = Path(__file__).with_name("slice_sounds")
folder.mkdir(exist_ok=True)

for index in range(10):
    randomizer = random.Random(1701 + index)
    duration = 0.31 + 0.018 * index
    strike = duration * (0.36 + 0.05 * (index % 3))
    pitch = 1.0 + (index - 4) * 0.045
    air = previous = phase = 0.0
    samples = []
    for sample in range(round(duration * RATE)):
        t = sample / RATE
        sweep = math.exp(-((t - strike + 0.035) / (0.045 + index * 0.002)) ** 2)
        noise = randomizer.uniform(-1, 1)
        air += (0.08 + 0.38 * sweep) * (noise - air)
        hiss = (air - previous) * sweep * 0.72
        previous = air
        phase += math.tau * (240 + 800 * sweep) * pitch / RATE
        swish = sweep * 0.075 * math.sin(phase)
        ring = 0.0
        if t >= strike:
            age = t - strike
            bite = (1 - math.exp(-age * 1100)) * math.exp(-age * (23 + index))
            ring = bite * (0.19 * math.sin(math.tau * 2070 * pitch * age)
                           + 0.12 * math.sin(math.tau * 3391 * pitch * age)
                           + 0.055 * math.sin(math.tau * 5390 * pitch * age))
        fade = min(1.0, t * 120, (duration - t) * 70)
        samples.append((hiss + swish + ring) * fade)

    peak = max(abs(value) for value in samples)
    level = 13000 / peak
    with wave.open(str(folder / f"slice-{index + 1:02d}.wav"), "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(b"".join(struct.pack("<h", round(value * level)) for value in samples))
