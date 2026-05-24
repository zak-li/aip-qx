"""
Build the HElib pybind11 extension with setuptools.

Usage:
    pip install pybind11 cmake
    python setup.py build_ext --inplace

HElib must be installed and discoverable by CMake (set HELIB_DIR if needed):
    cmake -B _build -DCMAKE_BUILD_TYPE=Release -Dhelib_DIR=/path/to/helib/lib/cmake/helib
    cmake --build _build --target helib_ckks
    cp _build/helib_ckks*.so .   # or .pyd on Windows

Alternatively, run the CMake build directly (see CMakeLists.txt).
"""

import os
import subprocess
from pathlib import Path

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class CMakeExtension(Extension):
    def __init__(self, name: str):
        super().__init__(name, sources=[])
        self.source_dir = Path(__file__).parent.resolve()


class CMakeBuild(build_ext):
    def build_extension(self, ext: CMakeExtension) -> None:
        build_dir = Path(self.build_temp) / ext.name
        build_dir.mkdir(parents=True, exist_ok=True)

        output_dir = Path(self.get_ext_fullpath(ext.name)).parent.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        cmake_args = [
            f"-DCMAKE_BUILD_TYPE={'Debug' if self.debug else 'Release'}",
            f"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={output_dir}",
        ]

        if helib_dir := os.environ.get("HELIB_DIR"):
            cmake_args.append(f"-Dhelib_DIR={helib_dir}")

        subprocess.check_call(  # noqa: S603
            ["cmake", str(ext.source_dir), *cmake_args], cwd=build_dir  # noqa: S607
        )
        subprocess.check_call(  # noqa: S603
            ["cmake", "--build", ".", "--target", "helib_ckks",  # noqa: S607
             "--config", "Release", "--parallel"],
            cwd=build_dir,
        )


setup(
    name="helib_ckks",
    version="1.0.0",
    ext_modules=[CMakeExtension("helib_ckks")],
    cmdclass={"build_ext": CMakeBuild},
    zip_safe=False,
)
