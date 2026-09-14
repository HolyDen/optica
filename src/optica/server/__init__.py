"""The browser server that ``optica label`` and ``optica curate`` share.

Implements plan § "Labeling & Curation". FastAPI and uvicorn are the
``optica[web]`` extra, so only :mod:`optica.server.routes` imports them, and only
:mod:`optica.server.app` imports that module — lazily, at the point a server
starts.
"""

from __future__ import annotations
