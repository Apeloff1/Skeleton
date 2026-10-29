"""Canonical AI model-provider runtime for the Skeleton engine.

Provider-specific SDK objects, credentials, governance/admission checks, and
provider network policy live behind this engine-owned boundary. Application
code may consume these neutral contracts through compatibility facades, but it
must not create a second credential-bearing provider runtime.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import io
import json
import math
import os
import platform
import socket
import threading
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass, field, replace
from skeleton.compat_datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from importlib import metadata as package_metadata
from importlib.util import find_spec
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4
