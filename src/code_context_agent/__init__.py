"""Code Context Agent - A CLI tool for code context analysis."""

import os

# Disable OpenTelemetry SDK before any strands imports to avoid
# context detachment errors in async generators.
# This MUST happen before any strands modules are imported.
# Can be overridden by setting CODE_CONTEXT_OTEL_DISABLED=false
if os.environ.get("CODE_CONTEXT_OTEL_DISABLED", "true").lower() != "false":
    os.environ["OTEL_SDK_DISABLED"] = "true"

__version__ = "0.3.3"
__all__ = ["__version__"]
