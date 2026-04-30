"""FHE session management using HElib CKKS via pybind11 bindings.

The HElibCKKSSession object owns both the helib::Context and the
helib::SecKey.  It is intentionally constructed once at process startup
(see get_session()) and reused for every scoring call — key generation
is expensive (~1-2 s) and the context is thread-safe for concurrent
encrypt/score operations.

Build the native extension before running:
    cd backend/features/fhe && python setup.py build_ext --inplace
Or via CMake directly — see CMakeLists.txt.
"""

from __future__ import annotations

import functools

# helib_ckks is the compiled pybind11 module produced by helib_ckks.cpp.
# Import error is intentional here: if the .so/.pyd is missing the caller
# gets a clear ImportError rather than a silent runtime crash.
from backend.features.fhe.helib_ckks import HElibCKKSSession


@functools.lru_cache(maxsize=1)
def get_session() -> HElibCKKSSession:
    """Return the process-wide HElib CKKS session (lazy, cached)."""
    return HElibCKKSSession()
