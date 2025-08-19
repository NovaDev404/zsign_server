#!/bin/bash
# Install dependencies from PyPI (no apt needed)
pip install --upgrade pip

# Build zsign in a writable directory
cd $HOME
if [ -d "zsign" ]; then
    rm -rf zsign
fi

git clone https://github.com/zhlynn/zsign.git
cd zsign
make

# Install zsign to a writable location
mkdir -p $HOME/.local/bin
cp zsign $HOME/.local/bin/
chmod +x $HOME/.local/bin/zsign

# Add to PATH
echo 'export PATH=$HOME/.local/bin:$PATH' >> $HOME/.bashrc
source $HOME/.bashrc
