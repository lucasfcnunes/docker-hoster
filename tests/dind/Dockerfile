# syntax = docker/dockerfile:experimental
# FROM busybox AS flavors

# USER root
# RUN wget https://github.com/docker/compose/releases/download/1.29.2/docker-compose-Linux-x86_64 -O docker-compose
# RUN chmod +x docker-compose

FROM docker:dind-rootless AS base

USER root
RUN wget "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" > ~/docker-compose
RUN chmod +x ~/docker-compose
RUN mv ~/docker-compose /usr/local/bin/docker-compose
RUN ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
USER rootless

FROM base

RUN dockerd-entrypoint.sh dockerd
WORKDIR /docker-hoster/
ADD ../../ /docker-hoster/
RUN docker build . --tag docker-hoster --target prod
