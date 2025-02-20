#FROM python:3.6.4
#FROM continuumio/miniconda3

#FROM tensorflow/tensorflow:1.13.1-gpu-py3
FROM  tensorflow/tensorflow:latest-gpu-jupyter

RUN apt-get update && apt-get install -y --no-install-recommends \
      bzip2 \
      g++ \
      git \
      graphviz \
      libgl1-mesa-glx \
      libhdf5-serial-dev \
      openmpi-bin \
      wget \
      libxext6 libsm6 libxrender-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /opt/app/requirements.txt
WORKDIR /opt/app

RUN pip install --default-timeout=60 -r requirements.txt
RUN pip install git+https://github.com/PyTables/PyTables.git@v3.5.2
RUN pip install imgaug==0.2.9
RUN pip install intervals==0.9.0
RUN pip install notebook==6.1.1

RUN apt-get update && apt-get install -y --no-install-recommends tmux

# Set keras backend to tensorflow by default
ENV KERAS_BACKEND tensorflow

# Install PyTables from source
# COPY ./PyTables /opt/app/PyTables
# WORKDIR /opt/app/PyTables
# RUN python setup.py install
# WORKDIR /opt/app

# COPY . /opt/app
