ARG BUILDER_VERSION=master
ARG TARGET=unknon

FROM ghcr.io/finomen/gentoo-embedded-base:${BUILDER_VERSION}

ARG TARGET

ADD make.conf.tail /tmp 
ADD portage /usr/${TARGET}/etc/portage
ADD binrepos/gentoo-embedded-${TARGET}.conf /usr/${TARGET}/etc/portage/binrepos.conf/

RUN crossdev --target ${TARGET} && \
    cat /tmp/make.conf.tail >> /usr/${TARGET}/etc/portage/make.conf && \
    rm /tmp/make.conf.tail

