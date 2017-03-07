# fslice
LLVM-based forward program slice instrumentation.

## Installation
To run fslice on TestFS, first install the following packages

```
sudo apt-get update
sudo apt-get install cmake binutils-dev build-essential git libxml2-dev
```

Now, download, extract, and compile the LLVM package. Do this in the root directory of `fslice`

```
wget http://llvm.org/releases/3.6.2/llvm-3.6.2.src.tar.xz
wget http://llvm.org/releases/3.6.2/cfe-3.6.2.src.tar.xz

tar xf llvm-3.6.2.src.tar.xz
tar xf cfe-3.6.2.src.tar.xz

rm llvm-3.6.2.src.tar.xz
rm cfe-3.6.2.src.tar.xz

mv llvm-3.6.2.src llvm
mv cfe-3.6.2.src llvm/tools/clang

cd llvm
mkdir build
cmake ../ -DCMAKE_BUILD_TYPE:STRING=Release+Asserts -DLLVM_ENABLE_RTTI:BOOL=ON
make -j2
```

Note you can do `make -j4` or however many CPUs you have available.



