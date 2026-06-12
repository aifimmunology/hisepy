'''
useful utility methods for HISE IDE users 
'''

import os
import time
import json
import requests
import shutil
import subprocess
import psutil
import uuid
import tempfile
from resource import RLIMIT_AS, getrlimit, setrlimit
from pathlib import Path
import hisepy.common_utils as cu
import hisepy.hise_requests as hreq
from hisepy.instances import IDEInstance
from hisepy.auth import ide_instance_guid, get_bearer_token_header
from hisepy.logging import with_default_logging, logger

# directory of hisepy package
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))

SDK_POLL_INTERVAL = 5  # seconds
SDK_POLL_TIMEOUT = 180  # seconds (3 minutes)


def build_and_install_sdk(sdk_dir: Path) -> None:
    """Build and install the SDK package from the given directory."""
    if not sdk_dir.exists():
        raise FileNotFoundError(f"SDK directory not found: {sdk_dir}")

    cmds = [["python", "setup.py", "build"], ["pip", "install", "."]]

    for cmd in cmds:
        subprocess.run(cmd,
                       cwd=sdk_dir,
                       check=True,
                       text=True,
                       capture_output=True)


@with_default_logging
def conda_env_builds(path_to_conda_env: str | None = None) -> bool:
    """
    Validates and builds a conda environment, returning True if successful.

    Parameters:
        path_to_conda_env (str, optional): Path to the conda environment to test.
    """
    logger.info("Starting conda environment build validation...")

    # resolve or validate environment path
    if path_to_conda_env:
        if not isinstance(path_to_conda_env, str):
            raise TypeError("Path to conda env must be a string.")
        env_path = Path(path_to_conda_env)
        if not env_path.exists():
            raise ValueError(f"Path does not exist: {path_to_conda_env}")
    else:
        modality_name = IDEInstance().environment['condaEnvName']
        env_path = Path(CONFIG['STORES']['ENV_STORE']) / modality_name

    temp_dir = tempfile.TemporaryDirectory(prefix="conda_env_test_")
    tmp_path = Path(temp_dir.name)

    conda_export_path = tmp_path / f"environment.yml"
    tmp_env_path = tmp_path / f"env_{cu.uuid_string()}"
    packed_env_path = tmp_path / f"packed_{cu.uuid_string()}.tar.gz"

    try:
        # export the environment
        logger.info(f"Exporting conda environment from {env_path}...")
        subprocess.run(
            [
                "conda", "env", "export", "-p",
                str(env_path), "-f",
                str(conda_export_path)
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        # remove hisepy dependency (if present)
        logger.info(
            "Removing hisepy references from exported environment file...")
        subprocess.run(
            ["sed", "-i", "/hisepy==*/d",
             str(conda_export_path)],
            check=True,
            text=True,
            capture_output=True,
        )

        # create temp conda environment
        logger.info(
            f"Creating temporary conda environment at {tmp_env_path}...")
        subprocess.run(
            [
                "conda", "env", "create", "-f",
                str(conda_export_path), "-p",
                str(tmp_env_path)
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        # verify conda-pack exists
        conda_pack_bin = env_path / "bin" / "conda-pack"
        if not conda_pack_bin.exists():
            raise FileNotFoundError(f"conda-pack not found in {env_path}. "
                                    "Please install it before proceeding.")

        # run conda-pack
        logger.info(f"Packing conda environment to {packed_env_path}...")
        subprocess.run(
            [
                "conda", "run", "-p",
                str(env_path), "conda-pack", "-p",
                str(tmp_env_path), "-o",
                str(packed_env_path)
            ],
            check=True,
            text=True,
            capture_output=True,
        )

        logger.info("Conda environment built and packed successfully.")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(
            f"Subprocess failed: {e.cmd}\nstdout: {e.stdout}\nstderr: {e.stderr}"
        )
        return False
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return False
    finally:
        # Automatic cleanup by TemporaryDirectory
        temp_dir.cleanup()


@with_default_logging
def get_memory_usage() -> float:
    """Gets current memory usage (in MB)."""
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        return mem_info.rss / (1024**3)  # in GB
    except Exception as e:
        raise Exception(f"failed to get memory usage: {e}")


@with_default_logging
def set_memory_limit(max_size_gb: int) -> None:
    ''' 
    Caps memory for a kernel/process. Call this method at the top of your notebook or script.
    If the current kernel reaches the limit, an error message will be raised, preventing OOM scenarios.
    
    Parameters: 
        max_size (int) : memory limit (in GB) for a kernel/process.
    '''
    if max_size_gb <= 0:
        raise ValueError("Memory limit must be greater than 0")
    if not isinstance(max_size_gb, int):
        raise TypeError("Memory limit must be an integer")

    try:
        maxsize = max_size_gb * (1024**3)  # in GB
        soft, hard = getrlimit(RLIMIT_AS)
        setrlimit(RLIMIT_AS, (maxsize, hard))
        print(f"Memory limit set to {max_size_gb} GB")
        return
    except Exception as e:
        raise Exception(f"failed to set memory limit: {e}")
    return


@with_default_logging
def update_sdk_version():
    """
    This will download the latest version of the SDK to /home/workspace/sdk, and if successful, 
    will update that version into the current activated conda environment. A restart of the kernel or terminal 
    is required for the changes to take effect.
    """
    try:

        # check that there's enough disk space in /home/workspace/sdk
        total_disk = shutil.disk_usage(CONFIG['STORES']['SDK_STORE']).total 
        usage_disk = shutil.disk_usage(CONFIG['STORES']['SDK_STORE']).used
        if usage_disk / total_disk > 0.95:  # if more than 90% of disk is used
            raise RuntimeError(
                "Not enough disk space to download SDK. Please free up space in /home/workspace/sdk and try again."
            )

        # Fetch latest version tag
        version_url = cu.hise_url("ide_management", "sdk_version", "python")
        version_tag = hreq.hise_get(version_url)
        if not version_tag:
            raise RuntimeError("No SDK version returned from server.")
        logger.info(f"Latest SDK version found: {version_tag}")

        # Request SDK installation from remote service
        install_url = cu.hise_url("ide_management", "install_sdk",
                                  ide_instance_guid())
        payload = {"hisePyTag": version_tag}
        logger.info(
            f"Requesting SDK installation for version {version_tag}...")
        hreq.hise_post(install_url, data=json.dumps(payload))

        # Wait for SDK to appear locally
        sdk_dir = Path(CONFIG['STORES']['SDK_STORE']) / f"hisepy_{version_tag}"
        logger.info(
            f"Waiting for SDK directory {sdk_dir} to become available...")
        wait_for_sdk(sdk_dir, timeout=SDK_POLL_TIMEOUT)

        # Build and install the SDK
        logger.info(
            f"Installing SDK version {version_tag} into active environment...")
        build_and_install_sdk(sdk_dir)

        logger.info(f"✅ SDK version {version_tag} installed successfully.")
        return version_tag

    except subprocess.CalledProcessError as e:
        logger.error(
            f"Command failed: {' '.join(e.cmd)}\nstdout:\n{e.stdout}\nstderr:\n{e.stderr}"
        )
        raise RuntimeError(
            f"SDK installation failed for version {version_tag}") from e
    except TimeoutError as e:
        logger.error(str(e))
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during SDK update: {e}")
        raise


def wait_for_sdk(sdk_dir: Path, timeout: int = SDK_POLL_TIMEOUT) -> None:
    """Wait until the SDK directory appears or raise TimeoutError."""
    start = time.time()
    while not sdk_dir.exists():
        if time.time() - start > timeout:
            raise TimeoutError(
                f"SDK directory did not appear within {timeout} seconds: {sdk_dir}"
            )
        logger.info(f"Waiting for SDK at {sdk_dir}...")
        time.sleep(SDK_POLL_INTERVAL)
