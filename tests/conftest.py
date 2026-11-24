# Home Assistant 2026.11 aliases httpx and httpcore to httpx2 and httpcore2 on
# import. Import it before any test module imports httpx, like HA does at runtime.
import homeassistant  # noqa: F401
