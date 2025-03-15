
__version__ = "???"
try:  # Python > 3.8+
    from importlib_metadata import version
    __version__ = version("ivcap_ai_tool")
except ImportError:
    try:
        import pkg_resources
        __version__ = pkg_resources.get_distribution('ivcap_ai_tool').version
    except Exception:
        pass
