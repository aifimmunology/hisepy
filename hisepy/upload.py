import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import re
import uuid

import plotly.graph_objects as go
import requests

import hisepy.common_utils as cu
from hisepy.common_utils import parse_hise_response, hise_url, current_notebook, project_shortname_to_guid, project_guid_to_shortname
from hisepy import auth
from hisepy.auth import get_bearer_token_header, IDEInstance, debug, ide_is_from_regular_account, ide_is_from_guest_account, ide_is_from_certificate_account
from hisepy.utils import conda_env_builds

dataframe_file_type = "Visualization-dataframe"
freezer_ignore_endpoints = {"shutdown": None}
permanent_store = "permanent"
project_store = "project"
no_study_default = "no study"
valid_upload_stores = [permanent_store, project_store]
no_study_default = "no study"
upload_files_conda_env_checked = False
save_dash_conda_env_checked = False
save_visualization_conda_env_checked = False

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))
IDE_HOME_DIR = CONFIG['IDE']['HOME_DIR'] if not auth.debug() else os.getcwd()
UPLOAD_HARVEST_LOWER_BOUND = CONFIG['TOOLCHAIN'][
    'UPLOAD_HARVEST_LOWER_BOUND_MB']


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
                 do_prompt: bool = True,
                 do_conda_build_check=True):
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

    if (ide_is_from_regular_account()) and (cu.is_legacy_ide()): 
        raise SystemError(CONFIG['PROMPTS']['UPLOAD_FROM_LEGACY'])
    if ((ide_is_from_guest_account()) or (ide_is_from_certificate_account())) and (cu.is_legacy_ide()):
        if not cu.prompt_yn(CONFIG['PROMPTS']['UPLOAD_AS_GUEST']):
            return
        
    # check that the upload is from an acceptable kernel 
    if not cu.is_valid_upload_kernel():
        raise Exception(CONFIG['PROMPTS']['INVALID_UPLOAD_KERNEL'])
    
    # check that the users' default conda environment builds
    # if ran subsequently, and conda env builds successfully, skip this check
    global upload_files_conda_env_checked
    if not upload_files_conda_env_checked: 
        if (not do_conda_build_check) or (debug()):
            pass
        elif do_conda_build_check and (not conda_env_builds()):
            raise SystemError(CONFIG['PROMPTS']['CONDA_ENV_BUILD'])
        else:
            upload_files_conda_env_checked = True

    # determine if ide is legacy or nextgen; and assign variables accordingly
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


def retry_ide_commit(id: str):
    if cu.is_legacy_ide():
        raise Exception("Cannot retry commit on a legacy IDE")
    return cu.parse_hise_response(
        requests.put(
            cu.hise_url("ide_management",
                        "upload_file_v3_path",
                        id,
                        args={"condaEnvironmentFile": do_conda_export()})))


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


def get_study_spaces():
    """ Returns list of studies a user has access to """
    return parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "study_space_path"),
                         headers=get_bearer_token_header()))


def get_study_space(id):
    """ Returns the given study space, assuming the user has access """
    return parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "study_space_path", id),
                         headers=get_bearer_token_header()))


def get_files_for_query(query_id):
    """ Returns a list of file_ids pertaining to a HISE query_id """
    resp = parse_hise_response(
        requests.post(hise_url("hydration", "query_search_path", query_id),
                      headers=get_bearer_token_header()))
    return list(map(lambda x: x['file']['id'], resp))


def get_trace(trace_id):
    """ Returns trace object """
    trace = parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "trace_path", trace_id),
                         headers=get_bearer_token_header()))
    if len(trace) == 0:
        raise Exception("Trace id %s is invalid" % trace_id)
    return trace[0]


def default_study_space_id(must=True):
    return default_study_space(must)["id"]


def default_study_space(must=True):
    sspaces = get_study_spaces()
    if len(sspaces) == 0:
        if not must:
            return None
        raise ValueError(
            "User belongs to no study spaces! Cannot upload to HISE!")
    if len(sspaces) > 1:
        if not must:
            return None
        for s in sspaces:
            print("%s: %s" % (s["id"], s["name"]))
        raise ValueError(
            "User belongs to multiple study spaces. Please specify with the study_space_id parameter"
        )
    return sspaces[0]

# Save a plotly figure
# network call process:
# save_static_image (POST hydration/source/studyspace/file) of figure written to png
# upload_files (POST toolchain/file) of plotly figure data (separated from layout)
# POST toolchain/visualization/json with upload trace and image IDs
def save_visualization(
        pl_obj,
        study_space_id=None,  # optional
        project=None,  # optional unless study_space_id is not specified
        title=None,  # not actually optional
        destination=None,  #optional 
        input_file_ids=None,  # not optional
        input_sample_ids=None, # optional
        do_conda_build_check = True):  # optional
    """
    Save a plotly figure to a user's specified study. 

    Parameters: 
        pl_obj (plotly.Figure): (see LINK HERE)
        study_space_id (str): UUID of study to save visualization to
        project (str) : projectShortName to save visuzliation to
        title (str): 10+ character for visualization being uploaded
        destination (str):  Destination folder for the files 
        input_file_ids (list): list of file_ids from HISE that were utilized to generate visualization.
    Returns: 
        dictionary with keys ["trace_id", "files"]
    """
    if input_file_ids is None:
        input_file_ids = []
    if input_sample_ids is None:
        input_sample_ids = []
    if destination is None:
        destination = ""

    # check that the upload is from an acceptable kernel 
    if not cu.is_valid_upload_kernel():
        raise Exception(CONFIG['PROMPTS']['INVALID_UPLOAD_KERNEL'])
    
    tmp_data_file = "{}/{}".format(CONFIG['STORES']['TEMP_STORE'],
                                   CONFIG['VISUALIZATION']['PLOTLY_DATA_FILE'])
    tmp_plotly_file = "{}/{}".format(CONFIG['STORES']['TEMP_STORE'],
                                     CONFIG['VISUALIZATION']['PLOTLY_FILE'])
    tmp_img_file = "{}/{}".format(CONFIG['STORES']['TEMP_STORE'],
                                  CONFIG['VISUALIZATION']['PLOTLY_IMAGE_FILE'])
    log_dir = CONFIG['STORES']['TEMP_STORE'] if not cu.is_legacy_ide(
    ) else IDE_HOME_DIR
    pl_obj.write_image(tmp_img_file)
    if auth.debug():
        pass
    else:
        # check that the users' default conda environment builds 
        # if ran subsequently, and conda env builds successfully, skip this check
        global save_visualization_conda_env_checked
        if not save_visualization_conda_env_checked: 
            if (not do_conda_build_check) or (debug()):
                pass
            elif do_conda_build_check and (not conda_env_builds()):
                raise SystemError(CONFIG['PROMPTS']['CONDA_ENV_BUILD'])
            else:
                save_visualization_conda_env_checked = True
        cu.validate_upload_input_ids(input_file_ids, input_sample_ids, log_dir)
    if study_space_id is None:
        print(
            "study space id was not submitted. Saving the static image will not happen"
        )
        args = {"project": project}
    else:
        img_data = save_static_image(image=tmp_img_file,
                                     title=title,
                                     study_space_id=study_space_id)

        # if-else clause to handle if user is calling method from a guest workspace
        if img_data is None:
            args = {}
        else:
            args = {"images": img_data["id"]}
    os.remove(tmp_img_file)

    exp_obj = json.loads(pl_obj.to_json())

    f = open(tmp_data_file, "w")
    f.write(json.dumps(exp_obj["data"]))
    f.close()

    up_res = upload_files(files=[tmp_data_file],
                          study_space_id=study_space_id,
                          project=project,
                          title=title,
                          input_file_ids=input_file_ids,
                          input_sample_ids=input_sample_ids,
                          file_types=[dataframe_file_type],
                          store=permanent_store,
                          destination=destination,
                          do_prompt=False)
    args['traceId'] = up_res["TraceId"]

    # now null out the data and save the plotly without it
    exp_obj["data"] = []
    f = open(tmp_plotly_file, "w")
    f.write(json.dumps(exp_obj))
    f.close()

    vis_dict = {
        'file': (tmp_plotly_file, open(tmp_plotly_file,
                                       'rb'), 'application/json', {
                                           'Expires': '0'
                                       })
    }
    url = hise_url("toolchain", "visualization_path", "json", args=args)
    parse_hise_response(
        requests.post(url, headers=get_bearer_token_header(), files=vis_dict))
    #os.remove(tmp_data_file)
    #os.remove(tmp_plotly_file)
    return up_res


class DashAppImg:
    """ Class representing a Dash App Object """
    dash_app_name = 'app.py'

    def __init__(self,
                 app_filepath: str,
                 additional_files: list,
                 additional_dirs: list,
                 hero_image: str,
                 study_space_id: str,
                 input_file_ids: list,
                 work_dir: str,
                 title: str,
                 requirements: str = None,
                 description: str = None,
                 input_sample_ids=None):

        if input_sample_ids is None:
            input_sample_ids = []
        self.app_filepath = os.path.abspath(app_filepath)
        # store filepaths as set to automatically drop dupes
        self.filepaths = {os.path.abspath(path) for path in additional_files}
        self.directories = {os.path.abspath(path) for path in additional_dirs}
        self.hero_image = os.path.abspath(hero_image)
        self.requirements = os.path.abspath(
            requirements) if requirements is not None else None
        self.study_space_id = study_space_id
        self.input_file_ids = input_file_ids
        self.input_sample_ids = input_sample_ids
        self.title = title
        self.description = description
        self.work_dir = work_dir

    def create_req_txt(self):
        if self.requirements is None:
            subprocess.run([
                'pipreqs', '--savepath', '{wd}/{app}/requirements.in'.format(
                    wd=self.work_dir, app=os.path.dirname(self.app_filepath)),
                '{}'.format(self.work_dir)
            ],
                           check=True,
                           capture_output=True)
            subprocess.run([
                'pip-compile', '--no-annotate', '--no-header', '--quiet',
                '--strip-extras', '{wd}/{app}/requirements.in'.format(
                    wd=self.work_dir, app=os.path.dirname(self.app_filepath))
            ],
                           check=True)
        else:
            subprocess.run([
                'pip-compile', '--no-annotate', '--no-header', '--quiet',
                '--strip-extras',
                '--output-file={wd}/{app}/requirements.txt'.format(
                    wd=self.work_dir, app=os.path.dirname(
                        self.app_filepath)), self.requirements
            ],
                           check=True)

    def upload_hero_image(self):
        # I don't think this title is ever user-visible, but save_static_image requires it
        image_title = self.title if len(
            self.title) >= 10 else "dash app static image"
        return save_static_image(image=self.hero_image,
                                 title=image_title,
                                 study_space_id=self.study_space_id)

    def create_dash_image(self):
        """Creates image by bundling all required objects"""
        tarfile_path = '{wd}/dash_app.tar.gz'.format(wd=self.work_dir)
        with tarfile.open(tarfile_path, "w:gz") as tar:
            tar.add(self.work_dir, arcname="")
        return True

    def export_dash_image(self):
        """ Uploads, saves and deploys Dash app """

        img_resp = self.upload_hero_image()
        if img_resp['error'] is not False:
            print("Error uploading image: ", img_resp['error'])

        print("POST hydration/source/studyspace/file for hero image:")
        print(img_resp)

        upload_resp = upload_files(
            files=['{wd}/dash_app.tar.gz'.format(wd=self.work_dir)],
            study_space_id=self.study_space_id,
            title=self.title,
            input_file_ids=self.input_file_ids,
            input_sample_ids=self.input_sample_ids,
            store=permanent_store,
            do_prompt=False)

        print("POST toolchain/file for dash app tarball:")
        print(upload_resp)
        homedir = IDE_HOME_DIR if cu.is_legacy_ide(
        ) else CONFIG['IDE']['HOME_DIR_V2']
        save_args = {
            "studySpaceId": self.study_space_id,
            "title": self.title,
            "instanceId": IDEInstance().friendlyName,
            "inputFileIds": self.input_file_ids,
            "sampleIds": self.input_sample_ids,
            "notebook": current_notebook(),
            "homedir": homedir,
            "images": img_resp['id'],
            "traceId": upload_resp['TraceId']
        }
        save_url = hise_url("toolchain", "save_dash_app_path", args=save_args)
        headers = get_bearer_token_header()
        # We don't technically need the save response because it's the same Trace ID,
        # but we'll go through it to help with debugging if save returns something crazy
        save_resp = parse_hise_response(
            requests.post(save_url, headers=headers))

        print("POST toolchain/visualization/dash to save dash app:")
        print(save_resp)

        deploy_url = hise_url("toolchain",
                              "deploy_dash_app_path",
                              resource=save_resp['TraceId'])
        deploy_resp = parse_hise_response(
            requests.post(deploy_url, headers=headers))

        print("POST toolchain/deploy/visualization to deploy dash app:")
        print(deploy_resp)

        return deploy_resp


def validate_app_path(app_path):
    if os.path.basename(app_path) != 'app.py':
        raise ValueError("App file must be called `app.py`")
    if not os.path.exists(app_path):
        raise ValueError("%s is not a valid file" % app_path)
    abspath = os.path.abspath(app_path)
    prefix_home_path = CONFIG['IDE']['HOME_DIR_V2'] if not cu.is_legacy_ide(
    ) else IDE_HOME_DIR
    if not abspath.startswith(prefix_home_path):
        raise ValueError("App file must be within %s" % prefix_home_path)
    if cu.string_contains_whitespaces(app_path):
        raise ValueError(
            "Your filepath contains whitespaces. Please try again after removing whitespaces from the following file: {}"
            .format(app_path))


def validate_files(filenames):
    """ Verifies that all submitted input files exist and are in /home/jupyter """
    ide_dir = CONFIG['IDE']['HOME_DIR_V2'] if not cu.is_legacy_ide() else IDE_HOME_DIR
    for this_f in filenames:
        abs_path = os.path.abspath(this_f)
        if cu.string_contains_whitespaces(abs_path):
            raise ValueError(
                "The following additional_file contains whitespaces. Please remove all whitespaces for the following filepath: {}"
                .format(abs_path))
        if not os.path.exists(abs_path):
            # Echo user's input back to them for easy reference along with
            # where we expected that file to be. It would be nicer to
            # validate *all* the input and then mention *all* the problems,
            # especially as this is coming after multiple other HISE calls,
            # so retrying is kinda expensive, but here we are.
            raise FileNotFoundError("Can't find '%s' (no such file: %s)" %
                                    (this_f, abs_path))
        if not abs_path.startswith(ide_dir):
            raise Exception(
                "Only files under %s can be included.  Not there: %s" %
                (ide_dir, abs_path))


def validate_hero_image(hero_image):
    if type(hero_image) != str or cu.get_filetype(hero_image) != 'png':
        raise ValueError("image must be a PNG")


def create_temp_directory_files(list_paths: list, tmpdirname: str):
    """ Takes a list of filepaths, and creates a temporary directory that contains all files. 
        paths are preserved when copying files to the temporary directory. 
    """
    for f in list_paths:
        rel_path = os.path.relpath(f, '/')
        if os.path.isfile(f):
            dst = os.path.normpath(
                tmpdirname +
                os.path.dirname(f))  # create path up until the filename
            if not os.path.exists(dst):
                os.makedirs(dst)
            shutil.copy(f, dst)
        elif os.path.isdir(f):
            dst = os.path.join(
                tmpdirname,
                rel_path)  # we want to keep the entire path that's passed in
            shutil.copytree(f, dst)
    return


def save_dash_app(app_filepath: str,
                  additional_files: list,
                  additional_dirs: list,
                  input_file_ids: list,
                  study_space_id: str,
                  title: str,
                  description: str = None,
                  image: str = None,
                  requirements: str = None,
                  input_sample_ids: list = None,
                  do_conda_build_check=True):
    """
    Given a Dash app consisting of an entry point named `app.py` and a list of supporting files, upload and deploy that
    app to HISE as a visualization in the given study space.

    Parameters:
        app_filepath (str): path to file named app.py that serves your Dash app
            (i.e., ends with `app.run_server(host='0.0.0.0')`)
        additional_files (list): list of additional files used by your app (e.g., data files, custom CSS).
            Only files under /home/jupyter can be included.
        input_file_ids (list): list of HISE file UUIDs that this app visualizes
        study_space_id (str): UUID of study space to save app to
        title (str): a 10+ character title for the app
        description (str): description of app being uploaded 
        image (str): png thumbnail image for app in study space
        input_sample_ids (list): list of samples UUIDs that this app visualizes
    Returns:
        Response from server
    Example:
        hisepy.save_dash_app(app_filepath='dash_app/app.py',
                            additional_files=['data/input-1.csv', 'data/input-2.csv'],
                            input_file_ids=['9f6d7ab5-1c7b-4709-9455-3d8ffffbb6c8','0fb06e51-74c4-46be-b92d-5e045232b2d9'],
                            study_space_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                            title="Hello world Dash app",
                            description="An amazingly complex data visualization",
                            image="dash_app/thumbnail.png",
                            input_sample_ids=['93ea6cb8-a45f-4370-bbfe-d57ba6420882'])
    """
    if input_sample_ids is None:
        input_sample_ids = []

    # check that the upload is from an acceptable kernel 
    if not cu.is_valid_upload_kernel():
        raise Exception(CONFIG['PROMPTS']['INVALID_UPLOAD_KERNEL'])
    
    # check that the users' default conda environment builds
    # if ran subsequently, and conda env builds successfully, skip this check
    global save_dash_conda_env_checked
    if not save_dash_conda_env_checked: 
        if (not do_conda_build_check) or (debug()):
            pass
        elif do_conda_build_check and (not conda_env_builds()):
            raise SystemError(CONFIG['PROMPTS']['CONDA_ENV_BUILD'])
        else:
            save_dash_conda_env_checked = True

    # validate ASAP to avoid making a couple network calls before failing
    validate_app_path(app_filepath)
    validate_files(additional_files)
    validate_hero_image(image)
    log_dir = CONFIG['STORES']['TEMP_STORE'] if not cu.is_legacy_ide(
    ) else IDE_HOME_DIR
    if auth.debug():
        pass
    else:
        cu.validate_upload_input_ids(input_file_ids, input_sample_ids, log_dir)
    home_dir_prefix = CONFIG['IDE']['HOME_DIR_V2'] if not cu.is_legacy_ide(
    ) else IDE_HOME_DIR
    tmpdirname = tempfile.mkdtemp(prefix='{}/'.format(home_dir_prefix))

    # set permissions so toolchain can read and copy this file
    os.chmod(tmpdirname, 0o777)

    # create static dash image
    dobj = DashAppImg(app_filepath=app_filepath,
                      additional_files=additional_files,
                      additional_dirs=additional_dirs,
                      hero_image=image,
                      study_space_id=study_space_id,
                      input_file_ids=input_file_ids,
                      title=title,
                      description=description,
                      requirements=requirements,
                      input_sample_ids=input_sample_ids,
                      work_dir=tmpdirname)

    # Insert UI widget code here:

    # move everything to a temporary dir while creating/preserving source
    # directories
    app_files = dobj.filepaths.union({dobj.app_filepath})
    app_files = app_files.union(dobj.directories)
    create_temp_directory_files(app_files, tmpdirname)

    # create .txt files that contains user's imported libraries
    dobj.create_req_txt()

    # tar it up; upload; and clean up
    dobj.create_dash_image()

    resp = dobj.export_dash_image()

    print('dash image was successfully uploaded!')
    return resp


def save_static_image(image, title, study_space_id=None):
    """
    Saves a PNG image to a study
    
    Parameters: 
        image (str): absolute path to image 
        title (str): title of image being uploaded 
        study_space_id (str): UUID of study
    Returns: 
        Response from server
    Example: 
        hp.save_static_image(image='/home/jupyter/imgs/viz_image.png', 
                             title='visualization title',
                             study_space_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba')
    """
    if not os.path.exists(image):
        raise ValueError("%s is not a valid file." % image)

    img_dict = {
        'bytes': (image, open(image,
                              'rb'), "image/%s" % (cu.get_filetype(image)))
    }
    validate_upload_data(files=[image],
                         study_space_id=study_space_id,
                         project=None,
                         title=title,
                         input_file_ids=["not a file"])
    args = {"studySpaceId": study_space_id, "title": title}
    return parse_hise_response(
        requests.post(hise_url("hydration", "upload_path", args=args),
                      headers=get_bearer_token_header(),
                      files=img_dict))


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
            .format(files_in_private)
        )
    if len(input_file_ids) == 0:
        raise ValueError("You must specify at least one input file UUID")


def load_visualization(id):
    """ 
    Loads a plotly visualization to user
    
    Parameters: 
        id (str): trace id or visualization id 
    Returns: 
        plotly figure
    """
    return go.Figure(parse_hise_response(
        requests.request("GET",
                         hise_url("toolchain", "visualization_path", id),
                         headers=get_bearer_token_header())),
                     skip_invalid=True)


def get_size_in_megabytes(file_list, convert_to_megabytes=True):
    total_size = 0
    for file in file_list:
        if os.path.isfile(file):
            total_size += os.path.getsize(file)
    if not convert_to_megabytes:
        return total_size
    else:
        return total_size / (1024 * 1024)  # convert bytes to megabytes
