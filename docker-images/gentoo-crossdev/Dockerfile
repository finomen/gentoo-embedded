ARG BUILDER_VERSION=master
ARG TARGET=unknon

FROM ghcr.io/finomen/gentoo-embedded-base:${BUILDER_VERSION}

ARG TARGET

RUN crossdev --target ${TARGET}
