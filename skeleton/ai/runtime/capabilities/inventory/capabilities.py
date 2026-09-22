"""Compatibility facade for capability-inventory classification.

The canonical classifier remains `skeleton.inventory.capabilities` during the
staged AI-tree migration. This facade avoids duplicating credential-name
sentinels under `skeleton.ai`, where provider-bootstrap intentionally treats
those markers as possible credential ownership.
"""

from skeleton.inventory.capabilities import *  # noqa: F401,F403
