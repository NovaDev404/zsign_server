#!/bin/bash
apt-get update
apt-get install -y git openssl libssl-dev zlib1g-dev
git clone https://github.com/zhlynn/zsign.git
cd zsign
make
cp zsign /usr/local/bin/
