# motion_lang/modules.py
"""Python interoperability for Motion Language.

Resolves ``import`` statements that target the Python ecosystem instead of
``.hmg`` modules:

* standard library / third-party packages: ``import math``,
  ``import numpy as np``, ``import os.path``
* local ``.py`` scripts: ``import helpers`` (resolved against the importing
  script's directory) or ``import x from "file.py"``

Imported modules are bound into the DSL scope as plain Python objects, so
attribute reads (``np.pi``), chained paths (``os.path.join``) and calls
(``math.sin(x)``) work natively in ``.hmg`` files.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from types import ModuleType
from typing import Any, Dict, List, Optional, Tuple


def default_bind_name(dotted: str) -> str:
    """Binding for ``import a.b.c`` (Python semantics): the top component."""
    return dotted.split(".")[0]


def import_dotted(dotted: str, base_dir: Optional[str] = None) -> ModuleType:
    """Import ``a.b.c`` via the import system, falling back to local files.

    Tries :func:`importlib.import_module` first; if that fails and
    ``base_dir`` is given, attempts ``<base>/<a>/<b>/<c>.py``,
    ``<base>/<a>/<b>/<c>/__init__.py`` and ``<base>/<a>.py`` so scripts
    sitting next to the ``.hmg`` file resolve without ``sys.path`` hacks.
    """
    try:
        return importlib.import_module(dotted)
    except ImportError:
        pass
    if base_dir:
        parts = dotted.split(".")
        candidates = [
            os.path.join(base_dir, *parts) + ".py",
            os.path.join(base_dir, *parts, "__init__.py"),
        ]
        if len(parts) > 1:
            candidates.append(os.path.join(base_dir, parts[0] + ".py"))
        for cand in candidates:
            if os.path.isfile(cand):
                return load_py_file(cand, dotted)
    raise ImportError(f"No Python module named '{dotted}'.")


def load_py_file(path: str, name: Optional[str] = None) -> ModuleType:
    """Load a ``.py`` file as a module (for ``from "helpers.py"`` imports)."""
    full = os.path.abspath(path)
    mod_name = name or os.path.splitext(os.path.basename(full))[0]
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in mod_name)
    unique = f"_hmg_py_{safe}"
    spec = importlib.util.spec_from_file_location(unique, full)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load Python file '{path}'.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(unique, None)
        raise
    return module


def resolve_py_import(items: List[Tuple[str, Optional[str]]],
                      base_dir: Optional[str] = None) -> Dict[str, Any]:
    """Resolve ``[(dotted, alias|None), ...]`` to ``{binding: module}``."""
    bound: Dict[str, Any] = {}
    for dotted, alias in items:
        try:
            module = import_dotted(dotted, base_dir)
        except ImportError as exc:
            print(f"[DSL Warning] Python import failed: {exc}")
            continue
        if alias:
            bound[alias] = module
        else:
            # Python semantics: `import os.path` binds `os`.
            top = default_bind_name(dotted)
            bound[top] = sys.modules.get(top, module)
    return bound
