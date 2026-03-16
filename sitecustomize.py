"""Repo-local Python startup customizations.

This repository runs on top of a developer machine that may have globally installed
Pydantic plugins unrelated to the project. Some of those plugins currently fail to
import because of environment-specific OpenTelemetry mismatches, which causes noisy
warnings before our CLI output renders.

Disable the unrelated `logfire` plugin at interpreter startup so local CLI commands
stay clean without changing the user's global Python installation.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYDANTIC_DISABLE_PLUGINS", "logfire-plugin")
