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