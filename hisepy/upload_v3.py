import requests
import os
import re
import shutil
import subprocess
import hisepy.common_utils as cu
from hisepy.auth import get_bearer_token_header, HiseUser, IDEInstance, debug, ide_instance_guid, get_from_metadata_server
from hisepy.common_utils import project_shortname_to_guid, project_guid_to_shortname
from hisepy.upload import valid_upload_stores, get_study_spaces, validate_upload_data, get_size_in_megabytes

no_study_default = "no study"
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def set_default_store(store=None):
    return IDEInstance().set_default_store(store)


def set_default_project(project=None):
    return IDEInstance().set_default_project(project)


def get_default_store():
    return IDEInstance().get_default_store()


def get_default_project():
    return IDEInstance().get_default_project()


def upload_files(files: list,
                 study_space_id: str = None,
                 project: str = None,
                 title: str = None,
                 input_file_ids: list = [],
                 input_sample_ids: list = [],
                 file_types: list = [],
                 store: str = None,
                 destination: str = "",
                 do_prompt: bool = True):
    """
    Uploads files to a store and records their provenance in HISE, but V3

    Parameters:
        files (list): absolute filepath of file to be uploaded
        study_space_id (str): ID that pertains to a study in the collaboration space (optional)
        project (str): project short name (required if study space is not specified, defaults to the ide's default setting
        title (str): 10+ character title for upload result 
        input_file_ids (list): fileIds from HISE that were utilized to generate a user's result
        input_sample_ids (list): sampleIds from HISE that were utilized to generate a user's result
        file_types (str): filetype of uploaded files 
        store (str): Which store ('project' or 'permanent') to use for the files, defaults to the ide's setting
        destination (str): Destination folder for the files 
        do_prompt (bool): whether or not to prompt for user's input, asking to proceed.
    Returns: 
        dictionary with keys ["trace_id", "files"]
    Example: 
        hp.upload_files(files=['/home/jupyter/upload_file.csv'],
                        study_space_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                        title='a upload title',
                        input_file_ids=['9f6d7ab5-1c7b-4709-9455-3d8ffffbb6c8'])
    """
    # determine if ide is legaxy or nextgen; and assign variables accordingly
    inst = IDEInstance()
    ide_name = inst.podName
    ide_guid = inst.id
    if cu.is_legacy_ide(): 
        file_log_dir = CONFIG['IDE']['HOME_DIR']
        home_dir = CONFIG["IDE"]["HOME_DIR"]
    else: 
        file_log_dir = CONFIG['STORES']['TEMP_STORE']
        home_dir = CONFIG["IDE"]["HOME_DIR_V2"]

    if len(file_types) > 0 and len(file_types) != len(files):
        raise ValueError(
            "File types must be a list with one type for each upload")
    if store is not None:
        if store not in valid_upload_stores:
            raise ValueError("Value for store must be in %s" %
                             (", ".join(valid_upload_stores)))
        if do_prompt:
            check_default_store(store)
    else:
        store = get_default_store()

    if study_space_id is None:
        study_space_id = select_study_space(project)

    if project is not None:
        if do_prompt:
            check_default_project(project)
    elif study_space_id == no_study_default:
        project = get_default_project()
        if project is None:
            raise ValueError(
                "Neither project nor study space was specified and there is no default project set for this IDE. You must specify one of the former or set the latter."
            )

    check_project_against_study_space(project, study_space_id)

    if len(files) == 0:
        raise ValueError("No files specified for upload")
    if cu.string_contains_whitespaces(destination):
        raise ValueError(
            "destination directory %s contains whitespaces. Please rename and remove any whitespaces"
            % destination)
    if debug():
        pass
    else:
        cu.validate_upload_input_ids(input_file_ids, input_sample_ids,
                                     file_log_dir)
    validate_upload_data(files, study_space_id, project, title, input_file_ids)
    qargs = {
        "title": title,
        "fileType": [],
        "saveIDE": True,
        "store": store,
        "destination": destination,
        "instanceId": ide_name,
        "instanceGuid": ide_guid,
        "inputFileIds": input_file_ids,
        "project": project,
        "sampleIds": input_sample_ids,
        "notebook": cu.current_notebook(),
        "homedir": home_dir
    }
    # export conda env to file 
    # TODO: test without exporting anything 
    if not cu.is_legacy_ide():
        qargs["condaEnvironmentFile"] = do_conda_export()

    if study_space_id is not no_study_default:
        qargs["studySpaceId"] = study_space_id

    url = cu.hise_url("ide_management", "upload_file_v3_path", args=qargs)
    return cu.parse_hise_response(
        requests.post(url,
                      json=gen_upload_body(files, file_types),
                      headers=get_bearer_token_header()))


def gen_upload_body(files, filetypes):
    body = {"files": []}
    for i, f in enumerate(files):
        if not os.path.exists(f):
            raise ValueError("%s is not a valid file." % f)
        ft = filetypes[i] if len(filetypes) > i else cu.get_filetype(f)
        body["files"].append({"name": os.path.abspath(f), "type": ft})
    return body


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


def get_conda_env_name():
    """
    Returns the name of the current conda environment
    """
    # get IDE instance
    inst = IDEInstance()

    # get the name of the current conda environment
    return inst.environment['condaEnvName']


def do_conda_export():
    """
    Exports the current conda environment to a file
    """
    # export to scratch and move to to staging store
    env_dir = "{}/{}".format(CONFIG["STORES"]["ENV_STORE"],
                             get_conda_env_name())
    subprocess.run("conda env export -p {env} > {dir}/environment.yml".format(
        env=env_dir, dir=CONFIG["STORES"]["TEMP_STORE"]),
                   shell=True)

    # check that the environment file isn't empty
    if (get_size_in_megabytes(
        ["{dir}/environment.yml".format(dir=CONFIG["STORES"]["TEMP_STORE"])],
            False) == 0) and not debug():
        raise ValueError(
            "Environment file is empty, please ensure that the conda environment is active and not empty."
        )

    return "{dir}/environment.yml".format(dir=CONFIG["STORES"]["TEMP_STORE"])


def select_study_space(proj):
    pguid = None
    if proj is not None:
        pguid = project_shortname_to_guid(proj)
    options = [{"name": no_study_default, "id": no_study_default}]
    for sp in get_study_spaces():
        if pguid is None or sp["projectGuid"] == pguid:
            options.append(sp)
    idx = cu.prompt_from_options("Select a study space",
                                 [d["name"] for d in options], True)
    return options[idx]["id"]


def get_study_space(id):
    """ Returns list of studies a user has access to """
    return cu.parse_hise_response(
        requests.request("GET",
                         cu.hise_url("tracer", "study_space_path", id),
                         headers=get_bearer_token_header()))


def move_file_to_output_staging(file: str,
                                project: str,
                                study_space_id: str,
                                replace_ok: bool = False):
    sdir = re.sub(r'\W+', '', study_space_id).lower()
    if study_space_id != no_study_default:
        ss = get_study_space(study_space_id)
        if project is None:
            project = project_guid_to_shortname(ss["projectGuid"])
        sdir = re.sub(r'\W+', '', ss['name']).lower()
    elif project is None:
        #this should have been caught earlier and if you get here your code is very bad
        raise ValueError(
            "Neither project nor study space was set, cannot move file")
    pdir = re.sub(r'\W+', '', project).lower()
    dest_dir = "%s/%s/%s" % (cu.get_from_config('stores',
                                                'output_store'), pdir, sdir)
    dest_file = "%s/%s" % (dest_dir, os.path.basename(file))
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir)
    elif os.path.exists(dest_file) and not replace_ok:
        raise ValueError(
            "The file %s is already in the output directory for %s and study %s. Either rename the file to be uploaded or, if you are sure it isn't being used, delete it from %s manually and run the upload command again."
            % (os.path.basename(file), project, study_space_id, dest_dir))
    elif os.path.exists(dest_file) and replace_ok:
        os.remove(dest_file)
    shutil.copy(file, dest_file)
    return dest_file


def check_project_against_study_space(project, study_space_id):
    if project is None:
        return
    elif study_space_id is None or study_space_id is no_study_default:
        return

    pguid = project_shortname_to_guid(project)
    ss = get_study_space(study_space_id)
    if "projectGuid" not in ss:
        raise ValueError("%s was not a valid study space" % study_space_id)

    if pguid != ss["projectGuid"]:
        raise ValueError(
            "The specified study space %s is not in the project %s" %
            (ss["name"], project))
