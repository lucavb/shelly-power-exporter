import importlib.metadata


def get_version() -> str:
    """Read version from package metadata."""
    try:
        # setuptools-scm reads version from git tags and makes it available via importlib.metadata
        return importlib.metadata.version("shelly-power-exporter")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
