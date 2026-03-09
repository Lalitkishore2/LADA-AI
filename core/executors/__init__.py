"""
LADA Executor Base — Interface for command executors.

Each executor handles a domain of commands (system, browser, files, etc.)
and is called by JarvisCommandProcessor.process() in priority order.
"""

from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class BaseExecutor:
    """
    Base class for command executors.

    Subclasses implement `try_handle(cmd)` which returns:
    - (True, response_str)  if the command was handled
    - (False, "")           if the command is not in this executor's domain
    """

    def __init__(self, core):
        """
        Args:
            core: The JarvisCommandProcessor instance (provides access to all subsystems).
        """
        self.core = core

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        """
        Try to handle a command.

        Returns:
            (handled: bool, response: str)
        """
        raise NotImplementedError

    @property
    def name(self) -> str:
        return self.__class__.__name__
