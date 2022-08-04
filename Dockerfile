FROM ubuntu:20.04 as build

ARG LIBVA_VERSION=2.15.0
ARG GMMLIB_VERSION=22.1.4
ARG INTEL_MEDIA_DRIVER_VERSION=22.4.4
ARG FFMPEG_VERSION=4.4.2
ARG OPENCV_PYTHON_VERSION=66

ARG BUILD_DEPS="\
    build-essential \
    pkg-config \
    git \
    autoconf \
    automake \
    cmake \
    libtool \
    libdrm-dev \
    yasm \
    nasm \
    python3-pip \
"

ARG FFMPEG_CONFIG="\
    --disable-debug \
    --enable-shared \
    --enable-pic \
    --disable-doc \
    --disable-htmlpages \
    --disable-manpages \
    --disable-podpages \
    --disable-txtpages \
    --enable-vaapi \
"

ARG CMAKE_ARGS="\
    -DWITH_JPEG=ON \
    -DWITH_FFMPEG=ON \
    -DWITH_V4L=ON \
    -DWITH_1394=OFF \
    -DWITH_VTK=OFF \
    -DWITH_EIGEN=OFF \
    -DWITH_GSTREAMER=OFF \
    -DWITH_GTK=OFF \
    -DWITH_IPP=OFF \
    -DWITH_OPENVINO=OFF \
    -DWITH_JASPER=OFF \
    -DWITH_OPENJPEG=OFF \
    -DWITH_OPENEXR=OFF \
    -DWITH_TIFF=OFF \
    -DWITH_OPENCLAMDFFT=OFF \
    -DWITH_OPENCLAMDBLAS=OFF \
    -DWITH_LAPACK=OFF \
    -DWITH_ITT=OFF \
    -DWITH_PROTOBUF=OFF \
    -DWITH_IMGCODEC_HDR=OFF \
    -DWITH_IMGCODEC_SUNRASTER=OFF \
    -DWITH_IMGCODEC_PXM=OFF \
    -DWITH_IMGCODEC_PFM=OFF \
    -DWITH_QUIRC=OFF \
    -DWITH_OBSENSOR=OFF \
"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install ${BUILD_DEPS} -y && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --upgrade pip

WORKDIR /

# libva
RUN git clone https://github.com/intel/libva.git -b ${LIBVA_VERSION} && \
    cd /libva && \
    ./autogen.sh && ./configure && \
    make -j$(nproc) install

# libva-utils
RUN git clone https://github.com/intel/libva-utils.git -b ${LIBVA_VERSION} && \
    cd /libva-utils && \
    ./autogen.sh && ./configure && \
    make -j$(nproc) install

WORKDIR /

# gmmlib
RUN git clone https://github.com/intel/gmmlib.git -b intel-gmmlib-${GMMLIB_VERSION} && \
    mkdir gmmlib/build && \
    cd /gmmlib/build && \
    cmake -DCMAKE_BUILD_TYPE= Release .. && \
    make -j$(nproc) install

# Intel Media Driver
RUN git clone https://github.com/intel/media-driver.git -b intel-media-${INTEL_MEDIA_DRIVER_VERSION} && \
    mkdir media-driver/build && \
    cd /media-driver/build && \
    cmake .. && \
    make -j$(nproc) install

# FFmpeg
RUN git clone https://github.com/FFmpeg/FFmpeg.git -b n${FFMPEG_VERSION} && \
    cd /FFmpeg && \
    ./configure ${FFMPEG_CONFIG} && make -j$(nproc) install

# OpenCV
RUN git clone --recursive https://github.com/opencv/opencv-python.git -b ${OPENCV_PYTHON_VERSION} && \
    cd opencv-python && \
    export ENABLE_HEADLESS=1 && \
    export ENABLE_CONTRIB=0 && \
    python3 -m pip wheel . --verbose

FROM ubuntu:20.04

ARG DEPS="\
    python3 \
    python3-pip \
    libdrm2 \
"

COPY *.py *.txt /app/

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt install ${DEPS} -y && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local/bin/ffmpeg /usr/local/bin/
COPY --from=build /usr/local/bin/vainfo /usr/local/bin/
COPY --from=build /usr/local/lib/ /usr/local/lib/
COPY --from=build /usr/local/lib/dri/ /usr/local/lib/dri/
COPY --from=build /opencv-python/opencv_python_headless*.whl /

RUN ldconfig

WORKDIR /app

RUN python3 -m pip install -r requirements-docker.txt && \
    python3 -m pip install /*.whl && \
    rm /*.whl
