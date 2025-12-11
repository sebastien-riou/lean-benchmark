# lean-benchmark
Simple yet flexible benchmarking framework for embedded devices.

## Introduction
lean-benchmark is a library meant to be executed on the target to benchmark. It comes with a python script which parse the output of the library. 

The library measure the execution time and the stack size actually consumed in one run.
The user specify how to get the current time on the target platform, so the reported number can be either time or clock cycles.

The library allows to add associated data to each trial. For example, if benchmarking ML-DSA sign operation, it is useful to report the number of repetitions that occured.

The user specify how many trials must be done in a 'record'.
In a single run the target can generate several records of the same type or of different types: 
- same function, same arguments
- same function, different arguments
- different functions
- ...

See [main.c](test/source/main.c) for an example of integration.

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

### Trouble shooting
VSCode tends to interfere with cmake files and force it to use Ninja. If that happens, use the `clean` script.

## How to use
This example runs on Linux but the principle is the same with an embedded target.

1. Run the target: `./build/linux/lean-benchmark-test-fw`
2. In a second terminal, run the python script: `pipenv run python lean_benchmark.py --device /dev/pts/?` (replace '?' with the number reported by the target)

The result are displayed in the second terminal and are also captured in a python pickle file for easy export.
The pickle file can be read back using:
````
pipenv run python lean_benchmark.py --describe file.pickle
````

For embedded targets, it is also possible to just capture the UART output and then parse this output with the python script:
````
pipenv run python lean_benchmark.py --uart-log uart-rv64imc.log
```` 

## How to make a release package
The script `build-release` builds all targets for both build types and zip everything.
By default it build for Linux and launch the test. This requires use interaction currently
so it is recommend to disable it by providing '0' as argument. 

Example:
````
./build-release 0
````
