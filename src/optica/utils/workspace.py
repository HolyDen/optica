"""Creating the folders Optica owns, gitignored on the way in.

Implements plan § "Project layout" l.289:

    **Gitignored:** ``./checkpoints/`` and ``./optica-output/`` … When Optica
    first creates either folder, it drops a ``.gitignore`` containing ``*``
    **inside that folder**. Optica never touches the user's project-level or
    global ``.gitignore``.

Both halves of that sentence matter, and they pull in opposite directions: the
first asks Optica to write a file the user did not ask for, the second forbids
it from touching the user's own ignore rules. :func:`create_ignored` is where
the line between them is drawn.

**The trigger is creation, and only creation.** A folder that already exists
gets nothing — not a new ``.gitignore``, not an edited one. l.289 says *when
Optica first creates either folder*, and reading it any more loosely would have
Optica write into a directory the user made, which is the behaviour the
sentence's second half exists to rule out. It follows that a ``.gitignore`` the
user put there can never be overwritten: the only directory this function writes
into is one that did not exist a moment earlier, so there is nothing in it to
overwrite.

**``dataset/`` is deliberately not covered.** The plan gitignores exactly two
folders, and ``dataset/`` is not one of them — it is the user's curated data,
which they may well want committed. Do not extend this module to it.

*Known gap, and it follows from the reading above:* a ``checkpoints/`` or output
folder created before this shipped never gains a ``.gitignore``, because Optica
will not be the one creating it. The README tells users to add both folders to
their own ``.gitignore``, which covers that case and costs them nothing if they
are already covered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

__all__ = [
    "GITIGNORE_BODY",
    "GITIGNORE_FILE",
    "create_ignored",
]

GITIGNORE_FILE: Final = ".gitignore"
"""The file dropped inside a folder Optica creates."""

GITIGNORE_BODY: Final = "*\n"
"""What it contains. l.289 specifies ``*``; the newline is text-file convention,
and git reads the two identically."""


def create_ignored(path: Path) -> bool:
    """Create ``path``, and drop a ``.gitignore`` containing ``*`` inside it.

    Missing parents are created too, but only ``path`` itself is given a
    ``.gitignore`` — l.289 names the folder, not the chain leading to it.

    Args:
        path: The folder to create. One of the two l.289 names: a
            ``checkpoints/`` root, or an ``--output`` container.

    Returns:
        True when this call created the folder and wrote the file; False when
        the folder was already there, in which case nothing was written and
        anything already inside it — including the user's own ``.gitignore`` —
        is untouched.
    """
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        return False
    (path / GITIGNORE_FILE).write_text(GITIGNORE_BODY, encoding="utf-8")
    return True
