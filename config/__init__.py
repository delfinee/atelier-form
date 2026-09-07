"""Expose the backend Django configuration from the repository root.

Vercel's Django detector imports ``config.wsgi`` from the project root.  The
application keeps its Django packages under ``backend/``, so extend this
package's search path to make the existing configuration modules available
without duplicating them.
"""

from pathlib import Path

_backend_config = Path(__file__).resolve().parent.parent / "backend" / "config"
__path__.append(str(_backend_config))
