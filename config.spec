# SPDX-License-Identifier: MulanPSL-2.0
specVersion: 1
description: Nova5 wrist RGB camera paired with stationary robot feedback.
required: [calibration_config]
properties:
  calibration_config:
    type: string
    description: Required existing absolute calibration JSON path, for example /opt/nova5/calibration/config.json. Calibration paths resolve relative to it; missing files or mismatched calibration reject capture.
  arm_provider_id:
    type: string
    default: nova5_arm
    description: Same-host hardware provider instance, for example nova5_arm. Missing or stale feedback rejects capture.
