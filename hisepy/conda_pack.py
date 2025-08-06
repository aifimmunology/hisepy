import requests
import os 
import sys 
import subprocess
import hisepy.common_utils as cu 
from hisepy.utils import conda_env_builds
from hisepy.auth import ide_instance_guid, IDEInstance, HiseUser

valid_languages = ['python', 'r']
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))

def validate_conda_env_params(
    env_name : str,
    description: str,
    languages: list[str]
):
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
    if not isinstance(languages, list) or not all(isinstance(lang, str) for lang in languages):
        raise ValueError("languages must be a list of strings.")
    
    # verify languages are only python/R 
    valid_languages = ['Python', 'R']
    if not all(lang.capitalize() in valid_languages for lang in languages):
        raise ValueError(f"languages must be one of {valid_languages}.")

    return 

def save_custom_conda_environment(
    env_name : str,
    description: str,
    languages: list[str]
):
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

    # Validate parameters
    validate_conda_env_params(env_name, description, languages)

    # prompt user that active environment will be saved
    if cu.prompt_user(CONFIG["PROMPTS"]["SAVE_CUSTOM_CONDA_ENV"].format(c=sys.prefix)):

        # get path to current active conda environment 
        path_to_conda_env = sys.prefix

        # validate the environment can build 
        if conda_env_builds(path_to_conda_env) is not True:
            raise RuntimeError("Conda environment cannot be built successfully. Please check the YAML file and dependencies.")
        
        # export conda env to temp directory
        yaml_path = os.path.join(CONFIG['STORES']['TEMP_STORE'], 'environment.yml') 
        process = subprocess.run("conda env export -p {src} > {dst}".format(src=path_to_conda_env, dst=yaml_path),
                                    shell=True, capture_output=True)
        if process.returncode != 0:
            raise SystemError('Unable to export conda env: {}'.format(path_to_conda_env))
        
        # remove hisepy from exported yaml file, if it exists 
        process = subprocess.run("sed -i '/hisepy==*/d' {}".format(yaml_path),
                                    shell=True, capture_output=True)
        if process.returncode != 0:
            raise SystemError('Unable to remove hisepy from exported conda env: {}'.format(conda_export_dest))

        params = {
            "name": env_name,
            "description": description,
            "language": languages,
            "ownerEmail" : HiseUser().email,
        }
        with open(yaml_path, 'rb') as f:
            files = {
                'file': (os.path.basename(yaml_path), f, 'application/octet-stream')
            }
            url = cu.hise_url("ide_management", "save_custom_conda_env")
            resp = cu.parse_hise_response(
                requests.post(url, headers=cu.get_bearer_token_header(), data=params, files=files))

        return resp
    else:
        raise RuntimeError("User cancelled saving the custom conda environment.")

