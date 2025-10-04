"""Top-level backend package marker to ensure 'backend' is a proper package in the container image.__all__ = ["app"]


Having this file avoids any ambiguity with namespace packages when importing `backend.app`.
"""
__all__ = ["app"]
