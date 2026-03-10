import json
import operator
import os
import pandas as pd
import plotly
import plotly.graph_objects as go
import re
import requests
import shutil
import subprocess
import tarfile
import tempfile
from enum import Enum
from IPython.display import HTML, display  # TODO: Add ipython to requirements.txt
from pathlib import Path
from typing import Any

import hisepy.common_utils as cu
import hisepy.upload_utils as hpu
from hisepy.common_utils import parse_hise_response, hise_url, current_notebook, project_shortname_to_guid, project_guid_to_shortname
from hisepy.auth import get_bearer_token_header, IDEInstance, debug, ide_instance_guid, ide_is_from_guest_account, guest_hise_server
from hisepy.utils import conda_env_builds
from hisepy.logging import with_default_logging, logger
from hisepy.pixi_pack import get_pixi_env_dir

dataframe_file_type = "Visualization-dataframe"
upload_files_conda_env_checked = False
save_dash_conda_env_checked = False
save_visualization_conda_env_checked = False

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))
IDE_HOME_DIR = CONFIG['IDE']['HOME_DIR'] if not debug() else os.getcwd()
UPLOAD_HARVEST_LOWER_BOUND = CONFIG['TOOLCHAIN'][
    'UPLOAD_HARVEST_LOWER_BOUND_MB']


class DashAppImg:
    """Encapsulates a Dash app and its associated upload and deployment workflow."""

    DASH_ENTRY_FILENAME = "app.py"

    def __init__(self,
                 app_filepath: str,
                 additional_files: list[str],
                 additional_dirs: list[str],
                 hero_image: str,
                 study_space_id: str,
                 input_file_ids: list[str],
                 work_dir: str,
                 title: str,
                 do_conda_build_check: bool,
                 requirements: str | None = None,
                 description: str | None = None,
                 input_sample_ids: list[str] | None = None,
                 data_mount_path: str | None = None,
                 data_source_file_ids: list[str] | None = None):
        self.app_filepath = os.path.abspath(app_filepath)
        self.filepaths = {os.path.abspath(f) for f in additional_files or []}
        self.directories = {os.path.abspath(d) for d in additional_dirs or []}
        self.hero_image = os.path.abspath(hero_image)
        self.requirements = os.path.abspath(
            requirements) if requirements else None
        self.study_space_id = study_space_id
        self.input_file_ids = input_file_ids or []
        self.input_sample_ids = input_sample_ids or []
        self.title = title
        self.description = description
        self.work_dir = work_dir
        self.do_conda_build_check = do_conda_build_check
        self.data_mount_path = data_mount_path
        self.data_source_file_ids = data_source_file_ids
        self.conda_pack_env_path = f"{CONFIG['STORES']['ENV_STORE']}/{hpu.get_ide_env_name()}"

    def create_requirements_file(self) -> None:
        """Generate or compile a requirements.txt file for the Dash app."""
        app_dir = os.path.dirname(self.app_filepath)
        req_in_path = f"{self.work_dir}/{app_dir}/requirements.in"
        req_txt_path = f"{self.work_dir}/{app_dir}/requirements.txt"

        try:
            if self.requirements and 'requirements.in' == os.path.basename(
                    self.requirements):
                subprocess.run([
                    "bash", "-c",
                    f"source /opt/conda/etc/profile.d/conda.sh && "
                    f"conda activate {self.conda_pack_env_path} && "
                    f"pip-compile --no-annotate --no-header --quiet --strip-extras "
                    f"--output-file={self.work_dir}/{os.path.dirname(self.app_filepath)}/requirements.txt "
                    f"{self.requirements}"
                ],
                               check=True)
            elif self.requirements and "requirements.txt" == os.path.basename(
                    self.requirements):
                # save file to directory of app_filepath
                shutil.copy(
                    self.requirements,
                    f"{self.work_dir}/{os.path.dirname(self.app_filepath)}")
            else:
                logger.debug("Generating requirements.in using pipreqs...")
                subprocess.run(
                    ["pipreqs", "--savepath", req_in_path, self.work_dir],
                    check=True,
                    capture_output=True,
                )
                subprocess.run(
                    [
                        "pip-compile", "--no-annotate", "--no-header",
                        "--quiet", "--strip-extras", req_in_path
                    ],
                    check=True,
                )
        except subprocess.CalledProcessError as e:
            logger.error("Failed to create requirements file: %s", e.stderr
                         or e)
            raise RuntimeError("Failed to generate requirements.txt") from e

    def upload_hero_image(self) -> dict:
        """Upload the hero (thumbnail) image for this Dash app."""
        image_title = self.title if len(
            self.title or "") >= 10 else "dash app static image"
        logger.debug("Uploading hero image: %s", self.hero_image)
        return save_static_image(
            image=self.hero_image,
            title=image_title,
            study_space_id=self.study_space_id,
        )

    def create_dash_tarball(self) -> str:
        """Create a compressed archive of the Dash app directory."""
        tarfile_path = os.path.join(self.work_dir, "dash_app.tar.gz")
        logger.debug("Creating tarball: %s", tarfile_path)
        with tarfile.open(tarfile_path, "w:gz") as tar:
            tar.add(self.work_dir, arcname="")
        return tarfile_path

    def export(self) -> dict:
        """Upload and deploy the Dash app as a visualization."""
        logger.info("Uploading hero image...")
        img_resp = self.upload_hero_image()
        if img_resp.get("error"):
            logger.warning("Error uploading image: %s", img_resp["error"])

        logger.debug("Hero image response: %s", img_resp)
        tarball_path = os.path.join(self.work_dir, "dash_app.tar.gz")

        logger.info("Uploading Dash app bundle and dependencies...")
        upload_resp = upload_files(
            files=[tarball_path],
            study_space_id=self.study_space_id,
            title=self.title,
            input_file_ids=self.input_file_ids,
            input_sample_ids=self.input_sample_ids,
            store=hpu.permanent_store,
            do_prompt=False,
            do_conda_build_check=self.do_conda_build_check,
        )
        logger.debug("Upload response: %s", upload_resp)

        dash_flow_payload = {
            "images": [img_resp["id"]],
        }

        # this will be the path where we mount all of the data
        if self.data_mount_path:
            dash_flow_payload['dataMountPath'] = self.data_mount_path

        # for the case where a user wants to pull in files that are already in HISE
        if self.data_source_file_ids:
            dash_flow_payload["dataSourceFiles"] = self.data_source_file_ids

        dash_workflow_url = hise_url("ide_management",
                                     "dash_workflow",
                                     resource=upload_resp["TraceId"])
        logger.info("Creating Dash workflow: %s", dash_workflow_url)
        resp = requests.post(
            dash_workflow_url,
            json=dash_flow_payload,
            headers=get_bearer_token_header(),
        )
        workflow_resp = parse_hise_response(resp)
        logger.debug("Workflow response: %s", workflow_resp)

        return workflow_resp


@with_default_logging
def get_default_store():
    return IDEInstance().get_default_store()


@with_default_logging
def get_default_project():
    return IDEInstance().get_default_project()


@with_default_logging
def get_study_spaces(to_df: bool = False):
    """ 
    Returns list of studies a user has access to 
    
    Parameters:
        to_df (bool): return a data.frame object if set to True
    """
    resp = parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "study_space_path"),
                         headers=get_bearer_token_header()))
    if to_df:
        return pd.DataFrame(resp)
    else:
        return resp


@with_default_logging
def get_trace(trace_id):
    """ Returns trace object """
    trace = parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "trace_path", trace_id),
                         headers=get_bearer_token_header()))
    if len(trace) == 0:
        raise Exception("Trace id %s is invalid" % trace_id)
    return trace[0]


@with_default_logging
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


@with_default_logging
def retry_ide_commit(id: str):
    if cu.is_legacy_ide():
        raise Exception("Cannot retry commit on a legacy IDE")
    if ide_is_from_guest_account():
        url = guest_hise_server(
            cu.hise_url("ide_management",
                        "upload_file_v3_path",
                        id,
                        args={"condaEnvironmentFile": hpu.do_conda_export()}))
    else:
        url = cu.hise_url("ide_management",
                          "upload_file_v3_path",
                          id,
                          args={"condaEnvironmentFile": hpu.do_conda_export()})
    return cu.parse_hise_response(requests.put(url))


@with_default_logging
def save_visualization_app(
        application_files: list[str],
        application_dirs: list[str],
        study_space_id: str,
        title: str,
        png_image: str,
        data_mount_path: str,
        data_source_file_ids: list[str],
        description: str = '',
        build_template_name: str = '',
        build_template_major_version: int = -1,
        build_template_minor_version: int = -1,
        build_template_parameters: dict[str, str] | None = None,
        infer_build_template_arguments: bool = True) -> dict:
    if len(title) < 10:
        raise RuntimeError('Your title must be at least 10 characters long')
    elif data_mount_path == '':
        raise RuntimeError('A non-empty data_mount_path is required')
    elif len(data_source_file_ids) == 0:
        raise RuntimeError('A non-empty list of data_source_files is required')

    hpu.validate_files(application_files, application_dirs)
    png_image = hpu.validate_hero_image(png_image)
    hpu.get_study_space(study_space_id)
    hpu.validate_upload_input_ids(input_file_ids=data_source_file_ids,
                                  input_sample_ids=[],
                                  ide_dir=CONFIG['STORES']['TEMP_STORE'])

    if not data_mount_path.startswith('/'):
        data_mount_path = '/' + data_mount_path

    vbt = get_build_template(build_template_name, build_template_major_version,
                             build_template_minor_version)

    # enumerate all application files and directories
    all_files = set([os.path.abspath(f) for f in application_files])
    all_dirs = set([os.path.abspath(d) for d in application_dirs])
    for application_dir in list(all_dirs):
        for (dirpath, dirnames, filenames) in os.walk(application_dir):
            all_files.update(
                [os.path.join(dirpath, filename) for filename in filenames])
            all_dirs.update(
                [os.path.join(dirpath, dirname) for dirname in dirnames])

    template_params = {}
    for template_var in vbt['buildVariables']:
        varName = template_var['varName']
        if isinstance(
                build_template_parameters,
                dict) and varName in build_template_parameters and re.search(
                    template_var['matchRegex'],
                    build_template_parameters[varName]):
            template_params[varName] = build_template_parameters[varName]
        else:
            template_params[varName] = get_template_variable(
                template_var, all_files, all_dirs,
                infer_build_template_arguments)

    tmpdirname = tempfile.mkdtemp(dir=CONFIG['STORES']['TEMP_STORE'])
    os.chmod(tmpdirname, 0o777)
    logger.info("Created temporary directory for Visualization App build: %s",
                tmpdirname)

    hpu.create_temp_directory_files(list(all_files), tmpdirname)

    tarfile_path = os.path.join(tmpdirname, "viz_app.tar.gz")
    logger.debug("Creating tarball: %s", tarfile_path)
    with tarfile.open(tarfile_path, "w:gz") as tar:
        tar.add(tmpdirname, arcname="")

    logger.debug("Uploading hero image: %s", png_image)
    img_resp = save_static_image(image=png_image,
                                 title=title,
                                 study_space_id=study_space_id)

    if img_resp.get("error"):
        logger.warning("Error uploading image: %s", img_resp["error"])

    vizapp_workflow_url = hise_url("ide_management", "vizapp_workflow")
    logger.info("Creating Visualization App workflow: %s", vizapp_workflow_url)
    resp = requests.post(vizapp_workflow_url,
                         json={
                             'artifactsFileName': tarfile_path,
                             'dataMountPath': data_mount_path,
                             'dataSourceFileIds': data_source_file_ids,
                             'description': description,
                             'images': [img_resp['id']],
                             'instanceGuid': ide_instance_guid(),
                             'studySpaceId': study_space_id,
                             'title': title,
                             'visualizationBuildTemplateArgs': template_params,
                             'visualizationBuildTemplateId': vbt['id']
                         },
                         headers=get_bearer_token_header())
    return parse_hise_response(resp)


class BuildTemplateVariableType(Enum):
    FILE = 1
    DIRECTORY = 2
    OTHER = 3


def get_template_variable(template_var: dict[str,
                                             Any], application_files: set[str],
                          application_dirs: set[str],
                          infer_build_template_arguments: bool) -> str:
    var_type = BuildTemplateVariableType.OTHER
    if template_var['isPath']:
        var_type = BuildTemplateVariableType.DIRECTORY if template_var[
            'directoryStructure'] is not None else BuildTemplateVariableType.FILE

    match var_type:
        case BuildTemplateVariableType.FILE:
            if infer_build_template_arguments:
                found_file = ''
                for candidate in application_files:
                    if re.search(template_var['matchRegex'], candidate):
                        if found_file == '':
                            found_file = candidate
                        else:
                            found_file = ''
                            break

                if found_file != '':
                    return found_file

            while True:
                user_input = input(
                    f'Please enter {template_var["friendlyName"]}:')
                if user_input == '' and not template_var['required']:
                    return ''
                elif re.search(template_var['matchRegex'],
                               user_input) and os.path.isfile(user_input):
                    user_input_abspath = os.path.abspath(user_input)
                    application_files.add(user_input_abspath)
                    return user_input_abspath
        case BuildTemplateVariableType.DIRECTORY:
            dir_structure = template_var['directoryStructure']
            if infer_build_template_arguments:
                found_dir = ''
                for candidate in application_dirs:
                    if user_included_directory_structure(
                            candidate, dir_structure, application_files,
                            application_dirs):
                        if found_dir == '':
                            found_dir = candidate
                        else:
                            found_dir = ''
                            break

                if found_dir != '':
                    return found_dir

            while True:
                user_input = input(
                    f'Please enter {template_var["friendlyName"]}:')
                if user_input == '' and not template_var['required']:
                    return ''
                elif re.search(template_var['matchRegex'],
                               user_input) and os.path.isdir(user_input):
                    user_input_abspath = os.path.abspath(user_input)
                    if user_included_directory_structure(
                            user_input_abspath, dir_structure):
                        # Include files in all subdirectories of the directory that the user gave us in our list of
                        # files that we will upload for this visualization app
                        for (dirpath, dirnames,
                             filenames) in os.walk(user_input_abspath):
                            application_dirs.update([
                                os.path.join(dirpath, dirname)
                                for dirname in dirnames
                            ])
                            application_files.update([
                                os.path.join(dirpath, filename)
                                for filename in filenames
                            ])
                        return user_input_abspath
        case BuildTemplateVariableType.OTHER:
            while True:
                user_input = input(
                    f'Please enter {template_var["friendlyName"]}:')
                if user_input == '' and not template_var['required']:
                    return ''
                elif re.search(template_var['matchRegex'], user_input):
                    return user_input
    raise RuntimeError(f'impossible BuildTemplateVariableType {var_type}')


def user_included_directory_structure(
        user_dir: str,
        dir_structure: dict,
        included_files: set[str] | None = None,
        included_dirs: set[str] | None = None) -> bool:
    if operator.xor(included_files is None, included_dirs is None):
        raise RuntimeError(
            'either both files and dirs must be included or neither files nor dirs can be included'
        )

    dirs = set([])
    files = set([])
    if included_dirs is not None and included_files is not None:
        dirs = included_dirs
        files = included_files
    else:
        for (dirpath, dirnames, filenames) in os.walk(user_dir):
            dirs = set(
                [os.path.join(dirpath, dirname) for dirname in dirnames])
            files = set(
                [os.path.join(dirpath, filename) for filename in filenames])
            break

    for name, val in dir_structure.items():
        if isinstance(val, dict):
            dirname = os.path.join(user_dir, name)
            if not dirname in dirs or not user_included_directory_structure(
                    dirname, val, included_files, included_dirs):
                return False
        elif isinstance(val, str):
            # Do we have a file with this exact name?
            if val == '':
                return os.path.join(user_dir, name) in files

            # Do we have a file that matches this regex?
            if not any(re.search(val, file) for file in files):
                return False
    return True


def get_build_template(build_template_name: str,
                       build_template_major_version: int,
                       build_template_minor_version: int):
    templates = get_build_templates(build_template_name,
                                    build_template_major_version,
                                    build_template_minor_version)
    if len(templates) == 1:
        return templates[0]
    elif len(templates) == 0:
        raise RuntimeError(
            'No visualization templates found with name %s version %s.%s' % (
                build_template_name,
                '*' if build_template_major_version < 0 else
                build_template_major_version,
                '*' if build_template_minor_version < 0 else
                build_template_minor_version,
            ))

    template_df = pd.DataFrame({
        'Name': [vbt['name'] for vbt in templates],
        'Version': [vbt['githubLink'] for vbt in templates],
        'Description': [vbt['description'] for vbt in templates]
    })

    # Define the function to create a clickable HTML link in a DataFrame
    def make_clickable(val):
        # target="_blank" ensures the link opens in a new window/tab
        # The last element of the Github URL is the version of the Visualization Build Template
        return '<a target="_blank" href="%s">%s</a>' % (val,
                                                        val.split('/')[-1])

    styled_df = template_df.style.format(formatter={'Version': make_clickable})
    print('The following Visualization Build Templates are available:')
    display(HTML(styled_df.to_html()))

    prompt = 'Enter the index of your desired template. Possible values range from 0 to %d' % (
        len(templates) - 1)
    user_choice = -1
    while not 0 <= user_choice < len(templates):
        try:
            user_choice = int(input(prompt))
        except ValueError:
            user_choice = -1
    return templates[user_choice]


def get_build_templates(build_template_name: str,
                        build_template_major_version: int,
                        build_template_minor_version: int) -> list:
    query_filter = {}
    query_filter["deprecated"] = "false"
    if build_template_name != "":
        query_filter["name"] = build_template_name
        if build_template_major_version >= 0:
            query_filter["version.major"] = build_template_major_version
            if build_template_minor_version >= 0:
                query_filter["version.minor"] = build_template_minor_version
                del query_filter[
                    "deprecated"]  # they specified the exact template; include deprecated ones

    resp = cu.requests.post(url=hise_url("tracer",
                                         "visualization_build_template",
                                         "filter"),
                            headers=get_bearer_token_header(),
                            json={"Filter": query_filter})
    return resp.json()


@with_default_logging
def save_dash_app(app_filepath: str,
                  additional_files: list[str],
                  additional_dirs: list[str],
                  input_file_ids: list[str],
                  study_space_id: str,
                  title: str,
                  description: str | None = None,
                  image: str | None = None,
                  requirements: str | None = None,
                  input_sample_ids: list[str] | None = None,
                  do_conda_build_check: bool = True,
                  data_mount_path: str | None = None,
                  data_source_file_ids: list[str] | None = None) -> dict:
    """
    Given a Dash app consisting of an entry point named `app.py` and a list of supporting files, upload and deploy that
    app to HISE as a visualization in the given study space.

    Parameters:
        app_filepath (str): path to file named app.py that serves your Dash app
            (i.e., ends with `app.run_server(host='0.0.0.0')`)
        additional_files (list): list of additional files used by your app (e.g., custom CSS).
            Only files under /home/jupyter can be included.
        additional_dirs (list): list of additional directories for your app. 
            Directories specified are for configs, or additional scripts, not input data.
        input_file_ids (list): list of HISE file UUIDs that this app visualizes
        study_space_id (str): UUID of study space to save app to
        title (str): a 10+ character title for the app
        description (str): description of app being uploaded
        image (str): png thumbnail image for app in study space
        input_sample_ids (list): list of samples UUIDs that this app visualizes
        data_mount_path (str): path of directory where input datasets should be read from 
        data_source_file_ids list[str] : file IDs in HISE of input data to a dash app 
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
    input_sample_ids = input_sample_ids or []

    # validation on kernel
    if not cu.is_valid_upload_kernel():
        raise RuntimeError(CONFIG['PROMPTS']['INVALID_UPLOAD_KERNEL'])

    hpu.validate_app_path(app_filepath)
    hpu.validate_files(additional_files)
    hpu.validate_hero_image(image)

    log_dir = CONFIG['STORES']['TEMP_STORE'] if not cu.is_legacy_ide(
    ) else IDE_HOME_DIR
    if not debug():
        hpu.validate_upload_input_ids(input_file_ids, input_sample_ids,
                                      log_dir)

    # validate environment can build
    global save_dash_conda_env_checked
    if not save_dash_conda_env_checked:
        if do_conda_build_check and not conda_env_builds():
            raise SystemError(CONFIG['PROMPTS']['CONDA_ENV_BUILD'])
        save_dash_conda_env_checked = True

    home_dir_prefix = CONFIG['IDE']['HOME_DIR_V2'] if not cu.is_legacy_ide(
    ) else IDE_HOME_DIR
    tmpdirname = tempfile.mkdtemp(prefix=f"{home_dir_prefix}/")
    os.chmod(tmpdirname, 0o777)

    logger.info("Created temporary directory for Dash app build: %s",
                tmpdirname)

    try:
        dash_app = DashAppImg(app_filepath=app_filepath,
                              additional_files=additional_files,
                              additional_dirs=additional_dirs,
                              hero_image=image,
                              study_space_id=study_space_id,
                              input_file_ids=input_file_ids,
                              title=title,
                              description=description,
                              requirements=requirements,
                              input_sample_ids=input_sample_ids,
                              work_dir=tmpdirname,
                              do_conda_build_check=False,
                              data_mount_path=data_mount_path,
                              data_source_file_ids=data_source_file_ids)

        # Copy files and prepare build context
        all_files = dash_app.filepaths.union({dash_app.app_filepath
                                              }).union(dash_app.directories)
        hpu.create_temp_directory_files(list(all_files), tmpdirname)

        dash_app.create_requirements_file()
        tarball_path = dash_app.create_dash_tarball()

        logger.info("Dash app packaged at: %s", tarball_path)

        resp = dash_app.export()
        logger.extra["_override"]['workflow'] = resp[
            'WorkflowId']  #attach workflow to log entry
        logger.info("Dash app successfully uploaded and deployed.")
        return resp
    except:
        raise Exception("Failed to deploy dash app")


@with_default_logging
def save_visualization(pl_obj: plotly.graph_objs.Figure,
                       study_space_id: str | None = None,
                       project: str | None = None,
                       title: str | None = None,
                       destination: str | None = None,
                       input_file_ids: list[str] | None = None,
                       input_sample_ids: list[str] | None = None,
                       do_conda_build_check: bool = True) -> dict:
    """
    Save a plotly figure to a user's specified study.

    Parameters:
        pl_obj (plotly.Figure): Plotly figure object to save.
        study_space_id (str, optional): UUID of study to save visualization to.
        project (str, optional): Project short name to associate with visualization.
        title (str, optional): Title (≥10 chars) for the visualization.
        destination (str, optional): Destination folder for upload.
        input_file_ids (list[str], optional): File IDs used to generate visualization.
        input_sample_ids (list[str], optional): Sample IDs used to generate visualization.
        do_conda_build_check (bool): Whether to verify conda build integrity.

    Returns:
        dict: Upload result with keys ["trace_id", "files"].
    """
    # validate inputs
    if not isinstance(pl_obj, plotly.graph_objs.Figure):
        raise TypeError("pl_obj must be a valid plotly.Figure instance.")
    if title and len(title) < 10:
        raise ValueError(
            "Visualization title must be at least 10 characters long.")

    input_file_ids = input_file_ids or []
    input_sample_ids = input_sample_ids or []
    destination = destination or ""

    # kernel check
    if not cu.is_valid_upload_kernel():
        raise RuntimeError(CONFIG['PROMPTS']['INVALID_UPLOAD_KERNEL'])

    # construct file paths
    temp_store = CONFIG['STORES']['TEMP_STORE']
    tmp_data_file = os.path.join(temp_store,
                                 CONFIG['VISUALIZATION']['PLOTLY_DATA_FILE'])
    tmp_plotly_file = os.path.join(temp_store,
                                   CONFIG['VISUALIZATION']['PLOTLY_FILE'])
    tmp_img_file = os.path.join(temp_store,
                                CONFIG['VISUALIZATION']['PLOTLY_IMAGE_FILE'])
    log_dir = IDE_HOME_DIR if cu.is_legacy_ide() else temp_store

    # save figure image
    pl_obj.write_image(tmp_img_file)

    # validate upload ids
    hpu.validate_upload_input_ids(input_file_ids, input_sample_ids, log_dir)

    # conda environment validation
    global save_visualization_conda_env_checked
    if not auth.debug() and not save_visualization_conda_env_checked:
        if do_conda_build_check and not conda_env_builds():
            raise SystemError(CONFIG['PROMPTS']['CONDA_ENV_BUILD'])
        save_visualization_conda_env_checked = True

    # save static image
    args = {}
    if study_space_id:
        img_data = save_static_image(image=tmp_img_file,
                                     title=title,
                                     study_space_id=study_space_id)
        if img_data:
            args["images"] = img_data["id"]
    else:
        print("No study_space_id provided; static image will not be saved.")
        args["project"] = project

    # clean up tmp image
    if os.path.exists(tmp_img_file):
        os.remove(tmp_img_file)

    # serialize figure data
    exp_obj = json.loads(pl_obj.to_json())
    with open(tmp_data_file, "w", encoding="utf-8") as f:
        json.dump(exp_obj["data"], f)

    # upload data
    upload_result = upload_files(
        files=[tmp_data_file],
        study_space_id=study_space_id,
        project=project,
        title=title,
        input_file_ids=input_file_ids,
        input_sample_ids=input_sample_ids,
        file_types=[dataframe_file_type],
        store=hpu.permanent_store,
        destination=destination,
        do_prompt=False,
        do_conda_build_check=do_conda_build_check,
    )
    args["traceId"] = upload_result["TraceId"]

    # save layout
    exp_obj["data"] = []
    with open(tmp_plotly_file, "w", encoding="utf-8") as f:
        json.dump(exp_obj, f)

    # upload viz json
    vis_dict = {
        "file": (
            tmp_plotly_file,
            open(tmp_plotly_file, "rb"),
            "application/json",
            {
                "Expires": "0"
            },
        )
    }

    try:
        url = hise_url("toolchain", "visualization_path", "json", args=args)
        response = requests.post(url,
                                 headers=get_bearer_token_header(),
                                 files=vis_dict)
        parse_hise_response(response)
    finally:
        # ensure temporary cleanup even if upload fails
        cu.safe_remove(tmp_data_file)
        cu.safe_remove(tmp_plotly_file)
        vis_dict["file"][1].close()

    return upload_result


@with_default_logging
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
    hpu.validate_upload_data(files=[image],
                             study_space_id=study_space_id,
                             project=None,
                             title=title,
                             input_file_ids=["not a file"])
    args = {"studySpaceId": study_space_id, "title": title}
    return parse_hise_response(
        requests.post(hise_url("hydration", "upload_path", args=args),
                      headers=get_bearer_token_header(),
                      files=img_dict))


@with_default_logging
def set_default_project(project=None):
    return IDEInstance().set_default_project(project)


@with_default_logging
def set_default_store(store=None):
    return IDEInstance().set_default_store(store)


@with_default_logging
def upload_files(files: list,
                 study_space_id: str = None,
                 project: str | None = None,
                 title: str | None = None,
                 input_file_ids: list[str] | None = None,
                 input_sample_ids: list[str] | None = None,
                 file_types: list[str] | None = None,
                 store: str | None = None,
                 destination: str = "",
                 do_prompt: bool = True,
                 do_conda_build_check: bool = True,
                 use_fast_mode: bool | None = None):
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
        do_conda_build_check (bool): If true, create and build the active Conda environment.
        use_fast_mode (bool): If true, speed up the upload flow by skipping the step that builds the IDE environment.
    Returns:
        dictionary with keys ["trace_id", "files", "workflowId", "fileIds", processId"]
    Example:
        hp.upload_files(files=['/home/jupyter/upload_file.csv'],
                        study_space_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                        title='a upload title',
                        input_file_ids=['9f6d7ab5-1c7b-4709-9455-3d8ffffbb6c8'])
    """
    # override logEntry to denote fast_mode was used
    if use_fast_mode:
        logger.info("user has chosen fast_mode for upload_files")
        logger.extra["_override"]['method_name'] = "upload_files_fast_mode"

    # validations
    hpu.validate_upload_context()
    hpu.validate_upload_parameters(
        files=files,
        file_types=file_types,
        destination=destination,
        store=store,
        project=project,
        study_space_id=study_space_id,
        do_prompt=do_prompt,
    )

    # setup
    inst = IDEInstance()
    home_dir, file_log_dir = hpu.get_workspace_dirs()
    study_space_id, project, input_sample_ids = hpu.resolve_upload_context(
        study_space_id, project, input_sample_ids, do_prompt)

    if ide_is_from_guest_account():
        input_file_ids = cu.replica_files_used(input_file_ids or [],
                                               file_log_dir)
    hpu.validate_upload_input_ids(input_file_ids, input_sample_ids,
                                  file_log_dir)
    hpu.validate_upload_data(files, study_space_id, project, title,
                             file_log_dir)

    # build payload
    tmpdir = tempfile.mkdtemp(dir='/home/workspace/temp', prefix="env_export_")
    qargs = hpu.build_upload_payload(
        files=files,
        file_types=file_types,
        title=title,
        store=store or get_default_store(),
        destination=destination,
        project=project,
        study_space_id=study_space_id,
        input_file_ids=input_file_ids or [],
        input_sample_ids=input_sample_ids or [],
        home_dir=home_dir,
        inst=inst,
    )

    # get conda pack to determine whether to use pixi or conda
    package_manager = cu.get_ide_package_manager()
    qargs['packageManager'] = package_manager
    if not cu.is_legacy_ide():
        if package_manager == "conda":
            qargs["condaEnvironmentFile"] = hpu.do_conda_export(tmpdir)
        elif package_manager == "pixi":
            qargs["condaEnvironmentFile"] = hpu.do_pixi_export(tmpdir)

            # copy over additional files to temp dir
            wheel_dir = get_pixi_env_dir() / "python-packages"
            wheel_files = list(wheel_dir.glob("*.whl"))
            if wheel_files:
                logger.info(
                    "Copying additional package files to temp directory for upload..."
                )
                additional_packages = []
                for wheel in wheel_files:
                    shutil.copy2(wheel, Path(tmpdir) / wheel.name)
                    additional_packages.append(Path(tmpdir) / wheel.name)
                qargs['additionalPackages'] = [
                    str(p) for p in additional_packages
                ]

        else:
            raise SystemError(f"{package_manager} is not supported")
    # only use fast_mode if the user made the call from upload_files_fast_mode
    if use_fast_mode:
        if cu.prompt_yn(CONFIG['PROMPTS']['FAST_MODE_UPLOAD']):
            qargs['useFastMode'] = True

    global upload_files_conda_env_checked
    if not upload_files_conda_env_checked:
        if not use_fast_mode and package_manager == "conda":  # check the conda environment if user isn't not running fast_mode
            hpu.ensure_conda_env_ready(do_conda_build_check)
            upload_files_conda_env_checked = True

    # upload thy files
    url = hpu.get_upload_url()
    try:
        resp = cu.parse_hise_response(
            requests.post(url, json=qargs, headers=get_bearer_token_header()))
        logger.extra["_override"]['workflow'] = resp['WorkflowId']
        return resp
    except requests.RequestException as e:
        raise RuntimeError(f"Upload request failed: {e}") from e
