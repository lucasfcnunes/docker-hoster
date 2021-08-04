from sys import platform as _platform

try:
    from loguru import logger
except Exception:
    import logging

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

PATH_FOR_PLATFORM = {
    "linux": "/etc/hosts",
    "darwin": "/etc/hosts",
    "win32": r"C:\Windows\System32\drivers\etc\hosts",
}
temp_path = PATH_FOR_PLATFORM[_platform]
