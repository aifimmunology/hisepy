import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid

import plotly.graph_objects as go
import requests

import hisepy.common_utils as cu
from hisepy import auth
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, instance_name_path
from hisepy.reader import parse_hise_response, hise_url
from hisepy.scheduler import current_notebook

dataframe_file_type = "Visualization-dataframe"
freezer_ignore_endpoints = {"shutdown": None}
permanent_store = "permanent"
project_store = "project"
valid_upload_stores = [permanent_store, project_store]

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))
IDE_HOME_DIR = CONFIG['IDE']['HOME_DIR'] if not auth.debug() else os.getcwd()
UPLOAD_HARVEST_LOWER_BOUND = CONFIG['TOOLCHAIN'][
    'UPLOAD_HARVEST_LOWER_BOUND_MB']


def get_study_spaces():
    """ Returns list of studies a user has access to """
    return parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "study_space_path"),
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


def upload_files(files: list,
                 study_space_id: str = None,
                 project: str = None,
                 title: str = None,
                 input_file_ids=None,
                 input_sample_ids=None,
                 file_types=None,
                 store=None,
                 destination=None,
                 do_prompt: bool = True):
    """
    Uploads files to a specified study.

    Parameters:
        files (list): absolute filepath of file to be uploaded
        study_space_id (str): ID that pertains to a study in the collaboration space (optional)
        project (str): project short name (required if study space is not specified)
        title (str): 10+ character title for upload result 
        input_file_ids (list): fileIds from HISE that were utilized to generate a user's result
        input_sample_ids (list): sampleIds from HISE that were utilized to generate a user's result
        file_types (str): filetype of uploaded files 
        store (str): Which store ('project' or 'permanent') to use for the files (default in 'project')
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
    if input_file_ids is None:
        input_file_ids = []
    if input_sample_ids is None:
        input_sample_ids = []
    if file_types is None:
        file_types = []
    elif type(file_types) is not list:
        raise ValueError(
            "File types must be a list with one type for each upload")
    elif len(file_types) != len(files):
        raise ValueError(
            "File types must be a list with one type for each upload")
    if store is not None:
        if store not in valid_upload_stores:
            raise ValueError("Value for store must be in %s" %
                             (", ".join(valid_upload_stores)))

    if destination is not None:
        if type(destination) is not str:
            raise ValueError("file destination directory must be a string")
    else:
        destination = ""

    def _user_prompt_upload(prompt_files: list):
        print(
            'you are trying to upload file_ids... {}. Do you truly want to proceed?'
            .format(prompt_files))
        user_input = input('(y/n)')
        while user_input.lower() not in ['y', 'n']:
            print('please enter either "n" for no, or "y" for yes.')
            user_input = input('(y/n)')
        if user_input.lower() == 'y':
            return True
        elif user_input.lower() == 'n':
            return False

    if type(files) is not list or len(files) == 0:
        raise ValueError("No files specified for upload")
    if cu.string_contains_whitespaces(destination):
        raise ValueError(
            "destination param, {}, contains whitespaces. Please rename and remove any whitespaces"
            .format(destination))
    cu.validate_upload_input_ids(input_file_ids, input_sample_ids)
    validate_upload_data(files, study_space_id, project, title, input_file_ids)
    uploads = None
    body = None
    qargs = {
        "title": title,
        "fileType": [],
        "saveIDE": True,
        "store": store,
        "destination": destination,
        "instanceId": get_from_metadata_server(instance_name_path),
        "inputFileIds": input_file_ids,
        "sampleIds": input_sample_ids,
        "notebook": current_notebook(),
        "homedir": IDE_HOME_DIR
    }
    if study_space_id is not None:
        qargs["studySpaceId"] = study_space_id
    if project is not None:
        qargs["project"] = project
    if get_size_in_megabytes(files) > UPLOAD_HARVEST_LOWER_BOUND:
        #user is uploading big stuff.
        #do this as a harvest
        qargs["harvest"] = True

        # flag to tell toolchain to clean up any temporary directories that a SDK call creates
        if CONFIG['FILETYPES']['DASH_APP'] in files[0]:
            qargs['deleteFiles'] = True
        body = {"files": []}
        for i, f in enumerate(files):
            if not os.path.exists(f):
                raise ValueError("%s is not a valid file." % f)
            ft = file_types[i] if len(file_types) > i else cu.get_filetype(f)
            body["files"].append({"name": os.path.abspath(f), "type": ft})
    else:
        uploads = []
        for i, f in enumerate(files):
            if not os.path.exists(f):
                raise ValueError("%s is not a valid file." % f)

            uploads.append(('file', (f, open(f, 'rb'), 'application/json', {
                'Expires': '0'
            })))
            qargs["fileType"].append(
                file_types[i] if len(file_types) > i else cu.get_filetype(f))

    url = hise_url("toolchain", "upload_file_path", args=qargs)
    headers = get_bearer_token_header()
    if not do_prompt or _user_prompt_upload(prompt_files=files):
        df_data = parse_hise_response(
            requests.post(url, headers=headers, json=body, files=uploads))
        return {"trace_id": df_data["TraceId"], "files": files}
    else:
        print('Uploading canceled.')
        return {}


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
        input_sample_ids=None):  # optional
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
    tmp_data_file = "/tmp/plotly_data.json"
    tmp_plotly_file = "/tmp/plotly.json"
    tmp_img_file = "/tmp/plotly.png"

    pl_obj.write_image(tmp_img_file)
    cu.validate_upload_input_ids(input_file_ids, input_sample_ids)
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
    args['traceId'] = up_res["trace_id"]

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
    os.remove(tmp_data_file)
    os.remove(tmp_plotly_file)
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
        self.requirements = os.path.abspath(requirements)
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
                'pip-compile', '--no-annotate', '--no-header', '--quiet', '--strip-extras',
                '{wd}/{app}/requirements.in'.format(
                    wd=self.work_dir, app=os.path.dirname(self.app_filepath))
            ],
                        check=True)
        else:
            subprocess.run([
                'pip-compile', '--no-annotate', '--no-header', '--quiet', '--strip-extras',
                '--output-file={wd}/home/jupyter/requirements.txt'.format(
                    wd=self.work_dir, app=os.path.dirname(self.app_filepath)),
                self.requirements
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

        save_args = {
            "studySpaceId": self.study_space_id,
            "title": self.title,
            "instanceId": get_from_metadata_server(instance_name_path),
            "inputFileIds": self.input_file_ids,
            "sampleIds": self.input_sample_ids,
            "notebook": current_notebook(),
            "homedir": IDE_HOME_DIR,
            "images": img_resp['id'],
            "traceId": upload_resp['trace_id']
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

    if not abspath.startswith(IDE_HOME_DIR):
        raise ValueError("App file must be within %s" % IDE_HOME_DIR)
    if cu.string_contains_whitespaces(app_path):
        raise ValueError(
            "Your filepath contains whitespaces. Please try again after removing whitespaces from the following file: {}"
            .format(app_path))


def validate_files(filenames):
    """ Verifies that all submitted input files exist and are in /home/jupyter """
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
        if not abs_path.startswith(IDE_HOME_DIR):
            raise Exception(
                "Only files under %s can be included.  Not there: %s" %
                (IDE_HOME_DIR, abs_path))


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
                  input_sample_ids: list = None):
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

    # validate ASAP to avoid making a couple network calls before failing
    validate_app_path(app_filepath)
    validate_files(additional_files)
    validate_hero_image(image)
    cu.validate_upload_input_ids(input_file_ids, input_sample_ids)
    tmpdirname = tempfile.mkdtemp(prefix='{}/'.format(IDE_HOME_DIR))

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

    # tar it up; upload; and clean up
    dobj.create_dash_image()

    # create .txt files that contains user's imported libraries
    dobj.create_req_txt()

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


def get_size_in_megabytes(file_list):
    total_size = 0
    for file in file_list:
        if os.path.isfile(file):
            total_size += os.path.getsize(file)
    return total_size / (1024 * 1024)  # convert bytes to megabytes
