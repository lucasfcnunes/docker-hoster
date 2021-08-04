import pathlib
import pytest  # noqa
from pyexpect import expect

from docker_hoster import Hoster, HosterContainer, HosterContainerCollection
import docker

# from .conftest import dockerd, docker_client
# from . import conftest

try:
    from loguru import logger
except Exception:
    import logging

    logger = logging.getLogger(__name__)


class TestHosterContainer:
    @classmethod
    def setup_class(cls):
        "Runs once per class"

    @classmethod
    def teardown_class(cls):
        "Runs at end of class"

    def test_create(
        self,
        dind_docker_client: docker.DockerClient,
        create_dummy_containers,
    ):
        """create"""
        containers = create_dummy_containers(3)

        logger.info(dind_docker_client.containers)
        not_a_id = ["not a container"]
        for id in [*not_a_id, *[container.id for container in containers]]:
            try:
                hoster_container = HosterContainer(
                    container=id,
                    docker_client=dind_docker_client,
                    update=False,
                )
            except Exception as e:
                if id in not_a_id:
                    expect(repr(e)).matches("NotFound")
                    continue
                else:
                    raise
            else:
                if id in not_a_id:
                    raise

            expect(hoster_container).has_attr(*["id", "info"])
            expect(hoster_container.id).equal(id)
            expect(hoster_container.info).empty()

            hoster_container.update()
            expect(hoster_container.info).not_length(0)
            for info in hoster_container.info:
                expect(info).to_contain(*["ip", "name", "domains"])


class TestHoster:
    # @pytest.mark.notwritten
    def test_create(
        self,
        dind_docker_client: docker.DockerClient,
        create_dummy_containers,
        tmp_root_path: pathlib.Path,
    ):
        hoster = Hoster(
            docker_client=dind_docker_client,
            namespace="test",
            hosts=tmp_root_path / "tmp/hosts",
        )
        original = hoster.update_hosts_file()
        containers = create_dummy_containers(3)
        hoster.add_all_containers()
        modified = hoster.update_hosts_file()
        allegedly_original = hoster.update_hosts_file(to_original=True)
        # expect(original).equals(allegedly_original)
        # expect(original).not_equals(modified)
        # expect(modified).to_have_sub_list(original)


class TestHosterContainerCollection:
    @pytest.mark.notwritten
    def test_create(self):
        pass  # HosterContainerCollection()
