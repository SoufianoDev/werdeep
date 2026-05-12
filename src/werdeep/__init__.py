"""WeRDeep - Deep web search and research tool for OpenCode.

WeRDeep provides comprehensive web crawling and content extraction
capabilities for AI agents through the OpenCode tool system.
"""

from werdeep.config.ssl_bootstrap import patch_ssl

patch_ssl()

__version__ = "1.0.0"
__author__ = "SoufianoDev"

__all__ = ["__version__", "__author__"]
