import requests
import os
import sys
import subprocess
import shutil
from pathlib import Path
import hisepy.common_utils as cu
import hisepy.hise_requests as hreq
from hisepy.utils import conda_env_builds
from hisepy.auth import ide_instance_guid, IDEInstance, HiseUser
from hisepy.logging import with_default_logging, logger
from hisepy.conda_pack import validate_save_custom_env_params

valid_languages = ['python', 'r']
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))

import sys
import subprocess
import tempfile
from pathlib import Path
import logging
import requests
from typing import List, Optional
import tomllib
import tomli_w

logger = logging.getLogger(__name__)


def build_github_repo(url : str, version_tag : str) -> Path: 
    """ 
        Clones a github repo and attempts to build and create a .whl file. 
        If successful, it will copy it over to the IDE's Pixi environment

        Parameters:
            url (str): Github url of package
            version_tag (str): tag or branch of Github repo 

        Returns: 
            Filepath of copied wheel file 
    """
    wheel_dir = get_pixi_env_dir() / "python-packages"
    # clone repo to scratch, checkout tag, build it, and copy it over
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "repo"

        subprocess.run(
            ["git", "clone", url, str(repo_dir)],
            check=True,
        )

        subprocess.run(
            ["git", "checkout", version_tag],
            cwd=repo_dir,
            check=True,
        )

        # build a whl, copy whl to pixi env dir 
        # error out if whl can't be generated 
        subprocess.run(
            ["python", "-m", "pip", "install", "--quiet", "build"],
            check=True,
        )

        subprocess.run(
            ["python", "-m", "build", "--wheel"],
            cwd=repo_dir,
            check=True,
        )

        dist_dir = repo_dir / "dist"
        wheels = list(dist_dir.glob("*.whl"))

        if not wheels:
            raise RuntimeError("Wheel build succeeded but no .whl found")

        # take the first wheel
        wheel_path = wheels[0]
        dest_wheel = wheel_dir / wheel_path.name
        shutil.copy2(wheel_path, dest_wheel)
    return dest_wheel

def get_pixi_env_dir():
    return Path(os.path.dirname(os.getenv("PIXI_PROJECT_MANIFEST")))

@with_default_logging
def install_github_package_to_pixi_env(url : str, version_tag : str): 
    """
    Install a package from github to an existing pixi environment

    Parameters: 
        url (str): Github url of package
        version_tag (str): tag or branch of Github repo
    Returns: 
        True if installation was successful. Error otherwise
    Example: 
        install_github_package_to_pixi_env(url = "https://github.com/aifimmunology/hisepy", version_tag = 'v1.0.0')
    """

    # make wheel directory
    wheel_dir = get_pixi_env_dir() / "python-packages"
    wheel_dir.mkdir(exist_ok=True)

    try:
        # validate params 
        validate_install_github_package_params(url, version_tag)

        # create unique task name based on repo name
        print("building github repo...") 
        # clone repo to scratch, checkout tag, build it, and copy it over
        built_wheel = build_github_repo(url, version_tag)

        # add pixi task to build from the whl
        # update if the task already exists
        update_install_wheel_task(built_wheel)

    except Exception as e:
        raise SystemError(
            f"Failed to build github package: {e}"
        ) 
        
     # now install the packages using the pixi task command  
    try: 
        print("installing github package to environment...")
        install_wheels_to_env(built_wheel)
    except Exception as e: 
        raise SystemError(
            f"Failed to install github package {url}: {e}"
        )
    return True


def install_wheels_to_env(wheel_file): 

    subprocess.run(
        ["pip", "install", wheel_file],
        check=True,
    )
    return True 

@with_default_logging
def save_custom_pixi_environment(env_name : str, description : str, 
                                 languages : list[str]): 
    """
    Save a custom Pixi environment with additional metadata. 

    Parameters: 
        env_name (str): Name of the Pixi environment. This is the name that will show in the HISE UI.
        description (str): Description of the environment. 
        languages (list[str]): List of programming languages support by the environment.
    Returns: 
        dict: Response from the HISE API after saving the environment
    """

    # validate parameters 
    validate_save_custom_env_params(env_name, description, languages)

    # grab env path from PIXI_PROJECT_MANIFEST env var
    pixi_env_dir = Path(os.path.dirname(os.getenv("PIXI_PROJECT_MANIFEST")))
    if not pixi_env_dir:
        raise RuntimeError(
            "Pixi environment not detected. Please activate a Pixi environment before saving."
        )

    wheel_dir = pixi_env_dir / "python-packages"
    # prompt user 
    if not cu.prompt_user(CONFIG["PROMPTS"]["SAVE_CUSTOM_ENV"].format("pixi"),
                            pixi_env_dir):
        raise RuntimeError(
            "User cancelled saving the custom Pixi environment"
        )
    path_to_env = pixi_env_dir
    logger.info(f"saving activate Pixi environment at {path_to_env}")

    # grep all files in /wheels 
    wheel_files = list(wheel_dir.glob("*.whl"))

    # export manifest file to temporary directory
    with tempfile.TemporaryDirectory(prefix="env_export_") as tmpdir: 
        tmpdir_path = Path(tmpdir)
        toml_path = tmpdir_path / "pixi.toml"

        # copy wheel files to temp dir
        additional_packages = []
        for wheel in wheel_files:
            shutil.copy2(wheel, tmpdir_path / wheel.name)
            additional_packages.append(tmpdir_path / wheel.name)

        # export pixi manifest
        cu.copy_files(f"{path_to_env}/pixi.toml", toml_path)

        # prep request
        params = {
            "name": env_name,
            "description": description,
            "language": languages,
            "ownerEmail": HiseUser().email,
            "packageManager": "pixi",
            "additionalPackages": [Path(p).name for p in wheel_files],
        }

        files = []
        with open(toml_path, "rb") as f:
            files.append(("file", (toml_path.name, f, "application/octet-stream")))

            # additional packages (list of paths)
            for pkg_path in additional_packages:  # list of Path objects or strings
                pkg_path = Path(pkg_path)
                f = open(pkg_path, "rb")
                files.append(
                    ("additionalPackages", (pkg_path.name, f, "application/octet-stream"))
                )

            url = cu.hise_url("ide_management", "save_custom_conda_env")
            return hreq.hise_post(url, data=params, files=files)


def update_install_wheel_task(dest_wheel):
    pixi_toml = get_pixi_env_dir() / "pixi.toml"
    data = tomllib.loads(pixi_toml.read_text())

    tasks = data.setdefault("tasks", {})

    install_cmd = tasks.get("install-wheel", "")

    existing_wheels = set()
    if install_cmd.startswith("pip install"):
        existing_wheels = set(install_cmd.split()[2:])

    new_wheel_ref = f"{dest_wheel.name}"

    if new_wheel_ref not in existing_wheels:
        existing_wheels.add(new_wheel_ref)

    tasks["install-github-python-pkg"] = "pip install " + " ".join(sorted(existing_wheels))

    pixi_toml.write_text(tomli_w.dumps(data))
    return True

def validate_install_github_package_params(url : str, version_tag : str): 
    pixi_toml = Path(os.getenv("PIXI_PROJECT_MANIFEST"))
    if not url.startswith("https://github.com/"):
        raise ValueError("url must be a GitHub https URL")

    if not version_tag:
        raise ValueError("version_tag must be provided")

    if not pixi_toml.exists():
        raise FileNotFoundError(f"pixi.toml not found at {pixi_toml}")
    return True