# lean-benchmark
Simple benchmarking framework for embedded devices

## How to build
Use the `buildit` script to build for a single target and a single build type.
- All targets are represented by a file in the `on` folder.
- Build type is either `debug` or `minSizeRel`

Example:
````
./buildit on/linux debug
````

The script `build-all-targets` builds all targets for a single build type, default is `minSizeRel`.

Example:
````
./build-all-targets
````

The script `build-release` builds all targets for both build types and zip everything.

## Troubl shooting
VSCode tends to interfere with cmake files and force it to use Ninja. If that happens, use the `clean` script.
