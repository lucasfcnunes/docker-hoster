import sys
import signal
import pathlib
import os
import tempfile
import shutil

import docker
from docker.models.containers import Container, ContainerCollection
import python_hosts

from collections import UserDict
from typing import Dict, Iterator, List, Union
from pyexpect import expect
import pprint
import difflib
from loguru import logger

logger
# TODO: add test scripts
# TODO: use difflib
# TODO: docker-py filters
# TODO: feature SAME_NETWORK bool
# docker run --rm busybox cat /proc/self/cgroup | head -1 | tr --delete ‘11:memory:/docker/’


class HosterContainer:
    def __init__(
        self,
        container: Union[str, Container],
        docker_client: docker.DockerClient = None,
        update=True,
    ) -> None:
        if isinstance(container, Container):
            self.__container = container
            self.__docker_client = container.client
        elif isinstance(container, str):
            expect(docker_client).isinstance(docker.DockerClient)
            self.__docker_client = docker_client
            self.__container = self.__docker_client.containers.get(container)
        else:
            raise ValueError

        self.__id = self.__container.id
        self.__info = {}

        if update:
            self.update()

    @property
    def id(self) -> str:
        return self.__id

    @property
    def container(self) -> Container:
        return self.__container

    @property
    def info(self) -> List[Dict]:
        return self.__info

    def __fetch_new_info(self) -> List[Dict]:
        # extract all the info with the docker api
        container_id = self.id
        info = self.__docker_client.api.inspect_container(container_id)
        container_hostname = info["Config"]["Hostname"]
        container_name = info["Name"].strip("/")
        container_ip = info["NetworkSettings"]["IPAddress"]
        if not container_ip:
            network_mode = info.get("HostConfig", {}).get("NetworkMode", "")
            if network_mode:
                if network_mode.startswith("container:"):
                    pid = network_mode[10:]
                    pinfo = self.__docker_client.api.inspect_container(pid)
                    info = pinfo
                elif network_mode in ("host",):
                    container_ip = "127.0.0.1"
                elif network_mode in ("default",):
                    pass
                else:
                    raise NotImplementedError(f"{network_mode=} is not implemented")

        if info["Config"]["Domainname"]:
            container_hostname = container_hostname + "." + info["Config"]["Domainname"]

        result = []

        for values in info["NetworkSettings"]["Networks"].values():

            if not values["Aliases"]:
                continue

            result.append(
                {
                    "ip": values["IPAddress"],
                    "name": container_name,
                    "domains": set(
                        values["Aliases"] + [container_name, container_hostname]
                    ),
                }
            )

        if container_ip:
            result.append(
                {
                    "ip": container_ip,
                    "name": container_name,
                    "domains": [container_name, container_hostname],
                }
            )

        return result

    def update(self) -> List[Dict]:
        self.__info = self.__fetch_new_info()
        return self.__info


class HosterContainerCollection(UserDict):
    def __init__(self, dict={}, docker_client: docker.DockerClient = None):
        self.data: Dict[str, HosterContainer] = {}
        if dict:
            self.update(dict)
        self.__docker_client = docker_client

    def __getitem__(self, key: str) -> HosterContainer:
        if not isinstance(key, str):
            raise ValueError
        return self.data[key]

    def __delitem__(self, key: str):
        del self.data[key]

    def __setitem__(self, key: str, value: HosterContainer):
        if (
            not isinstance(value, HosterContainer)
            or not isinstance(key, str)
            or key != value.id
        ):
            raise ValueError
        self.data[key] = value

    def __iter__(self):
        return iter(self.data)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return f"{type(self).__name__}({self.data})"

    def add(
        self,
        container: Union[str, pathlib.Path, Container],
        docker_client: docker.DockerClient = None,
        force_update=True,
    ) -> HosterContainer:
        if not isinstance(container, Container):
            if not docker_client:
                expect(
                    self.__docker_client,
                    message="No docker client specified...",
                ).isinstance(docker.APIClient)
                docker_client = self.__docker_client

        hoster_container = HosterContainer(
            container=container,
            docker_client=docker_client,
            update=force_update,
        )
        self[hoster_container.id] = hoster_container
        return hoster_container

    def update_all(self):
        for container_id in self:
            self[container_id].update()


class Hoster:
    CONTAINER_STATUS_UP = ("start",)
    CONTAINER_STATUS_DOWN = ("stop", "die", "destroy")
    CONTAINER_STATUS = CONTAINER_STATUS_UP + CONTAINER_STATUS_DOWN

    def __init__(
        self,
        docker_client: docker.DockerClient,
        namespace: str = "docker-hoster",
        hosts: Union[str, python_hosts.Hosts] = None,
        filters: dict = None,
    ) -> None:
        signal.signal(signal.SIGINT, self.__exit_handler)
        signal.signal(signal.SIGTERM, self.__exit_handler)

        self.__docker_client = docker_client
        self.__containers = HosterContainerCollection(
            docker_client=self.__docker_client
        )
        self.__namespace = namespace

        if isinstance(hosts, python_hosts.Hosts):
            self.__hosts = hosts
        elif isinstance(hosts, (str, pathlib.Path)):
            self.__hosts = python_hosts.Hosts(path=str(hosts))
        else:
            logger.warning("no hosts(/path) set...")
            raise NotImplementedError
        self.__hosts_path = pathlib.Path(self.__hosts.hosts_path)
        self.__filters = filters

    @property
    def hosts(self) -> python_hosts.Hosts:
        return self.__hosts

    @property
    def hosts_path(self):
        return self.__hosts_path

    @property
    def containers(self) -> ContainerCollection:
        return self.__containers

    def start_events_daemon(self) -> None:
        """
        listen for events to keep the hosts file updated
        """
        # batch
        self.batch_update_hosts_file()

        # incremental
        events = self.__docker_client.events(decode=True, filters=self.__filters)
        for event in events:
            if event["Type"] != "container":
                continue

            status = event["status"]
            if status in self.CONTAINER_STATUS:
                container_id: str = event["id"]
                try:
                    if status in self.CONTAINER_STATUS_UP:
                        self.__containers.add(
                            container_id=container_id,
                            docker_client=self.__docker_client,
                            force_update=True,
                        )
                    elif status in self.CONTAINER_STATUS_DOWN:
                        if container_id in self.__containers:
                            self.__containers.pop(container_id)
                    else:
                        raise RuntimeError(f"Unknown status {status!r}...")
                except Exception as e:
                    logger.warning(repr(e))
                finally:
                    self.update_hosts_file()
        events.close()

    def __exit_handler(self, signal, frame):
        """
        exit handler: register the exit signals
        """
        # TODO: better "destroyer" method
        self.update_hosts_file(to_original=True)
        sys.exit(0)

    def add_all_containers(self, filters: Dict = None) -> HosterContainerCollection:
        for container in self.__docker_client.containers.list(
            all=False,
            filters=filters,
        ):
            self.__containers.add(
                container=container.id,
                docker_client=self.__docker_client,
            )
        return self.__containers

    def as_python_hosts_entries(self):
        """
        hoster_containers -> hosts_entries
        """
        result = []
        for id, hoster_container in self.__containers.items():
            for info in hoster_container.info:
                new_entry = python_hosts.HostsEntry(
                    entry_type=info.get("ip_version", "ipv4"),
                    address=info["ip"],
                    names=info["domains"],
                    comment=info.get("namespace", self.__namespace),
                )
                result.append(new_entry)
        return result

    def update_all_containers(self):
        self.__containers.update_all()

    def update_hosts_entries(self) -> python_hosts.Hosts:
        """in memory: entries list"""
        self.__hosts.entries = []
        self.__hosts.populate_entries()
        return self.__hosts

    def batch_update_hosts_file(self):
        self.add_all_containers(filters=self.__filters)
        self.update_all_containers()
        self.update_hosts_file()

    def update_hosts_file(self, to_original=False) -> Iterator[str]:
        """in storage: hosts files"""
        # current
        self.update_hosts_entries()
        before = pprint.pformat(self.__hosts)
        logger.debug(before)

        # back to original
        self.__hosts.entries = [
            entry for entry in self.__hosts.entries if entry.comment != self.__namespace
        ]
        # to modified
        if not to_original:
            self.__hosts.add(entries=self.as_python_hosts_entries())

        after = pprint.pformat(self.__hosts)
        logger.debug(after)

        # with tempfile.TemporaryFile() as tmp:
        #     tmp_path = pathlib.Path(tmp.name).resolve()
        #     expect(tmp_path.is_file() and tmp_path.is_absolute()).equals(True)
        #     result = self.__hosts.write()
        #     shutil.copy(tmp_path)
        result = self.__hosts.write()
        logger.info(result)

        diff = difflib.unified_diff(
            a=before.splitlines(),
            b=after.splitlines(),
        )
        logger.debug("\n".join(diff))
        return diff
