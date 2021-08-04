import pytest
import subprocess
import pathlib
import shutil
from typing import Dict, List
import time
from pyexpect import expect
import re

# from docker_hoster.external import *

import docker
import docker.types

import docker
import docker.models
from docker.models.containers import Container


import docker_hoster

try:
    from loguru import logger
except Exception:
    import logging

    logger = logging.getLogger(__name__)

DOCKER_DIND_NAME = "docker-hoster-dind"

PWD = pathlib.Path(".").resolve()
TEST_ROOT_PATH = pathlib.Path(__file__).parent.resolve() / "dind/root/"

# container internal files/paths
DIND_SOCK_INTERNAL = pathlib.Path("var/run/docker.sock")  # sock
DIND_DATA_INTERNAL = pathlib.Path("var/lib/docker")  # dir
# DIND_CERTS_INTERNAL = pathlib.Path("certs")
DIND_CERTS_INTERNAL = ""  # dir # empty disables https [tls,ssl]
DIND_HOSTS_INTERNAL = pathlib.Path("tmp/hosts")  # file

DIND_SOCK_HOST = None
DIND_HOSTS_HOST = None

# https
# ? tls=True
DIND_HTTP_TLS = False
DIND_HTTP_HOST = None
DIND_HTTP_PORT = 2376 if DIND_CERTS_INTERNAL else 2375
TLS_VERIFY_FLAG = f"--tls={'true' if DIND_HTTP_TLS else 'false'}"

#
NEXT_TRY_WAIT = 10  # seconds


def map_folder_mount_kwargs(
    path: pathlib.Path,
    translation: pathlib.Path,
    volume_type: str = "bind",
) -> Dict:
    "As in docker.types.Mount(**mount_kwargs)"
    mount_kwargs = dict(
        target=str("/" / path),
        source=str(translation / path),
        type=volume_type,
    )
    return mount_kwargs


def map_folder(
    path: pathlib.Path,
    translation: pathlib.Path,
):
    mount_kwargs = map_folder_mount_kwargs(path=path, translation=translation)
    return f"{mount_kwargs['source']!s}:{mount_kwargs['target']!s}"


@pytest.fixture(scope="session")
def tmp_root_path(tmp_path_factory: pytest.TempPathFactory):
    TMP_ROOT_PATH = tmp_path_factory.mktemp("docker-hoster") / "dind/"
    logger.info(f"setting up tmp path {TMP_ROOT_PATH}")
    shutil.copytree(str(TEST_ROOT_PATH), str(TMP_ROOT_PATH))
    yield TMP_ROOT_PATH
    logger.info(f"end tmp path {TMP_ROOT_PATH}")


@pytest.fixture(scope="session")
def dockerd(tmp_root_path: pathlib.Path) -> subprocess.Popen:
    # volumes = " ".join(
    #     f"-v {map_folder(path, tmp_root_path)}"
    #     for path in [
    #         # DIND_DATA_INTERNAL,
    #         # DIND_SOCK_INTERNAL,
    #         # DIND_CERTS_INTERNAL,
    #         # DIND_HOSTS_INTERNAL,
    #     ]
    # )
    volumes = []
    for path in [
        # DIND_DATA_INTERNAL,
        # DIND_SOCK_INTERNAL,
        # DIND_CERTS_INTERNAL,
        DIND_HOSTS_INTERNAL,
    ]:
        mount_kwargs = map_folder_mount_kwargs(path=path, translation=tmp_root_path)
        volumes.append(docker.types.Mount(**mount_kwargs))
        if path == DIND_SOCK_INTERNAL:
            global DIND_SOCK_HOST
            DIND_SOCK_HOST = mount_kwargs["target"]
        elif path == DIND_HOSTS_INTERNAL:
            global DIND_HOSTS_HOST
            DIND_HOSTS_HOST = mount_kwargs["target"]

    logger.info("docker_client setup")
    host_docker_client = docker.from_env()

    logger.info("initializing docker daemon...")
    # ! '--privileged' is, unfortunately, required # https://hub.docker.com/_/docker#Rootless
    dind = host_docker_client.containers.run(
        image="docker:dind-rootless",
        command=f"dockerd-entrypoint.sh {TLS_VERIFY_FLAG}",
        name=DOCKER_DIND_NAME,
        auto_remove=True,
        remove=True,
        stdin_open=True,
        tty=True,
        detach=True,
        mounts=volumes,
        privileged=True,
        environment=[
            f"DOCKER_TLS_CERTDIR={DIND_CERTS_INTERNAL!s}",
        ],
    )
    try:
        # Give the server time to start
        container_up = False
        tries = 4

        for remaining_tries in range(tries, 0, -1):
            logger.info(f"Remaining tries: {remaining_tries}...")
            for message in [dind.logs(tail=3).decode("utf-8")]:
                logger.info(f"logs:\n\n{message}\n")

                if re.match(
                    pattern=rf".*Daemon has completed initialization.*API listen on .+:\d+.*",
                    string=message,
                    flags=re.MULTILINE | re.DOTALL,
                ):
                    container_up = True
                    break
            else:
                time.sleep(NEXT_TRY_WAIT)
                continue

            if container_up:
                break

        expect(container_up, message="Timeout: couldn't expose API...").equal(True)

        logger.info("logs confirmed that docker daemon's up!")

        yield {"dind": dind}

    except Exception as e:
        logger.error(e)
    finally:
        # Shut it down at the end of the pytest session
        logger.info("shutting down docker daemon!")
        dind.stop()
        try:
            dind.remove()
        except Exception as e:
            logger.warning(e)
        logger.info("docker daemon down.")


@pytest.fixture(scope="session")
def dind_docker_client(dockerd: dict) -> docker.DockerClient:
    dind: Container = dockerd["dind"]
    dind_hoster = docker_hoster.HosterContainer(dind)
    global DIND_HTTP_HOST
    # DIND_HTTP_HOST = dind.attrs["NetworkSettings"]["IPAddress"]
    DIND_HTTP_HOST = dind_hoster.info[0]["ip"]

    URI = f"tcp://{DIND_HTTP_HOST}:{DIND_HTTP_PORT}"  # or :2375
    logger.info(f"{URI=}")
    dind_docker_client = docker.DockerClient(base_url=URI, tls=DIND_HTTP_TLS)
    yield dind_docker_client
    logger.info("docker_client teardown")


@pytest.fixture(scope="module")
def create_dummy_containers(
    dind_docker_client: docker.DockerClient,
) -> List[Container]:
    containers: List[Container] = []

    def __create_dummy_containers(n):
        interval = 60
        containers = __create_dummy_containers.containers
        containers += [
            dind_docker_client.containers.run(
                image="busybox",
                command=f"sleep {interval}",
                auto_remove=True,
                remove=True,
                detach=True,
            )
            for _ in range(n)
        ]
        return containers

    __create_dummy_containers.containers = containers

    try:
        yield __create_dummy_containers
    except Exception as e:
        logger.warning(e)
    finally:
        for container in containers:
            try:
                container.remove()
            except Exception:
                pass
