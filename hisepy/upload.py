import json
import os
import pandas as pd
import plotly
import plotly.graph_objects as go
import requests
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

import hisepy.upload_utils as hpu
from hisepy.common_utils import get_filetype, get_ide_package_manager, hise_url, is_legacy_ide, is_valid_upload_kernel, parse_hise_response, prompt_yn, read_yaml, replica_files_used, safe_remove
from hisepy.auth import get_bearer_token_header, IDEInstance, debug, ide_instance_guid, ide_is_from_guest_account, guest_hise_server
from hisepy.utils import conda_env_builds
from hisepy.logging import with_default_logging, logger
from hisepy.pixi_pack import get_pixi_env_dir
from hisepy.viz_utils import create_visualization_tarball, enumerate_all_files, get_build_template_and_params

dataframe_file_type = "Visualization-dataframe"
upload_files_conda_env_checked = False
save_dash_conda_env_checked = False
save_visualization_conda_env_checked = False

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = read_yaml('{}/config.yaml'.format(_here))
IDE_HOME_DIR = CONFIG['IDE']['HOME_DIR'] if not debug() else os.getcwd()
UPLOAD_HARVEST_LOWER_BOUND = CONFIG['TOOLCHAIN'][
    'UPLOAD_HARVEST_LOWER_BOUND_MB']
TMP_DIR = '/home/workspace/temp'
if debug():
    TMP_DIR = "/tmp"


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
        upload_resp = upload_files_internal(
            files=[{
                hpu.file_key: tarball_path,
                hpu.file_sample_id_key: self.input_sample_ids
            }],
            study_space_id=self.study_space_id,
            title=self.title,
            input_file_ids=self.input_file_ids,
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
    if is_legacy_ide():
        raise Exception("Cannot retry commit on a legacy IDE")
    if ide_is_from_guest_account():
        url = guest_hise_server(
            hise_url("ide_management",
                     "upload_file_v3_path",
                     id,
                     args={"condaEnvironmentFile": hpu.do_conda_export()[0]}))
    else:
        url = hise_url("ide_management",
                       "upload_file_v3_path",
                       id,
                       args={"condaEnvironmentFile": hpu.do_conda_export()[0]})
    return parse_hise_response(requests.put(url))


@with_default_logging
def save_visualization_app(application_files: list[str],
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
                           build_template_parameters: dict[str, str]
                           | None = None,
                           infer_build_template_arguments: bool = True) -> str:
    """
    Given an app supported by HISE Visualization Build Templates, upload and deploy that
    app to HISE as a visualization in the given study space.

    Parameters:
        application_files (list): list of individual files used by your app (e.g., custom CSS).
            Only files under /home/workspace can be included.
        application_dirs (list): list of directories used by your app. 
            Directories specified are for configs or scripts, not input data.
            Only directories under /home/workspace can be included.
        study_space_id (str): UUID of study space to save app to
        title (str): a 10+ character title for the app
        png_image (str): png thumbnail image for app in study space
        data_mount_path (str): path of directory where input datasets should be read from 
        data_source_file_ids list[str] : file IDs in HISE of input data to your app
        description (str): description of app being uploaded
        build_template_name (str): the name of the HISE Visualization Build Template framework
            (i.e. dash, deckgl), if known in advance
        build_template_major_version (int): the major version number of the desired 
            HISE Visualization Build Template framework, if known in advance
        build_template_major_version (int): the minor version number of the desired 
            HISE Visualization Build Template framework, if known in advance
        build_template_parameters (dict[str, str]): the framework-specific arguments required by the
            HISE Visualization Build Template, if known in advance
        infer_build_template_arguments (bool): flag for whether this method should try to infer paths
            for HISE Visualization Build Template arguments
    Returns:
        Response from server
    Example:
        hisepy.save_visualization_app(application_files=['dash_app/app.py'],
                            application_dirs=['data'],
                            study_space_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                            title="Hello world Dash app",
                            png_image="dash_app/thumbnail.png",
                            data_mount_path='/my_mount_path'
                            data_source_file_ids=['9f6d7ab5-1c7b-4709-9455-3d8ffffbb6c8','0fb06e51-74c4-46be-b92d-5e045232b2d9'],
                            description="An amazingly complex data visualization")
    """
    title = title.strip()
    if len(title) < 10:
        raise RuntimeError('Your title must be at least 10 characters long')
    elif len(data_source_file_ids) == 0:
        raise RuntimeError('A non-empty list of data_source_files is required')

    data_mount_path = data_mount_path.strip().rstrip('/')
    if data_mount_path == '':
        raise RuntimeError('A non-empty data_mount_path is required')
    elif not data_mount_path.startswith('/'):
        data_mount_path = '/' + data_mount_path

    hpu.validate_files(application_files, application_dirs)
    png_image = hpu.validate_hero_image(png_image)
    hpu.get_study_space(study_space_id)
    hpu.validate_upload_input_ids(input_file_ids=data_source_file_ids,
                                  files=[],
                                  ide_dir=CONFIG['STORES']['TEMP_STORE'])

    all_files = enumerate_all_files(application_files, application_dirs)
    validate_data_mount_path(data_mount_path, all_files)
    vbt, template_params = get_build_template_and_params(
        build_template_name, build_template_major_version,
        build_template_minor_version, all_files, build_template_parameters
        or {}, infer_build_template_arguments)
    tarfile_path = create_visualization_tarball(CONFIG, list(all_files))

    logger.debug('Uploading hero image: %s', png_image)
    img_resp = save_static_image(image=png_image,
                                 title=title,
                                 study_space_id=study_space_id)

    if img_resp.get('error'):
        logger.warning('Error uploading image: %s', img_resp['error'])

    vizapp_workflow_url = hise_url('ide_management', 'vizapp_workflow')
    logger.info('Creating Visualization App workflow: %s', vizapp_workflow_url)
    resp = parse_hise_response(
        requests.post(vizapp_workflow_url,
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
                      headers=get_bearer_token_header()))
    workflowId = resp['WorkflowId']
    logger.extra['_override']['workflow'] = workflowId
    return 'Visualization App Workflow initiated: %s' % (hise_url(
        'workflow', 'ui_path', workflowId))


def validate_data_mount_path(data_mount_path: str, files: set[str]):
    for f in files:
        f_path = f.rstrip('/')
        if f_path == data_mount_path or f_path.startswith(data_mount_path +
                                                          '/'):
            raise ValueError(
                f'data_mount_path "{data_mount_path}" will overwrite application file "{f}". Please choose a different data_mount_path.'
            )


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
    if not is_valid_upload_kernel():
        raise RuntimeError(CONFIG['PROMPTS']['INVALID_UPLOAD_KERNEL'])

    hpu.validate_app_path(app_filepath)
    hpu.validate_files(additional_files)
    hpu.validate_hero_image(image)

    log_dir = CONFIG['STORES']['TEMP_STORE'] if not is_legacy_ide(
    ) else IDE_HOME_DIR
    hpu.validate_upload_input_ids(input_file_ids, [], log_dir)

    # validate environment can build
    global save_dash_conda_env_checked
    if not save_dash_conda_env_checked:
        if do_conda_build_check and not conda_env_builds():
            raise SystemError(CONFIG['PROMPTS']['CONDA_ENV_BUILD'])
        save_dash_conda_env_checked = True

    home_dir_prefix = CONFIG['IDE']['HOME_DIR_V2'] if not is_legacy_ide(
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
    if not is_valid_upload_kernel():
        raise RuntimeError(CONFIG['PROMPTS']['INVALID_UPLOAD_KERNEL'])

    # construct file paths
    temp_store = CONFIG['STORES']['TEMP_STORE']
    tmp_data_file = os.path.join(temp_store,
                                 CONFIG['VISUALIZATION']['PLOTLY_DATA_FILE'])
    tmp_plotly_file = os.path.join(temp_store,
                                   CONFIG['VISUALIZATION']['PLOTLY_FILE'])
    tmp_img_file = os.path.join(temp_store,
                                CONFIG['VISUALIZATION']['PLOTLY_IMAGE_FILE'])
    log_dir = IDE_HOME_DIR if is_legacy_ide() else temp_store

    # save figure image
    pl_obj.write_image(tmp_img_file)

    # validate upload ids
    # mock up files to check samples
    mock_files = [{hpc.file_sample_id_key: i} for i in input_sample_ids]
    hpu.validate_upload_input_ids(input_file_ids, mock_files, log_dir)

    # conda environment validation
    global save_visualization_conda_env_checked
    if not debug() and not save_visualization_conda_env_checked:
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
    upload_result = upload_files_internal(
        files=[{
            hpu.file_key: tmp_data_file,
            hpu.file_sample_id_key: input_sample_ids,
            hpu.file_type_key: dataframe_file_type
        }],
        study_space_id=study_space_id,
        project=project,
        title=title,
        input_file_ids=input_file_ids,
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
        safe_remove(tmp_data_file)
        safe_remove(tmp_plotly_file)
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

    hpu.validate_upload_data(files=[{
        "file": image
    }],
                             study_space_id=study_space_id,
                             project=None,
                             title=title,
                             input_file_ids=["not a file"])

    args = {"studySpaceId": study_space_id, "title": title}
    with open(image, 'rb') as image_file:
        return parse_hise_response(
            requests.post(hise_url("hydration", "upload_path", args=args),
                          headers=get_bearer_token_header(),
                          files={
                              'bytes': (image, image_file,
                                        "image/%s" % (get_filetype(image)))
                          }))


@with_default_logging
def set_default_project(project=None):
    return IDEInstance().set_default_project(project)


@with_default_logging
def set_default_store(store=None):
    return IDEInstance().set_default_store(store)


@with_default_logging
def upload_files(
    files: list,
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
    use_fast_mode: bool | None = None,
    no_file_set: bool = False,
    directory: str | None = None,
    file_type_map: dict | None = None,
):
    """
    Uploads files to a store and records their provenance in HISE, but V3

    Parameters:
        files (list): absolute filepath of file to be uploaded
        study_space_id (str): ID that pertains to a study in the collaboration space (optional)
        project (str): project short name (required if study space is not specified, defaults to the ide's default setting
        title (str): 10+ character title for upload result
        input_file_ids (list): fileIds from HISE that were utilized to generate a user's result
        input_sample_ids (list): sampleIds from HISE that were utilized to generate a user's result
        file_types (list): filetype of uploaded files. If specified, list must be same length as files list and
            filetypes will be associated in order. If not specified, filetypes will be inferred based on file
            extension. Mutually exclusive with file_type_map. Cannot be used with directory.
        store (str): Which store ('project' or 'permanent') to use for the files, defaults to the ide's setting
        destination (str): Destination folder for the files
        do_prompt (bool): whether or not to prompt for user's input, asking to proceed.
        do_conda_build_check (bool): If true, create and build the active Conda environment.
        use_fast_mode (bool): If true, speed up the upload flow by skipping the step that builds the IDE environment.
        no_file_set (bool): If true, skip the automatic creation of a fileset for the uploaded files
        directory (str): Path to a directory whose files will be added to the upload. The fully qualified directory
            path is also forwarded to the service. Cannot be used with file_types.
        file_type_map (dict): Mapping of file extension to file type (e.g. {"csv": "flow-cytometry-analysis", "txt": "txt#derived"}).
            For each uploaded file the extension is looked up in this map and, if found, assigned as the file
            type. Mutually exclusive with file_types.
    Returns:
        dictionary with keys ["trace_id", "files", "workflowId", "fileIds", processId"]
    Example:
        hp.upload_files(files=['/home/jupyter/upload_file.csv'],
                        study_space_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                        title='a upload title',
                        input_file_ids=['9f6d7ab5-1c7b-4709-9455-3d8ffffbb6c8'])

        hp.upload_files(directory='/home/jupyter/results',
                        file_type_map={'csv': 'CSV', 'txt': 'Text'},
                        study_space_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                        title='a upload title')
    """
    if file_types is not None and file_type_map is not None:
        raise ValueError(
            "Specify either file_types or file_type_map, not both.")
    if directory is not None and file_types is not None:
        raise ValueError(
            "Cannot use file_types with directory; file_types maps 1:1 to an explicit files list."
        )

    files = list(files)
    abs_directory = None
    if directory is not None:
        abs_directory = os.path.abspath(directory)
        dir_files = sorted(
            os.path.join(root, name)
            for root, _, names in os.walk(abs_directory) for name in names)
        files = files + dir_files

    file_map = []
    for i, file in enumerate(files):
        f = {hpu.file_key: file, hpu.file_sample_id_key: input_sample_ids}
        if file_types is not None and len(file_types) > i:
            f[hpu.file_type_key] = file_types[i]
        elif file_type_map is not None:
            ext = os.path.splitext(file)[1].lstrip('.')
            if ext in file_type_map:
                f[hpu.file_type_key] = file_type_map[ext]
        file_map.append(f)

    return upload_files_internal(files=file_map,
                                 study_space_id=study_space_id,
                                 project=project,
                                 title=title,
                                 input_file_ids=input_file_ids,
                                 store=store,
                                 destination=destination,
                                 do_prompt=do_prompt,
                                 do_conda_build_check=do_conda_build_check,
                                 use_fast_mode=use_fast_mode,
                                 no_file_set=no_file_set,
                                 directory=abs_directory)


@with_default_logging
def upload_file_map(files: list,
                    study_space_id: str = None,
                    project: str | None = None,
                    title: str | None = None,
                    input_file_ids: list[str] | None = None,
                    store: str | None = None,
                    destination: str = "",
                    do_prompt: bool = True,
                    do_conda_build_check: bool = True,
                    use_fast_mode: bool | None = None,
                    no_file_set: bool = False):
    """
    Uploads files to a store and records their provenance in HISE, but V3

    Parameters:
        files (list): a list of dictionary objects containing the following fields:
                      file: absolute filepath of file to be uploaded
                      file_type: (optional, can be inferred) the result file type of the file
                      input_sample_ids: optional list of input sample guids
        study_space_id (str): ID that pertains to a study in the collaboration space (optional)
        project (str): project short name (required if study space is not specified, defaults to the ide's default setting
        title (str): 10+ character title for upload result
        input_file_ids (list): fileIds from HISE that were utilized to generate a user's result
        store (str): Which store ('project' or 'permanent') to use for the files, defaults to the ide's setting
        destination (str): Destination folder for the files
        do_prompt (bool): whether or not to prompt for user's input, asking to proceed.
        do_conda_build_check (bool): If true, create and build the active Conda environment.
        use_fast_mode (bool): If true, speed up the upload flow by skipping the step that builds the IDE environment.
        no_file_set (bool): If true, skip the automatic creation of a fileset for the uploaded files    
    Returns:
        dictionary with keys ["trace_id", "files", "workflowId", "fileIds", processId"]
    Example:
        hp.upload_file_map(files=[{"file": '/home/jupyter/upload_file.csv',
                                   "file_type": "csv",
                                   "input_sample_ids": ["a1a03ecb-5a1d-4995-8db9-56bd18a36247"]}],
                        study_space_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                        title='an upload title',
                        input_file_ids=['9f6d7ab5-1c7b-4709-9455-3d8ffffbb6c8'])
    """
    return upload_files_internal(files=files,
                                 study_space_id=study_space_id,
                                 project=project,
                                 title=title,
                                 input_file_ids=input_file_ids,
                                 store=store,
                                 destination=destination,
                                 do_prompt=do_prompt,
                                 do_conda_build_check=do_conda_build_check,
                                 use_fast_mode=use_fast_mode,
                                 no_file_set=no_file_set)


@with_default_logging
def upload_files_internal(files: list,
                          study_space_id: str = None,
                          project: str | None = None,
                          title: str | None = None,
                          input_file_ids: list[str] | None = None,
                          store: str | None = None,
                          destination: str = "",
                          do_prompt: bool = True,
                          do_conda_build_check: bool = True,
                          use_fast_mode: bool | None = None,
                          no_file_set: bool | None = None,
                          directory: str | None = None):

    # override logEntry to denote fast_mode was used
    if use_fast_mode:
        logger.info("user has chosen fast_mode for upload_files")
        logger.extra["_override"]['method_name'] = "upload_files_fast_mode"
    # validations
    hpu.validate_upload_context()
    hpu.validate_upload_parameters(
        files=files,
        destination=destination,
        store=store,
        project=project,
        study_space_id=study_space_id,
        do_prompt=do_prompt,
    )
    # setup
    inst = IDEInstance()
    home_dir, file_log_dir = hpu.get_workspace_dirs()
    study_space_id, project = hpu.resolve_upload_context(
        study_space_id, project, files, do_prompt)

    if ide_is_from_guest_account():
        input_file_ids = replica_files_used(input_file_ids or [], file_log_dir)
    hpu.validate_upload_input_ids(input_file_ids, files, file_log_dir)
    hpu.validate_upload_data(files, study_space_id, project, title,
                             file_log_dir)

    # build payload
    tmpdir = tempfile.mkdtemp(dir=TMP_DIR, prefix="env_export_")
    qargs = hpu.build_upload_payload(files=files,
                                     title=title,
                                     store=store or get_default_store(),
                                     destination=destination,
                                     project=project,
                                     study_space_id=study_space_id,
                                     input_file_ids=input_file_ids or [],
                                     home_dir=home_dir,
                                     inst=inst,
                                     no_file_set=no_file_set,
                                     directory=directory)

    # get conda pack to determine whether to use pixi or conda
    package_manager = get_ide_package_manager()
    qargs['packageManager'] = package_manager
    if not is_legacy_ide():
        if package_manager == "conda":
            conda_export_info = hpu.do_conda_export(tmpdir)
            qargs["condaEnvironmentFile"] = conda_export_info[0]
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
        if prompt_yn(CONFIG['PROMPTS']['FAST_MODE_UPLOAD']):
            qargs['useFastMode'] = True
        else:
            logger.info(
                "User declined to use fast_mode after prompt; canceling upload_files call."
            )
            return

    global upload_files_conda_env_checked
    if not upload_files_conda_env_checked:
        if not use_fast_mode and package_manager == "conda":  # check the conda environment if user isn't not running fast_mode
            hpu.ensure_conda_env_ready(do_conda_build_check,
                                       conda_export_info[1])
            upload_files_conda_env_checked = True

    # upload thy files
    url = hpu.get_upload_url()
    try:
        resp = parse_hise_response(
            requests.post(url, json=qargs, headers=get_bearer_token_header()))
        logger.extra["_override"]['workflow'] = resp['WorkflowId']
        return resp
    except requests.RequestException as e:
        raise RuntimeError(f"Upload request failed: {e}") from e
