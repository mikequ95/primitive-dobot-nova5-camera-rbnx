---
description: Capture a calibrated RGB frame from the Nova5 wrist camera while the arm is stationary.
---

# Wrist RGB snapshot

Call `camera/snapshot` to observe the current scene. RGB is checked against continuous stationary feedback from the same-host `nova5_arm` provider; monotonic receipt times establish the stationary window, while the image acquisition timestamp is unknown (header stamp zero). The black Robonix box sits on the fixed 25 mm checkerboard. This capability never moves the arm or gripper.
