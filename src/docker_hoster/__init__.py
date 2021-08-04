"""
Docker Hoster!
"""

from .hoster import Hoster, HosterContainer, HosterContainerCollection
from . import external

__all__ = [
    Hoster,
    HosterContainerCollection,
    HosterContainer,
]

try:
    from loguru import logger
except Exception:
    import logging

    logger = logging.getLogger(__name__)

logger.debug(f"{__package__}")

__title__ = "docker_hoster"
