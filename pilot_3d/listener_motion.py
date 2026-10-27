"""Small, smooth listening motions around an alert, forward-looking pose."""

import math


def listener_offsets(index, count):
    if count < 5 or not 0 <= index < count:
        raise ValueError("Invalid listener animation sample.")
    sway = math.cos(math.pi * index / (count - 1))
    center = count // 2
    blink_phase = (index - (center - 2)) / 4
    blink = math.sin(math.pi * blink_phase) ** 2 if 0 < blink_phase < 1 else 0
    return {"head_yaw": .018 * sway, "chest_yaw": .008 * sway,
            "eye_horizontal": .02 * sway, "blink": .034 * blink}
