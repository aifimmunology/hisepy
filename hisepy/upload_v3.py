import requests
import os
import re
import shutil

import hisepy.common_utils as cu
from hisepy.auth import get_bearer_token_header
from hisepy.abstraction import project_shortname_to_guid, project_guid_to_shortname
from hisepy.common_utils import current_notebook
from hisepy.instances import HiseUser, IDEInstance
from hisepy.upload import valid_upload_stores, get_study_spaces, validate_upload_data, IDE_HOME_DIR

no_study_default = "no study"


def set_default_store(store=None):
    return IDEInstance().set_default_store(store)


def set_default_project(project=None):
    return IDEInstance().set_default_project(project)


def get_default_store():
    return IDEInstance().get_default_store()


def get_default_project():
    return IDEInstance().get_default_project()


def upload_files_v3(files: list,
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
        qargs["project"] = project
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

    cu.validate_upload_input_ids(input_file_ids, input_sample_ids)
    validate_upload_data(files, study_space_id, project, title, input_file_ids)
    inst = IDEInstance()
    qargs = {
        "title": title,
        "fileType": [],
        "saveIDE": True,
        "store": store,
        "destination": destination,
        "instanceId": inst.friendlyName,
        "instanceGuid": inst.id,
        "inputFileIds": input_file_ids,
        "project": project,
        "sampleIds": input_sample_ids,
        "notebook": current_notebook(),
        "homedir": IDE_HOME_DIR
    }
    if study_space_id is not no_study_default:
        qargs["studySpaceId"] = study_space_id

    body = {"files": []}
    if do_prompt:
        print("Copying files to output staging...")
    for i, f in enumerate(files):
        if not os.path.exists(f):
            raise ValueError("%s is not a valid file." % f)
        ft = file_types[i] if len(file_types) > i else cu.get_filetype(f)
        output = move_file_to_output_staging(os.path.abspath(f), project,
                                             study_space_id)
        body["files"].append({"name": output, "type": ft})

    url = cu.hise_url("toolchain", "upload_file_v3_path", args=qargs)
    return cu.parse_hise_response(
        requests.post(url, json=body, headers=get_bearer_token_header()))


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


def move_file_to_output_staging(file: str, project: str, study_space_id: str):
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
    elif os.path.exists(dest_file):
        raise ValueError(
            "The file %s is already in the output directory for %s and study %s. Either rename the file to be uploaded or, if you are sure it isn't being used, delete it from %s manually and run the upload command again."
            % (os.path.basename(file), project, study_space_id, dest_dir))
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
            ss["name"], project)
