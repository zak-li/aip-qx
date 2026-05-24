"""FHE session management using HElib CKKS via pybind11 bindings.

The HElibCKKSSession object owns both the helib::Context and the
helib::SecKey.  It is intentionally constructed once at process startup
(see get_session()) and reused for every scoring call — key generation
is expensive (~1-2 s) and the context is thread-safe for concurrent
encrypt/score operations.

Build the native extension before running:
    cd core/features/fhe && python setup.py build_ext --inplace
Or via CMake directly — see CMakeLists.txt.
"""

from __future__ import annotations

import functools

try:
    from core.features.fhe.helib_ckks import HElibCKKSSession as _HElibCKKSSession
    _fhe_available = True
except ImportError:
    _HElibCKKSSession = None  # type: ignore[assignment,misc]
    _fhe_available = False


@functools.lru_cache(maxsize=1)
def get_session():  # type: ignore[return]
    """Return the process-wide HElib CKKS session (lazy, cached).

    Raises RuntimeError if the native extension has not been compiled.
    """
    if not _fhe_available:
        raise RuntimeError(
            "HElib CKKS native extension not available. "
            "Build it first: cd core/features/fhe && python setup.py build_ext --inplace"
        )
    return _HElibCKKSSession()
