ARG BUILDER_VERSION=master
ARG TARGET=unknon

FROM ghcr.io/finomen/gentoo-embedded-base:${BUILDER_VERSION}

ARG TARGET


RUN crossdev --target ${TARGET}

ADD make.conf.tail /tmp 
ADD portage/package.use /usr/${TARGET}/etc/portage/package.use
ADD portage/bashrc /usr/${TARGET}/etc/portage

ADD binrepos/gentoo-embedded-${TARGET}.conf /usr/${TARGET}/etc/portage/binrepos.conf/

RUN cat /tmp/make.conf.tail >> /usr/${TARGET}/etc/portage/make.conf && \
    rm /tmp/make.conf.tail

