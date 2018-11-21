
#
# docker build -t open_nsfw .
# docker run open_nsfw classify_nsfw.py http://example.org/1.warc.gz http://example.org/2.warc.gz
#

## caffe ##

# We use an old verison of intel/caffe as the latest version is broken:
# https://github.com/intel/caffe/issues/219

FROM centos:7
RUN yum install -y epel-release && \
    yum install -y \
        redhat-rpm-config \
        tar \
        findutils \
        make \
        gcc-c++ \
        cmake \
        git \
        wget \
        atlas-devel \
        boost-devel \
        gflags-devel \
        glog-devel \
        hdf5-devel \
        leveldb-devel \
        lmdb-devel \
        opencv-devel \
        protobuf-devel \
        snappy-devel \
        protobuf-compiler \
        freetype-devel \
        libpng-devel \
        python-devel \
        python-numpy \
        python-pip \
        python-scipy \
        gcc-gfortran \
        libjpeg-turbo-devel && \
    yum clean all

# Need newer pip to build matplotlib
RUN pip install --upgrade pip

ENV CAFFE_ROOT=/opt/caffe
WORKDIR $CAFFE_ROOT

ENV CLONE_TAG=1.0.3a

RUN git clone -b ${CLONE_TAG} --depth 1 https://github.com/intel/caffe.git . && \
    for req in $(cat python/requirements.txt) pydot; do pip --no-cache-dir install $req; done && \
    mkdir build && cd build && \
    cmake -DCPU_ONLY=1 -DCMAKE_BUILD_TYPE=Release .. && \
    make all -j"$(nproc)"

ENV PYCAFFE_ROOT $CAFFE_ROOT/python
ENV PYTHONPATH $PYCAFFE_ROOT:$PYTHONPATH
ENV PATH $CAFFE_ROOT/build/tools:$PYCAFFE_ROOT:$PATH
RUN echo "$CAFFE_ROOT/build/lib" >> /etc/ld.so.conf.d/caffe.conf && ldconfig

## open_nsfw ##

RUN mkdir /opt/open_nsfw \
 && pip install warcio
WORKDIR /opt/open_nsfw
COPY . /opt/open_nsfw
CMD python classify_warc.py
