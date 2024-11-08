import json
import os
import requests
import tempfile
import tarfile
import shutil
import pathlib as pl
import hisepy.common_utils as cu
import hisepy.upload as cup
import hisepy.auth as auth
from hisepy.auth import get_bearer_token_header, IDEInstance, debug
import pandas as pd

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))
IDE_HOME_DIR = CONFIG['IDE']['HOME_DIR'] if not debug() else os.getcwd()
any_project_urn = "urn:hise:project:any"


def get_result_files(to_df=True):
    """ 
    Returns available result files for the user's current account/projects.
    The object returned will be a json object, or a data.frame.

    Parameters: 
        to_df (bool) : boolean, where if true, output will be a data.frame. Otherwise, 
        the object returned will be a json response. 

    """
    keep_cols = [
        'id', 'fileType', 'friendlyName', 'description', 'projectGuid',
        'isSearchable'
    ]
    resp = cu.parse_hise_response(
        requests.get(cu.hise_url("ledger", "result_file_search_path"),
                     headers=get_bearer_token_header()))
    if to_df:
        result_df = result_json_to_df(resp)
        return result_df[keep_cols]
    else:
        return resp


def result_json_to_df(json_obj):
    '''
    flatten nested structure of a JSON object and creates a data.frame 
    '''
    agg_df = pd.DataFrame()
    for o in json_obj:
        agg_df = pd.concat([agg_df, pd.json_normalize(o)])
    return agg_df


def user_prompt_select_result(rf_df: pd.DataFrame, filetype):
    """
    Prompt user to select resultFile.fileType of interest
    """
    # determine number of possibilities
    num_dups = len(rf_df)
    input_range = list(range(num_dups))

    # prompt user
    msg = "filetype {f} contains more than 1 entry. Please select one out of the following data.frame: ".format(
        f=filetype)
    print(msg)
    print(rf_df)
    user_input = input(
        "Enter entry index of interest. Possible values to enter are {}: ".
        format(input_range))

    # no escaping unless you choose a valid value
    while int(user_input) not in input_range:
        print("please enter a value from the following list: {}".format(
            input_range))
        user_input = input()

    return rf_df.loc[int(user_input), 'id']


def result_filetype_to_guid(filetype: str, proj_guid):
    ''' 
    Given a ResultFile.fileType, return the corresponding resultFile.ID
    '''

    # get all the resultFiles and concat
    agg_df = get_result_files()

    # check that the result file exists for the chosen project, or if the project is set to "urn:hise:project:any"
    results_in_proj_df = agg_df.loc[
        agg_df['projectGuid'].isin([proj_guid, any_project_urn]), ]
    if filetype not in results_in_proj_df[['fileType']].values:
        raise ValueError(
            "%s is not a valid resultFile name for project guid, %s. The following is a list of valid resultFile names for this project: %s"
            % (filetype, proj_guid, results_in_proj_df[['fileType']].values))
    else:
        # now filter on ResultFile.fileType
        desired_result = results_in_proj_df.loc[
            results_in_proj_df['fileType'].eq(filetype), ].reset_index(
                drop=True)

    # handle potential name collisions
    if len(desired_result) > 1:
        guid_val = user_prompt_select_result(desired_result, filetype)
        return guid_val
    else:
        guid_val = desired_result.loc[0, 'id']
        return guid_val


class AbstractionAppImg:
    """ Class representing an Abstraction App Object """
    abstraction_app_name = 'app.py'
    abstraction_image_name = 'abstraction_app.tar.gz'
    abstraction_config_filenames = [
        'config.toml', 'build.sh', 'entrypoint.sh', 'environment.yml'
    ]
    user_filenames = ['app.py']

    def __init__(self,
                 app_filepath: str,
                 hero_image: str,
                 title: str,
                 description: str,
                 data_contract_id: list,
                 project_guid: str,
                 work_dir: str,
                 result_file_ids: list = None,
                 is_sample_metadata_app: bool = None,
                 is_subject_metadata_app: bool = None):
        self.result_file_ids = result_file_ids
        self.is_sample_metadata_app = is_sample_metadata_app
        self.is_subject_metadata_app = is_subject_metadata_app
        self.project_guid = project_guid
        self.app_filepath = os.path.abspath(app_filepath)
        self.hero_image = os.path.abspath(hero_image)
        self.title = title
        self.description = description
        self.data_contract_id = data_contract_id
        self.work_dir = work_dir
        self.viz_configs_path = os.getcwd() if not auth.debug(
        ) is True else CONFIG['ABSTRACTION']['VIZ_CONFIGS_PATH']

    def create_static_image_url(self):
        return cu.hise_url("hydration", "hise_wide_static_img_path")

    def send_static_image_post(self, url, img_dict):
        resp = requests.post(url,
                             headers=get_bearer_token_header(),
                             files=img_dict)
        return resp

    def create_image_dict(self):
        return {
            'bytes': (self.hero_image, open(self.hero_image, 'rb'),
                      "image/%s" % (cu.get_filetype(self.hero_image)))
        }

    def determine_app_type(self):
        if self.result_file_ids is not None and len(self.result_file_ids) > 0:
            return self.result_file_ids
        elif self.is_sample_metadata_app:
            return [CONFIG['ABSTRACTION']['SAMPLE_METADATA_URN']]
        elif self.is_subject_metadata_app:
            return [CONFIG["ABSTRACTION"]['SUBJECT_METADATA_URN']]

    def create_args(self, img_resp):

        pargs = {
            "title": self.title,
            "description": self.description,
            "appDetails": self.abstraction_image_name,
            "inputResultFiles": self.determine_app_type(),
            "dataContractId": self.data_contract_id,
            "projectGuid": self.project_guid,
            "notebook": cu.current_notebook(),
            "homedir": IDE_HOME_DIR,
            "heroImages": [img_resp['url']],
            "instanceId": IDEInstance().friendlyName,
        }
        return pargs

    def copy_files_to_tmp(self, filename_list):
        # copy configs and/or user's app files to the temporary directory
        for f in filename_list:
            dst = os.path.normpath(self.work_dir + '/' + f)

            if f in self.abstraction_config_filenames:
                shutil.copy(os.path.normpath(self.viz_configs_path + '/' + f),
                            dst)
            elif f in self.user_filenames:
                if f in self.app_filepath:
                    shutil.copy(
                        '{}/{}'.format(os.path.dirname(self.app_filepath), f),
                        dst)
                elif f in self.hero_image:  # we save the image.. probably don't need to bundle it up
                    shutil.copy(
                        '{}/{}'.format(os.path.dirname(self.hero_image), f),
                        dst)
            else:
                # we need to preserve the directory tree since app.py may reference a custom module
                # take the relative path app.py and make that the destination
                try:
                    rel_dst = pl.PurePath(self.work_dir).joinpath(
                        pl.PurePath(os.path.dirname(f)).relative_to(
                            os.path.dirname(self.app_filepath)))
                except:
                    raise ValueError(
                        "{} in additional_files must be relative to the path specified in the app_filepath parameter. "
                        +
                        "If you want this file included in your application, please move the file somewhere in {}"
                        .format(f, os.path.dirname(self.app_filepath)))
                if not os.path.exists(rel_dst):
                    os.makedirs(rel_dst)
                dst = rel_dst.joinpath(pl.PurePath(os.path.basename(f)))
                shutil.copy(f, dst)
        return

    def create_tarball(self):

        # create tarball
        tarfile_path = '{wd}/{an}'.format(wd=self.work_dir,
                                          an=self.abstraction_image_name)
        with tarfile.open(tarfile_path, 'w:gz') as tar:
            tar.add(self.work_dir, arcname="")
        return True

    def create_file_arg(self):
        app_path = '{wd}/{an}'.format(wd=self.work_dir,
                                      an=self.abstraction_image_name)
        abstraction_img = {
            'file': (app_path, open(app_path, 'rb'), 'application/gzip', {
                'Expires': '0'
            })
        }
        return abstraction_img

    def create_url(self, args):
        return cu.hise_url("toolchain", "abstraction_path", args=args)

    def send_post(self, url, file):
        resp = requests.post(url,
                             headers=get_bearer_token_header(),
                             files=file)
        return resp


def validate_abstraction_app_path(app_path):
    if os.path.basename(app_path) != 'app.py':
        raise ValueError("App file must be called `app.py`")
    if not os.path.exists(app_path):
        raise ValueError("%s is not a valid file" % app_path)
    abspath = os.path.abspath(app_path)
    if not abspath.startswith(IDE_HOME_DIR):
        raise ValueError("App file must be within %s" % IDE_HOME_DIR)


def param_app_type_check(result_types, is_sample_app, is_subject_app):
    result_file_set = False
    sample_bool_set = False
    subject_bool_set = False
    if result_types is not None and len(result_types) != 0:
        result_file_set = True
    if is_sample_app is not None and is_sample_app is not False:
        sample_bool_set = True
    if is_subject_app is not None and is_subject_app is not False:
        subject_bool_set = True
    return (result_file_set, sample_bool_set, subject_bool_set)


def _validate_abstraction_params(title: str, description: str, input_ids: list,
                                 additional_files: list, additional_dirs: list,
                                 data_contract_id: str, project: str,
                                 is_sample_app: bool, is_subject_app: bool):
    """ validates parameters are coming in as expected """

    # required params check
    if title is None:
        raise ValueError("must provide a title for the abstraction")
    if description is None:
        raise ValueError("A description for the abstraction is required")
    if data_contract_id is None:
        raise ValueError(
            "A data contract must be submitted when saving an Abstraction")
    if project is None:
        raise ValueError(
            "A project must be specified when saving an Abstraction")

    # one of input_ids, is_sample_app, or is_subject_app must be set.
    input_ids_set, sample_app_bool_set, subject_app_bool_set = param_app_type_check(
        input_ids, is_sample_app, is_subject_app)
    app_type_list = [input_ids_set, sample_app_bool_set, subject_app_bool_set]
    if app_type_list.count(True) != 1:
        raise ValueError(
            "One of result_file_types, is_sample_metadata_app, is_subject_metadata_app must be specified. "
            + "Please try again by specifying only one of these parameters.")

    # type check
    if type(title) is not str:
        raise TypeError("title must be a string")
    if type(description) is not str:
        raise TypeError("description must be a string")
    if additional_files is not None and type(additional_files) is not list:
        raise TypeError("additional_files must be a list")
    if additional_dirs is not None and type(additional_dirs) is not list:
        raise TypeError("additional_dirs must be a list")
    if input_ids is not None and type(input_ids) is not list:
        raise TypeError("result_file_type must be of type list")
    if is_sample_app is not None and type(is_sample_app) is not bool:
        raise TypeError("is_sample_metadata_app must be of type boolean")
    if is_subject_app is not None and type(is_subject_app) is not bool:
        raise TypeError("is_subject_metadata_app must be of type boolean")
    if type(data_contract_id) is not str:
        raise TypeError("data_contract_id must be of type string")
    if type(project) is not str:
        raise TypeError("project must be of type string")

    if additional_dirs is not None and len(additional_dirs) > 0:
        for dir in additional_dirs:
            if not os.path.exists(dir):
                raise ValueError("%s is not a valid directory" % dir)

    # check that each file exists
    if additional_files is not None and len(additional_files) > 0:
        for f in additional_files:
            if not os.path.exists(f):
                raise ValueError("%s is not a valid file" % f)
    return True


def add_dir_to_additional_files(additional_files, additional_dirs):
    for dir in additional_dirs:
        files = os.listdir(dir)
        for file in files:
            full_path = os.path.join(dir, file)
            if os.path.isfile(full_path):
                additional_files.append(full_path)
    return additional_files


def save_abstraction(app_filepath: str = None,
                     additional_files: list = None,
                     additional_dirs: list = None,
                     title: str = None,
                     description: str = None,
                     project: str = None,
                     data_contract_id: str = None,
                     result_file_types: list = None,
                     is_sample_metadata_app: bool = None,
                     is_subject_metadata_app: bool = None,
                     image: str = None):  # optional
    """ 
    Save an abstraction to current user's account.
    
    Parameters:
        app_filepath (str) : path to file named app.py 
        additional_files (list) : list of additional files required for your app
        additional_dirs (list) : list of additional directories required for your app
        title (str) : a title for your app 
        description (str) : description of the app
        data_contract_id (str) : UUID of data contract. This data contract defines the column names of an input data.frame
                                 that's used as input for a visualization application.
        result_file_types (list) : Result fileType name (e.g Olink, fixed-RNA-seq-labeled, scRNA-seq-labeled, etc)
        is_sample_metadata_app (bool) : if True, will save the abstraction as a sample metadata visualization
        is_subject_metadata_app (bool) : If True, will save the abstraction as a subject metadata visualization
        image (str) : filepath to png thumbnail image for app 
    Returns:
        server response 
    Example: 
        hp.save_abstraction()
    """
    # parameter check
    _validate_abstraction_params(title, description, result_file_types,
                                 additional_files, additional_dirs,
                                 data_contract_id, project,
                                 is_sample_metadata_app,
                                 is_subject_metadata_app)

    validate_abstraction_app_path(app_filepath)

    # convert project to its' guid
    proj_guid = project_shortname_to_guid(project)

    # also convert resultFile.fileTypes to their guid
    result_file_ids = []
    if result_file_types is not None:
        for r in result_file_types:
            result_file_ids.append(result_filetype_to_guid(r, proj_guid))
    with tempfile.TemporaryDirectory() as tmpdirname:
        aobj = AbstractionAppImg(
            app_filepath=app_filepath,
            hero_image=image,
            title=title,
            description=description,
            data_contract_id=data_contract_id,
            project_guid=proj_guid,
            work_dir=tmpdirname,
            result_file_ids=result_file_ids,
            is_sample_metadata_app=is_sample_metadata_app,
            is_subject_metadata_app=is_subject_metadata_app)

        # POST to hydration and save the static image
        resp = cu.parse_hise_response(
            aobj.send_static_image_post(aobj.create_static_image_url(),
                                        aobj.create_image_dict()))

        additional_files = add_dir_to_additional_files(additional_files,
                                                       additional_dirs)

        # copy files to tmp dir and tar the bad boy up and upload
        if cu.prompt_user(CONFIG["PROMPTS"]["ABSTRACTION"]):
            aobj.copy_files_to_tmp(aobj.abstraction_config_filenames +
                                   aobj.user_filenames + additional_files)
            aobj.create_tarball()
            resp = cu.parse_hise_response(
                aobj.send_post(aobj.create_url(aobj.create_args(resp)),
                               aobj.create_file_arg()))

            return {
                "message": resp["Message"],
                "AbstractionId": resp["AbstractionId"]
            }
        else:
            print("canceling save abstraction call")
            return
