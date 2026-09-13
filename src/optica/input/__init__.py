"""The Input Manager and its adapters.

Implements plan § "Input & Acquisition". Every route into the pipeline — local
folders, manifests, and remote fetches — ends in an ``ImageFolder``-compatible
structure, and this package is where each route is turned into one.

Nothing here prompts. Prompts live in the CLI layer and the Python API raises
instead (plan § "Python API"), so where a decision needs an answer this package
takes a callback or returns the question rather than asking it.
"""

from __future__ import annotations
