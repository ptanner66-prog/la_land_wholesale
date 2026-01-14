"""Application bootstrap entrypoint.

This script serves as the main entry point for bootstrapping the application,
running migrations, and validating the environment. It delegates to the
core bootstrap logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src directory to python path if running as script
if __name__ == "__main__":
    src_path = Path(__file__).parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))

from core.bootstrap import bootstrap_application, validate_environment
from core.logging_config import setup_logging, get_logger

LOGGER = get_logger(__name__)


def main() -> None:
    """Run the bootstrap process."""
    setup_logging()
    LOGGER.info("Starting application bootstrap...")
    
    try:
        # 1. Validate environment
        validate_environment()
        LOGGER.info("Environment validation passed")
        
        # 2. Run bootstrap (migrations, extensions)
        bootstrap_application()
        LOGGER.info("Bootstrap completed successfully")
        
    except Exception as exc:
        LOGGER.critical("Bootstrap failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
