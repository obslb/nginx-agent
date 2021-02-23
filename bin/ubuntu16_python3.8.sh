#!/bin/sh

# install PPA
sudo add-apt-repository ppa:deadsnakes/ppa

# update and install
sudo apt update
sudo apt install python3.8 python3.8-dev python3.8-venv

# setup alternatives
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.5 1
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 2

# show menu for selecting the version
sudo update-alternatives --config python3

# or one command to set it
# sudo update-alternatives --set python3 /usr/bin/python3.8