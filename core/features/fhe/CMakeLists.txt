cmake_minimum_required(VERSION 3.18)
project(helib_ckks_binding CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# --- Dependencies -----------------------------------------------------------
find_package(helib REQUIRED)
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)
find_package(pybind11 REQUIRED)

# --- Extension module -------------------------------------------------------
pybind11_add_module(helib_ckks helib_ckks.cpp)

target_link_libraries(helib_ckks PRIVATE helib::helib)

# Place the compiled .so/.pyd next to the Python sources so that
# `from core.features.fhe import helib_ckks` resolves without PYTHONPATH hacks.
set_target_properties(helib_ckks PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
)

# --- Installation hint -------------------------------------------------------
# After building, copy the .so into the package directory:
#   cmake -B build -DCMAKE_BUILD_TYPE=Release
#   cmake --build build --target helib_ckks
