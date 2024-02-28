ARG PORTAGE_VERSION=latest
ARG STAGE3_VERSION=amd64-openrc

FROM gentoo/portage:${PORTAGE_VERSION} as portage
FROM gentoo/stage3:${STAGE3_VERSION}

COPY --from=portage /var/db/repos/gentoo /var/db/repos/gentoo

# TODO: ebuild for binhost?

RUN emerge -vq dev-python/PyGithub eix vim crossdev && eix-update

ADD portage /etc/portage
ADD crossdev.conf /etc/portage/respos.conf/crossdev.conf

RUN \ 
    cat /etc/portage/make.conf.tail >> /etc/portage/make.conf && \
    rm /etc/portage/make.conf.tail && \
    mkdir -p /var/db/repos/crossdev/{profiles,metadata} && \
    echo 'crossdev' > /var/db/repos/crossdev/profiles/repo_name && \
    echo 'masters = gentoo' > /var/db/repos/crossdev/metadata/layout.conf && \
    chown -R portage:portage /var/db/repos/crossdev

