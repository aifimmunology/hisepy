import os
import pyreadr
import subprocess
from pathlib import Path
import yaml
import shutil
from hisepy.utils import conda_env_builds
from hisepy.auth import IDEInstance, ide_is_from_guest_account, debug
import hisepy.common_utils as cu
from hisepy.upload import get_study_spaces, get_default_project, DashAppImg, set_default_project, set_default_store

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))

no_study_default = "no study"
permanent_store = "permanent"
project_store = "project"
valid_upload_stores = [permanent_store, project_store]


def build_upload_payload(files, file_types, title, store, destination, project,
                         study_space_id, input_file_ids, input_sample_ids,
                         home_dir, inst):
    """Builds the structured payload for upload."""
    if file_types is None:
        file_types = []
    qargs = {
        "title": title,
        "fileType": [],
        "saveIDE": True,
        "store": store,
        "destination": destination,
        "instanceId": inst.podName,
        "instanceGuid": inst.id,
        "inputFileIds": input_file_ids,
        "project": project,
        "sampleIds": input_sample_ids,
        "notebook": cu.current_notebook(),
        "homedir": home_dir,
    }

    if study_space_id and study_space_id is not no_study_default:
        qargs["studySpaceId"] = study_space_id

    qargs.update(gen_upload_body(files, file_types))
    return qargs


def check_project_against_study_space(project, study_space_id):
    if project is None:
        return
    elif study_space_id is None or study_space_id is no_study_default:
        return

    pguid = cu.project_shortname_to_guid(project)
    ss = get_study_space(study_space_id)
    if "projectGuid" not in ss:
        raise ValueError("%s was not a valid study space" % study_space_id)

    if pguid != ss["projectGuid"]:
        raise ValueError(
            "The specified study space %s is not in the project %s" %
            (ss["name"], project))


def check_default_store(store: str):
    if store not in valid_upload_stores:
        raise ValueError("%s is not a valid store" % store)
    if store != get_default_store() and cu.prompt_yn(
            "Set %s as your default store?" % store):
        set_default_store(store)


def check_default_project(proj: str):
    if proj != get_default_project() and cu.prompt_yn(
            "Set %s as your default project?" % proj):
        set_default_project(proj)


def create_temp_directory_files(paths: list[str], tmpdir: str) -> None:
    """Copy all files/directories into a temporary directory, preserving relative paths."""
    for src in paths:
        rel_path = os.path.relpath(src, "/")
        dst = os.path.join(tmpdir, os.path.dirname(rel_path))
        os.makedirs(dst, exist_ok=True)

        if os.path.isfile(src):
            shutil.copy(src, dst)
        elif os.path.isdir(src):
            shutil.copytree(src,
                            os.path.join(tmpdir, rel_path),
                            dirs_exist_ok=True)


def do_conda_export(to_directory: str = ""):
    """
    Exports the current conda environment to a file
    """
    if to_directory == "":
        to_directory = "{}".format(CONFIG["STORES"]["TEMP_STORE"])

    if not os.path.isdir(to_directory) and not debug():
        raise ValueError("directory {dir} is not a valid directory".format(
            dir=to_directory))

    conda_export_dest = os.path.join(to_directory, "environment.yml")

    # export to scratch and move to to staging store
    env_dir = "{}/{}".format(CONFIG["STORES"]["ENV_STORE"],
                             get_ide_env_name())
    result = subprocess.run(
        ["conda", "env", "export", "-p",
         str(env_dir)],
        stdout=open(conda_export_dest, "w"),
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise SystemError(f"Unable to export conda env: {result.stderr}")

    # check that the environment file isn't empty
    if not has_packages_in_env_file(conda_export_dest):
        raise ValueError(
            "Environment file is empty, please ensure that the conda environment is active and not empty."
        )

    return conda_export_dest


def do_pixi_export(to_directory): 
    """
    Exports the current Pixi environment to a file
    """
    if to_directory == "":
        to_directory = "{}".format(CONFIG["STORES"]["TEMP_STORE"])

    if not os.path.isdir(to_directory) and not debug():
        raise ValueError("directory {dir} is not a valid directory".format(
            dir=to_directory))
        
    # pack environment; copy manifests over to scratch
    env_dir = "{}/{}".format(CONFIG['STORES']['ENV_STORE'],
            get_ide_env_name())
    if not os.path.isdir(env_dir) and not debug(): 
        raise ValueError("directory {dir} is not a valid directory".format(dir=env_dir))
    pixi_export_dest = os.path.join(to_directory, "pixi.toml")
    pixi_manifest_src = os.path.join(env_dir, 'pixi.toml')

    shutil.copy(pixi_manifest_src, pixi_export_dest)
    return pixi_export_dest


def ensure_conda_env_ready(do_check: bool):
    if not do_check or debug():
        return
    if not conda_env_builds():
        raise RuntimeError(CONFIG['PROMPTS']['CONDA_ENV_BUILD'])


def gen_upload_body(files, filetypes=[]):
    body = {"files": []}
    for i, f in enumerate(files):
        if not os.path.exists(f):
            raise ValueError("%s is not a valid file." % f)
        ft = filetypes[i] if len(filetypes) > i else cu.get_filetype(f)
        body["files"].append({"name": os.path.abspath(f), "type": ft})
    return body


def get_ide_env_name():
    """
    Returns the name of the current conda environment
    """
    # get IDE instance
    inst = IDEInstance()

    # get the name of the current conda environment
    return inst.environment['condaEnvName']


def get_size_in_megabytes(file_list, convert_to_megabytes=True):
    total_size = 0
    for file in file_list:
        if os.path.isfile(file):
            total_size += os.path.getsize(file)
    if not convert_to_megabytes:
        return total_size
    else:
        return total_size / (1024 * 1024)  # convert bytes to megabytes


def get_study_space(id: str):
    """ Returns the given study space, assuming the user has access """
    return cu.parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "study_space_path", id),
                         headers=get_bearer_token_header()))


def get_upload_url():
    """Returns the correct upload URL depending on guest or non-guest account."""
    base_url = cu.hise_url("ide_management", "upload_file_v3_path")
    if ide_is_from_guest_account():
        return guest_hise_server(base_url)
    return base_url


def get_workspace_dirs():
    """Determines appropriate working directories based on IDE type."""
    if cu.is_legacy_ide():
        return CONFIG["IDE"]["HOME_DIR"], CONFIG["IDE"]["HOME_DIR"]
    return CONFIG["IDE"]["HOME_DIR_V2"], CONFIG["STORES"]["TEMP_STORE"]


def has_packages_in_env_file(env_file_path: str) -> bool:
    """
    Returns True if the environment.yml file contains at least one package
    in the 'dependencies' section.
    """
    env_file = Path(env_file_path)
    if not env_file.exists():
        return False

    with env_file.open("r") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError:
            return False  # invalid YAML

    if not isinstance(data, dict):
        return False

    deps = data.get("dependencies", [])
    if not deps:
        return False

    # deps can contain dicts for pip packages; check length
    for dep in deps:
        if isinstance(dep, str):
            return True
        elif isinstance(dep, dict) and dep.get("pip"):
            if dep["pip"]:
                return True

    return False


def resolve_upload_context(study_space_id, project, input_sample_ids,
                           do_prompt):
    """Resolves study space, project, and sample IDs, prompting the user if necessary."""
    if study_space_id is None:
        study_space_id = select_study_space(project)

    if not input_sample_ids:
        input_sample_ids = select_input_samples()

    if project:
        if do_prompt:
            check_default_project(project)
    elif study_space_id == no_study_default:
        project = get_default_project()
        if not project:
            raise ValueError(
                "Neither project nor study space specified and no default project is set for this IDE."
            )

    check_project_against_study_space(project, study_space_id)
    return study_space_id, project, input_sample_ids


def select_input_samples():
    provided_samples = cu.prompt_for_input(
        "Please provide input of comma separated sample ids for the files being uploaded: "
    )
    # Check for empty input
    if provided_samples is None or provided_samples == "":
        return []
    # replace qutoes and split by commas
    if '"' in provided_samples:
        provided_samples = provided_samples.replace('"', '')
    sampleIds = [s.strip() for s in provided_samples.split(",")]
    return sampleIds


def select_study_space(proj):
    pguid = None
    if proj is not None:
        pguid = cu.project_shortname_to_guid(proj)
    options = [{"name": no_study_default, "id": no_study_default}]
    for sp in get_study_spaces():
        if pguid is None or sp["projectGuid"] == pguid:
            options.append(sp)
    idx = cu.prompt_from_options("Select a study space",
                                 [d["name"] for d in options], True)
    return options[idx]["id"]


def validate_upload_context():
    if cu.is_legacy_ide():
        raise RuntimeError(CONFIG['PROMPTS']['UPLOAD_FROM_LEGACY'])
    if ide_is_from_guest_account() and cu.is_legacy_ide():
        if not cu.prompt_yn(CONFIG['PROMPTS']['UPLOAD_AS_GUEST']):
            raise RuntimeError("Upload cancelled by user.")
    if not cu.is_valid_upload_kernel():
        raise RuntimeError(CONFIG['PROMPTS']['INVALID_UPLOAD_KERNEL'])


def validate_app_path(app_path: str) -> None:
    """Ensure the Dash app entrypoint exists, is named 'app.py', and is in the allowed directory."""
    expected_name = DashAppImg.DASH_ENTRY_FILENAME
    prefix_home_path = CONFIG['IDE']['HOME_DIR_V2'] if not cu.is_legacy_ide(
    ) else IDE_HOME_DIR

    if os.path.basename(app_path) != expected_name:
        raise ValueError(f"App file must be called `{expected_name}`")
    if not os.path.exists(app_path):
        raise FileNotFoundError(f"{app_path} is not a valid file")
    abspath = os.path.abspath(app_path)
    if not abspath.startswith(prefix_home_path):
        raise PermissionError(f"App file must be within {prefix_home_path}")
    if cu.string_contains_whitespaces(app_path):
        raise ValueError(f"Filepath contains whitespace: {app_path}")


def validate_files(filenames: list[str]) -> None:
    """Ensure all provided files exist, are under /home/jupyter, and contain no spaces."""
    ide_dir = CONFIG['IDE']['HOME_DIR_V2'] if not cu.is_legacy_ide(
    ) else IDE_HOME_DIR
    for path in filenames or []:
        abs_path = os.path.abspath(path)
        if cu.string_contains_whitespaces(abs_path):
            raise ValueError(f"Whitespace detected in filepath: {abs_path}")
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"File not found: {abs_path}")
        if not abs_path.startswith(ide_dir):
            raise PermissionError(
                f"File outside allowed directory: {abs_path}")


def validate_hero_image(hero_image: str) -> None:
    """Validate that the hero image is a PNG file."""
    if not isinstance(hero_image, str) or cu.get_filetype(hero_image) != "png":
        raise ValueError("Hero image must be a PNG file path string.")


def validate_upload_data(files, study_space_id, project, title,
                         input_file_ids):
    files_not_found = []
    for f in files:
        if cu.string_contains_whitespaces(f):
            raise ValueError(
                "{} contains whitespace(s). Please rename this file by removing all whitespaces"
                .format(f))
        if not os.path.exists(f):
            files_not_found.append(f)
    if len(files_not_found) > 0:
        raise ValueError(
            "Cannot find the following file(s): {}. Please verify you have the correct filepath(s)"
            .format(files_not_found))
    if study_space_id is None:
        if project is None:
            raise ValueError("One of study space or project must be specified")
    if title is None:
        raise ValueError("Title cannot be empty")
    elif len(title) < 10:
        raise ValueError("Title must be at least 10 characters")

    # check if any files are within /home/workspace/private
    files_in_private = cu.files_within_private(files)
    if len(files_in_private) > 0:
        raise ValueError(
            "The following files are in your private folder: {}. These files cannot be uploaded from their current location. Please move to another directory and try again"
            .format(files_in_private))
    if len(input_file_ids) == 0:
        raise ValueError("You must specify at least one input file UUID")


def validate_upload_parameters(**kwargs):
    files, file_types, destination, store = (kwargs['files'],
                                             kwargs['file_types'],
                                             kwargs['destination'],
                                             kwargs['store'])
    if not files:
        raise ValueError("No files specified for upload.")
    if cu.string_contains_whitespaces(destination):
        raise ValueError(
            f"Destination path contains whitespace: {destination}")
    if file_types and len(file_types) != len(files):
        raise ValueError("file_types must have one entry per file.")
    if store and store not in valid_upload_stores:
        raise ValueError(
            f"Invalid store: {store}. Must be one of {valid_upload_stores}.")


def validate_upload_input_ids(input_file_ids: list, input_sample_ids: list,
                              ide_dir):
    """ Checks that files associated with a result have
        been seen in a user's IDE
    """
    cache_file_path = '{h}/{c}'.format(h=ide_dir,
                                       c=CONFIG['IDE']['CACHE_LOG_NAME'])

    if (not os.path.exists(cache_file_path)):
        raise FileNotFoundError(
            "No files have been downloaded into this IDE. You cannot upload results without utilizing any HISE input data."
        )

    cache_df = pyreadr.read_r(cache_file_path)[None]

    # loop through those ids and check they have been downloaded at some point
    invalid_file_ids = []
    mismatch_download_sources = dict()
    notebook_dir = os.getcwd()
    for f in input_file_ids:
        if (f not in cache_df['fileId'].unique()) and (
                f not in cache_df['replicaFileId'].unique()):
            invalid_file_ids += [f]

    invalid_sample_ids = []
    for s in input_sample_ids:
        if (s not in cache_df['sampleId'].unique()) and (
                s not in cache_df['replicaSampleId'].unique()):
            invalid_sample_ids += [s]

    if len(invalid_file_ids) > 0:
        raise ValueError(
            "The following file Ids were not downloaded in this IDE. You cannot reference a file in a result without downloading it first. {}"
            .format(invalid_file_ids))
    if len(invalid_sample_ids) > 0:
        raise ValueError(
            "The following sample Ids were not downloaded in this IDE. You cannot refernce a file in a result without downloading it first. {}"
            .format(invalid_sample_ids))

    return
