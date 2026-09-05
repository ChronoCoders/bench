"""What a measurement module raises when the file cannot carry the measurement.

One class, not one per module. The layer above catches it by name, and a module that
raises the class belonging to a different module, which is what levels and loudness both
do whenever they reach bs1770, left that catch looking for an attribute that was never
there.
"""

from __future__ import annotations


class Unmeasurable(ValueError):
    """The file has no value for this measurement. The message says why."""
