# syntax = docker/dockerfile:experimental
FROM python:3-alpine as base
LABEL maintainer="lucasfc.nunes@gmail.com"

ARG NAME="docker-hoster"
ARG BUILD_VERSION="0.1.0"
ARG BUILD_DATE
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.build-date=$BUILD_DATE
LABEL org.label-schema.name="lucasfcnunes/docker-hoster"
LABEL org.label-schema.description=""
LABEL org.label-schema.vcs-url="https://github.com/lucasfcnunes/docker-hoster"
LABEL org.label-schema.version=$BUILD_VERSION
LABEL org.label-schema.docker.cmd="docker run -v etc/hosts:/tmp/hosts -v docker.sock:/tmp/docker.sock -d lucasfcnunes/docker-hoster"

WORKDIR /dist
COPY ./dist /dist

# python-hosts uses git
RUN apk add --no-cache git

RUN --mount=type=cache,mode=0755,target=/root/.cache/pip \
    pip install ${NAME}-${BUILD_VERSION}.tar.gz
# ADD ./src/docker-hoster/ /docker-hoster

## -- debug
FROM base as dev
LABEL description="debug"
RUN --mount=type=cache,mode=0755,target=/root/.cache/pip \
    pip install debugpy
WORKDIR /app/
CMD python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m docker_hoster

## -- prod
FROM base as prod
LABEL description="prod"
CMD python -O -m docker_hoster
