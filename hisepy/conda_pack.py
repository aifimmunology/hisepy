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

PIXI_ENV_DIR = Path(f"{CONFIG['STORES']['ENV_STORE']}/{cu.get_environment_name()}")
PIXI_TOML = PIXI_ENV_DIR / "pixi.toml"
WHEEL_DIR = PIXI_ENV_DIR / "wheels"


def extract_repo_name(url: str) -> str:
    """
    Extract the repository name from a GitHub URL.

    Parameters:
        url (str): GitHub repository URL

    Returns:
        str: Repository name
    """
    repo_name = url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    return repo_name


@with_default_logging
def install_github_package_to_pixi_env(url : str, version_tag : str, overwrite : bool = False): 
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

    try:
        # validate params 
        validate_install_github_package_params(url, version_tag)

        # create unique task name based on repo name
        pkg_name = extract_repo_name(url)  
        task_name = f"install-github-{pkg_name}"

        print("updating manifest to build github package...") 
        # create task to install from github
        update_or_create_pixi_task(task_name, url, version_tag, overwrite)

        print("builing and installing github package...")
        # install immediately for the user
        subprocess.run(
            ["pixi", "run", task_name],
            check=True,
        )
    except Exception as e:
        raise SystemError(
            f"Failed to build github package: {e}"
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

    # prompt user 
    if not cu.prompt_user(CONFIG["PROMPTS"]["SAVE_CUSTOM_ENV"].format("pixi"),
                            PIXI_ENV_DIR):
        raise RuntimeError(
            "User cancelled saving the custom Pixi environment"
        )
    path_to_env = PIXI_ENV_DIR
    logger.info(f"saving activate Pixi environment at {path_to_env}")

    # verify packing is successful 
    # TODO 

    # export manifest file to temporary directory
    with tempfile.TemporaryDirectory(prefix="env_export_") as tmpdir: 
        tmpdir_path = Path(tmpdir)
        toml_path = tmpdir_path / "pixi.toml"

        # TODO: do I need to remove SDKs? 

        # export pixi manifest
        cu.copy_files(f"{path_to_env}/pixi.toml", toml_path)

        # prep request
        params = {
            "name": env_name,
            "description": description,
            "language": languages,
            "ownerEmail": HiseUser().email,
            "packageManager": "pixi"
        }

        with open(toml_path, "rb") as f:
            files = {"file": (toml_path.name, f, "application/octet-stream")}
            url = cu.hise_url("ide_management", "save_custom_conda_env")
            return hreq.hise_post(url, data=params, files=files)




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
        save_custom_conda_environment(
                env_name="my_custom_env",
                description="A custom conda environment for data science.",
                languages=["python", "r"],
            )
    """

    # validate parameters
    validate_save_custom_env_params(env_name, description, languages)

    # prompt user
    if not cu.prompt_user(CONFIG["PROMPTS"]["SAVE_CUSTOM_ENV"].format("conda"),
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
            "packageManager": "conda"
        }

        with open(yaml_path, "rb") as f:
            files = {"file": (yaml_path.name, f, "application/octet-stream")}
            url = cu.hise_url("ide_management", "save_custom_conda_env")
            resp = hreq.hise_post(url, data=params, files=files)

            # attach workflow to log entry 
            logger.extra["_override"]['workflow'] = resp['WorkflowId']
            return resp


def update_or_create_pixi_task(
    task_name: str,
    url: str,
    version_tag: str,
    overwrite : bool = False,
) -> None:
    """
    Create or update a Pixi task that installs a GitHub package by
    cloning, building, and installing a wheel.

    Parameters:
        task_name (str): Name of the Pixi task (e.g. install-github-hisepy)
        url (str): GitHub repository URL
        version_tag (str): Git tag or branch
    """

    if not PIXI_TOML.exists():
        raise FileNotFoundError("pixi.toml not found")

    result = subprocess.run(
        ["pixi", "task", "list"],
        capture_output=True,
        text=True,
        check=True
    )
    if task_name in result.stderr and not overwrite:
        raise RuntimeError(
            f"Pixi task '{task_name}' already exists. "
            "Pass overwrite=True to overwrite."
        )

    # Build a single-line shell command safely
    cmd = (
        f'REPO_URL="{url}" && '
        f'VERSION_TAG="{version_tag}" && '
        f'ENV="{PIXI_ENV_DIR}" && '
        'cd "$ENV" && '
        'rm -rf repo && '
        'git clone "$REPO_URL" repo && '
        'cd repo && '
        'git checkout "$VERSION_TAG" && '
        'python -m pip install --quiet build'
    )

    # delete so we can add it back 
    subprocess.run(
        ["pixi", "task", "remove", task_name],
        check=False  # ok if it doesn't exist
    )

    # Use subprocess to call Pixi CLI and add/update task
    result = subprocess.run(
        ["pixi", "task", "add", task_name, cmd],
        check=True
    )
    if result.returncode != 0:
        raise SystemError(
            f"Failed to add Pixi task: {result.stderr}")  

    print(f"Pixi task '{task_name}' updated/added successfully.")
    return True


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


def validate_save_custom_env_params(env_name: str, description: str,
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