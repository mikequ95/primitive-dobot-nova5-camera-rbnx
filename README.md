# Nova5 wrist RGB primitive

Provides `robonix/primitive/camera/snapshot` as raw `bgr8` over gRPC and JPEG over MCP. The default provider ID is `nova5_wrist_rgb`. Captures require calibrated Orbbec RGB and continuous stationary feedback from the deployed `nova5_arm` provider on the same host. Camera identity, intrinsic, hand-eye, work-plane, and pose checks remain enabled. No robot or gripper connection is opened by this package.

Use Linux, Python 3.12 with `venv`, and Robonix on `PATH`. Obtain `nova5-support` and `primitive-dobot-nova5-arm-rbnx`; follow their USB, networking, and calibration instructions. Build from this checkout:

```bash
rbnx setup /absolute/path/to/robonix
export NOVA5_SUPPORT_SOURCE=/absolute/path/to/nova5-support
export NOVA5_HARDWARE_SOURCE=/absolute/path/to/primitive-dobot-nova5-arm-rbnx
rbnx build -p .
```

Both source variables also accept pip VCS URLs pinned to published commits. The build uses `rbnx path robonix-api`, installs `nova5-support[camera]==0.1.0` and `nova5-hardware==0.1.0`, and generates camera and hardware-client interfaces in `rbnx-build/`. `NOVA5_PYTHON` defaults to `python3.12`.

Add the primitive to the robot's `robonix_manifest.yaml`:

```yaml
primitive:
  - name: nova5_wrist_rgb
    path: /absolute/path/to/primitive-dobot-nova5-camera-rbnx
    config:
      calibration_config: /absolute/path/to/calibration/config.json
      arm_provider_id: nova5_arm
```

Start with `rbnx boot -f robonix_manifest.yaml`. Calibration paths resolve relative to `calibration_config`; generate them for the actual hardware with `nova5-support`. The capture subprocess inherits `ROBONIX_ATLAS` and resolves the configured hardware provider. Services bind to loopback.

Image header timestamps are zero because the SDK clock has not been established as an epoch acquisition clock. Host receipt times remain separate metadata. Capture supports stationary windows using same-host monotonic feedback times; it does not support moving-arm synchronization. A timed-out capture retains the camera process and temporary files until it exits; deactivation waits up to 35 seconds and reports failure if ownership cannot be released.

Run hardware-independent tests after building:

```bash
PYTHONPATH="$PWD/rbnx-build/codegen/proto_gen:$PWD/rbnx-build/codegen/robonix_mcp_types" \
  rbnx-build/venv/bin/python -m unittest discover -s tests -v
```

CI runs this build and test sequence on Linux with Python 3.12. Its build
baseline is Robonix commit `e66e4abebd9c2cbb034015f5589592825d65f3df`, with
`robonix-api[codegen]` installed. It installs dependencies from the public
`mikequ95/nova5-support` and `mikequ95/primitive-dobot-nova5-arm-rbnx`
repositories at their `v0.1.0` tags.
