# fslice
LLVM-based forward program slice instrumentation.

## Installation
To run fslice on TestFS, first install the following packages

```
sudo apt-get update
sudo apt-get install cmake binutils-dev build-essential git
```

Now, compile the LLVM package

```
cd llvm
./configure
make
```

Note that it is not necessary to `make install` as the bootstrap script actually calls the executable directly from the build directory.

