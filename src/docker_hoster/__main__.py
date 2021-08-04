import argparse
import sys

import docker
import python_hosts
import docker_hoster
from loguru import logger

# try:
#     from .. import docker_hoster
# except ImportError:
#     import pathlib
#     import importlib

#     importlib.import_module()

#     docker_hoster = __import__(str((pathlib.Path(__file__).parent).resolve()))


HOSTS_PATH: str = "/tmp/hosts"
DOCKER_SOCK: str = "/tmp/docker.sock"
NAMESPACE: str = "docker-hoster"
SAME_NETWORK: bool = True

logger.debug(f"{__file__}: {__package__} is running!")


def get_parser():
    parser = argparse.ArgumentParser(
        description="Synchronize running docker container IPs with host /etc/hosts file."
    )
    parser.add_argument(
        "--socket",
        type=str,
        nargs="?",
        default=DOCKER_SOCK,
        help="The docker socket to listen for docker events.",
    )
    parser.add_argument(
        "--file",
        type=str,
        nargs="?",
        default=HOSTS_PATH,
        help="The /etc/hosts file to sync the containers with.",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        nargs="?",
        default=NAMESPACE,
        help="The inline comment after all entries added.",
    )
    parser.add_argument(
        "--same-network",
        type=bool,
        nargs="?",
        default=SAME_NETWORK,
        help="Added containers have to be in the same docker network as this container.",
    )
    return parser


@logger.catch
def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = get_parser()
    args = parser.parse_args(argv)
    HOSTS_PATH = args.file
    DOCKER_SOCK = args.socket
    SAME_NETWORK = args.same_network

    docker_client = docker.APIClient(base_url=f"unix://{DOCKER_SOCK}")
    hoster = docker_hoster.Hoster(
        docker_client=docker_client,
        namespace=NAMESPACE,
        hosts=HOSTS_PATH,
        # filters={"network": ""},
    )

    try:
        hoster.start_events_daemon()
    except Exception as e:
        logger.error(e)


if __name__ == "__main__":
    main()
