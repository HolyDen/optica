"""Cross-cutting helpers.

Terminal output, prompts, progress, system probing, and the global lock file.

Nothing here imports a non-Core dependency at module level — plan
§ "Exceptions" → *Lazy imports* makes that the mechanism the whole
optional-extras architecture rests on, and these modules are imported by
``optica --version``, which must work with no torch present.
"""

from __future__ import annotations
