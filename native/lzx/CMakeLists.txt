# Builds the dr2lzx shared library (LZX decoding for dr2kit). See docs/dev/setup.md.
#
#   cmake -S native/lzx -B native/lzx/build -DCMAKE_BUILD_TYPE=Release
#   cmake --build native/lzx/build --config Release
#
# dr2kit finds the result in native/lzx/build/ automatically when run from a checkout.
cmake_minimum_required(VERSION 3.16)
project(dr2lzx C)

add_library(dr2lzx SHARED dr2lzx.c libmspack/lzxd.c)
target_include_directories(dr2lzx PRIVATE libmspack)
set_target_properties(dr2lzx PROPERTIES C_VISIBILITY_PRESET hidden)
if(MSVC)
  # One DLL with the C runtime linked in, so it loads on a machine without the VC redist.
  set_property(TARGET dr2lzx PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded")
  target_compile_definitions(dr2lzx PRIVATE _CRT_SECURE_NO_WARNINGS)
endif()
