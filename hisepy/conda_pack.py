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

PIXI_ENV_DIR = Path(f"{CONFIG['STORES']['ENV_STORE']}/{cu.get_environment_name()")
PIXI_TOML = PIXI_ENV_DIR / "pixi.toml"
WHEEL_DIR = PIXI_ENV_DIR / "wheels"


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
        dest_wheel = WHEEL_DIR / wheel_path.name
        shutil.copy2(wheel_path, dest_wheel)
    return dest_wheel


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
    WHEEL_DIR.mkdir(exist_ok=True)
    
    try:
        # validate params 
        validate_install_github_package_params(url, version_tag)

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
def save_custom_conda_environment(env_name: str, description: str,
                                  languages: list[str]):
    """
    Save a custom conda environment with additional metadata.

    Parameters:
        env_name (str): Name of the conda environment. This is the name that will show in the HISE UI.
        description (str): Description of the environment.
        languages (list[str]): List of programming languages supported by the environment.
    Returns: 
        dict: Response from the HISE API after saving the environment.
    Example: 
        >>> save_custom_conda_environment(
                env_name="my_custom_env",
                description="A custom conda environment for data science.",
                languages=["python", "r"],
            )
    """

    # validate parameters
    validate_conda_env_params(env_name, description, languages)

    # prompt user
    if not cu.prompt_user(CONFIG["PROMPTS"]["SAVE_CUSTOM_CONDA_ENV"],
                          sys.prefix):
        raise RuntimeError(
            "User cancelled saving the custom conda environment.")

    path_to_conda_env = Path(sys.prefix)
    logger.info(f"Saving active conda environment at {path_to_conda_env}")

    # validate environment can build
    if not conda_env_builds(str(path_to_conda_env)):
        raise RuntimeError(
            "Conda environment cannot be built successfully. Please check the YAML file and dependencies."
        )

    # export and process YAML in a temporary directory
    with tempfile.TemporaryDirectory(prefix="conda_env_export_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        yaml_path = tmpdir_path / "environment.yml"

        # export conda environment
        logger.info(f"Exporting conda environment to {yaml_path}")
        result = subprocess.run(
            ["conda", "env", "export", "-p",
             str(path_to_conda_env)],
            stdout=open(yaml_path, "w"),
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise SystemError(f"Unable to export conda env: {result.stderr}")

        # remove hisepy dependency from YAML
        logger.info("Removing hisepy from exported YAML file")
        result = subprocess.run(
            ["sed", "-i", "/hisepy==*/d",
             str(yaml_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise SystemError(
                f"Unable to remove hisepy from exported YAML: {result.stderr}")

        # prepare API request
        params = {
            "name": env_name,
            "description": description,
            "language": languages,
            "ownerEmail": HiseUser().email,
        }

        with open(yaml_path, "rb") as f:
            files = {"file": (yaml_path.name, f, "application/octet-stream")}
            url = cu.hise_url("ide_management", "save_custom_conda_env")
            resp = hreq.hise_post(url, data=params, files=files)

            # attach workflow to log entry 
            logger.extra["_override"]['workflow'] = resp['WorkflowId']
            return resp


def update_install_wheel_task(dest_wheel):
    data = tomllib.loads(PIXI_TOML.read_text())

    tasks = data.setdefault("tasks", {})

    install_cmd = tasks.get("install-wheel", "")

    existing_wheels = set()
    if install_cmd.startswith("pip install"):
        existing_wheels = set(install_cmd.split()[2:])

    new_wheel_ref = f"wheels/{dest_wheel.name}"

    if new_wheel_ref not in existing_wheels:
        existing_wheels.add(new_wheel_ref)

    tasks["install-wheel"] = "pip install " + " ".join(sorted(existing_wheels))

    PIXI_TOML.write_text(tomli_w.dumps(data))
    return True


def validate_conda_env_params(env_name: str, description: str,
                              languages: list[str]):
    """
    Validate parameters for saving a custom conda environment.

    Args:
        env_name (str): Name of the conda environment.
        description (str): Description of the environment.
        languages (list[str]): List of programming languages supported by the environment.

    Raises:
        ValueError: If any parameter is invalid.
    """
    if not isinstance(env_name, str) or not env_name:
        raise ValueError("env_name must be a non-empty string.")
    if not isinstance(description, str):
        raise ValueError("description must be a string.")
    if not isinstance(languages, list) or not all(
            isinstance(lang, str) for lang in languages):
        raise ValueError("languages must be a list of strings.")

    # verify languages are only python/R
    valid_languages = ['Python', 'R']
    if not all(lang.capitalize() in valid_languages for lang in languages):
        raise ValueError(f"languages must be one of {valid_languages}.")

    return


def validate_install_github_package_params(url : str, version_tag : str): 
    if not url.startswith("https://github.com/"):
        raise ValueError("url must be a GitHub https URL")

    if not version_tag:
        raise ValueError("version_tag must be provided")

    if not PIXI_TOML.exists():
        raise FileNotFoundError(f"pixi.toml not found at {PIXI_TOML}")
    return True