# syntax=docker/dockerfile:1

###############################
# AlmaLinux 9 base
# with minimal patches to integrate into CERN computing environment
###############################
FROM gitlab-registry.cern.ch/linuxsupport/alma9-base AS linux-base
LABEL authors="Patrick Odagiu"

# Make sure everything is up to date.
RUN yum update -y

# Get EOS repositories when on CERN network.
# RUN touch /etc/yum.repos.d/eos8al-stable.repo
# RUN echo $'[eos8al-stable] \n\
# name=EOS binaries from CERN Linuxsoft [stable] \n\
# gpgcheck=0 \n\
# enabled=1 \n\
# baseurl=http://linuxsoft.cern.ch/internal/repos/eos8al-stable/x86_64/os \n\
# priority=9' >> /etc/yum.repos.d/eos8al-stable.repo

# Get EOS repositories when not on CERN network.
RUN touch /etc/yum.repos.d/eos9al-tag.repo
RUN echo $'[eos-tag] \n\
name=tagged EOS releases from EOS project \n\
baseurl=https://storage-ci.web.cern.ch/storage-ci/eos/diopside/tag/testing/el-$releasever/$basearch/ \n\
enabled=1 \n\
gpgcheck=0 \n\
priority=10' >> /etc/yum.repos.d/eos8al-tag.repo

RUN echo $'[eos-depend] \n\
name=dependencies for EOS releases from EOS project \n\
baseurl=https://storage-ci.web.cern.ch/storage-ci/eos/diopside-depend/el-$releasever/$basearch/ \n\
enabled=1 \n\
gpgcheck=0 \n\
priority=10' >> /etc/yum.repos.d/eos9al-tag.repo

# Install utils. Alma9 is pretty bare.
RUN yum install -y epel-release

RUN yum install -y \
    gcc \
    openssl-devel \
    bzip2-devel \
    libffi-devel \
    zlib-devel \
    ca-certificates \
    jemalloc \
    zeromq \
    autofs \
    findutils \
    hostname \
    tar \
    udev \
    which \
    curl \
    curl-devel \
    iproute \
    gcc-c++  \
    git \
    wget \
    make \
    cmake \
    nano \
    git-lfs \
    ncurses-libs \
    ncurses-devel \
    libX11 \
    libXrender \
    libXtst \
    davix-devel \
    diffutils \
    file \
    fuse-devel \
    glibc-langpack-en \
    ncurses-compat-libs \
    graphviz \
    gtest-devel \
    json-c-devel \
    krb5-devel \
    libmacaroons-devel \
    libtool \
    libuuid-devel \
    libxml2-devel \
    openssl-devel \
    python3-devel \
    python3-setuptools \
    readline-devel \
    scitokens-cpp-devel \
    systemd-devel \
    tinyxml-devel \
    voms-devel \
    yasm \
    zlib-devel \
    poppler-utils && \
    yum clean all

# Install EOS and xrootd for remote file access at CERN.
RUN yum install -y \
    eos-client \
    xrootd-client \
    xrootd-server \
    python3-xrootd


################################
# PYTHON-BASE
# Sets up all our shared environment variables
################################
FROM linux-base AS python-base

# Install python 3.10.
RUN wget https://www.python.org/ftp/python/3.10.14/Python-3.10.14.tar.xz && \
    tar -xf Python-3.10.14.tar.xz 
WORKDIR /Python-3.10.14
RUN ./configure --enable-optimizations && \ 
    make -j 2 && \
    nproc && \
    make install

# Restore workdir.
WORKDIR /

# Set up the environment variables.
ENV PYTHONUNBUFFERED=1 \
    # pip
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    \
    # Poetry
    # https://python-poetry.org/docs/configuration/#using-environment-variables
    POETRY_VERSION=2.1.3 \
    # Make poetry install to this location.
    POETRY_HOME="/opt/poetry" \
    # Do not ask any interactive question.
    POETRY_NO_INTERACTION=1 \
    # Never create virtual environment automaticly, only use env prepared by us.
    POETRY_VIRTUALENVS_CREATE=false \
    \
    # This is where our requirements + virtual environment will live.
    VIRTUAL_ENV="/venv"

# Prepend poetry and venv to path.
ENV PATH="$POETRY_HOME/bin:$VIRTUAL_ENV/bin:$PATH"

# Prepare virtual env.
RUN python3.10 -m venv $VIRTUAL_ENV

# Specify the working directory in the image.
WORKDIR /adl1t_datamaker

# Set up the pythonpath.
ENV PYTHONPATH="/app:$PYTHONPATH"


################################
# BUILDER-BASE
# Used to build deps + create our virtual environment
################################
FROM python-base AS builder-base
RUN yum install -y \
    gnupg \
    gpg

# Install poetry.
# The --mount will mount the buildx cache directory to where
# Poetry and Pip store their cache so that they can re-use it
RUN --mount=type=cache,target=/root/.cache \
    curl -sSL https://install.python-poetry.org | python3.10 -

# Go inside the working directory and copy the relevant files for the package.
WORKDIR /adl1t_datamaker
COPY poetry.lock pyproject.toml ./
COPY scripts/ ./scripts/
COPY src/ ./src/
COPY README.md ./

# Install the dependencies to the virtual environment specified in $VIRTUAL_ENV
RUN --mount=type=cache,target=/root/.cache \
    poetry install


################################
# DEVELOPMENT
# Image used during development / testing
################################
FROM builder-base AS development

WORKDIR /adl1t_datamaker

# Quicker install as runtime deps are already installed
RUN --mount=type=cache,target=/root/.cache \
    poetry install

CMD ["bash"]


################################
# PRODUCTION
# Final image used for runtime
################################
FROM python-base AS production

RUN yum install -y \
    ca-certificates && \
    yum clean all

# Copy in our built poetry + venv.
COPY --from=builder-base $POETRY_HOME $POETRY_HOME
COPY --from=builder-base $VIRTUAL_ENV $VIRTUAL_ENV

WORKDIR /adl1t_datamaker
COPY poetry.lock pyproject.toml ./
COPY scripts/ ./scripts/
COPY src/ ./src/
COPY README.md ./

CMD ["bash"]
