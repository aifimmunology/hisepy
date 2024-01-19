import json
import os
import requests
import tempfile
import tarfile
import shutil
import pathlib as pl
import hisepy.common_utils as cu
import hisepy.upload as cup
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, instance_name_path
from hisepy.reader import parse_hise_response, hise_url
from hisepy.scheduler import current_notebook
import pandas as pd
from hisepy import auth

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))
IDE_HOME_DIR = CONFIG['IDE']['HOME_DIR'] if not auth.debug() else os.getcwd()


def get_result_files(to_df=True):
    """ Returns available result files for the user's current account/projects.
        The object returned will be a json object, or a data.frame.
    """
    keep_cols = ['id', 'fileType', 'description', 'isSearchable']
    resp = parse_hise_response(
        requests.get(hise_url("ledger", "result_file_search_path"),
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


def result_filetype_to_guid(filetype: str):
    ''' 
    Given a ResultFile.fileType, return the corresponding resultFile.ID
    '''

    # get all the resultFiles and concat
    agg_df = get_result_files()

    # check that the result file exists
    if filetype not in agg_df['fileType'].values:
        raise ValueError(
            "%s is not a valid resultFile name. The following is a list of valid resultFile names: %s"
            % (filetype, agg_df['fileType'].values))
    else:
        # additional filter on isSearchable because you can only create visualizations on data you're able to find/download
        desired_result = agg_df.loc[
            agg_df['fileType'].eq(filetype)
            & agg_df['isSearchable'].eq("true"),
            ['id', 'fileType', 'description']].reset_index(drop=True)

    # handle potential name collisions
    if len(desired_result) > 1:
        guid_val = user_prompt_select_result(desired_result, filetype)
        return guid_val
    else:
        guid_val = desired_result.loc[0, 'id']
        return guid_val


def _validate_abstraction_params(title: str, description: str, input_ids: list,
                                 additional_files: list):
    """ validates parameters are coming in as expected """

    # required params check
    if title is None:
        raise ValueError("must provide a title for the abstraction")
    if description is None:
        raise ValueError("A description for the abstraction is required")

    # type check
    if type(title) is not str:
        raise TypeError("title must be a string")
    if type(description) is not str:
        raise TypeError("description must be a string")
    if type(additional_files) is not list:
        raise TypeError("additional_files must be a list")

    # check that each file exists
    for f in additional_files:
        if not os.path.exists(f):
            raise ValueError("%s is not a valid file" % f)
    return True


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
                 work_dir: str,
                 result_file_ids: list = None):
        self.result_file_ids = result_file_ids
        self.app_filepath = os.path.abspath(app_filepath)
        self.hero_image = os.path.abspath(hero_image)
        self.title = title
        self.description = description
        self.work_dir = work_dir
        self.viz_configs_path = CONFIG['ABSTRACTION']['VIZ_CONFIGS_PATH']

    def create_static_image_url(self):
        return hise_url("hydration", "hise_wide_static_img_path")

    def send_static_image_post(self, url, img_dict):
        resp = parse_hise_response(
            requests.post(url,
                          headers=get_bearer_token_header(),
                          files=img_dict))
        return resp

    def create_image_dict(self):
        return {
            'bytes': (self.hero_image, open(self.hero_image, 'rb'),
                      "image/%s" % (cu.get_filetype(self.hero_image)))
        }

    def create_args(self, img_resp):
        return {
            "title": self.title,
            "description": self.description,
            "appDetails": self.abstraction_image_name,
            "inputResultFiles": self.result_file_ids,
            "notebook": current_notebook(),
            "homedir": IDE_HOME_DIR,
            "heroImages": [img_resp['url']],
            "instanceId": get_from_metadata_server(instance_name_path)
        }

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
                        "{} in additional_files must be relative to the path specified in the app_filepath parameter. If you want this file included in your application, please move the file somewhere in {}"
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
        return hise_url("toolchain", "abstraction_path", args=args)

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


def save_abstraction(app_filepath: str = None,
                     additional_files: list = None,
                     title: str = None,
                     description: str = None,
                     result_file_type: list = None,
                     image: str = None):  # optional
    """ 
    Save an abstraction to current user's account.
    
    Parameters:
        app_filepath (str) : path to file named app.py 
        additional_files (list) : list of additional files required for your app
        title (str) : a title for your app 
        description (str) : description of the app
        result_file_ids (list) : UUID of Result File Type (e.g Olink, fixed-RNA-seq-labeled, scRNA-seq-labeled, etc)
        image (str) : filepath to png thumbnail image for app 
    Returns:
        server response 
    Example: 
        hp.save_abstraction()
    """
    # parameter check
    if additional_files is None:
        additional_files = []

    # convert each filetype to its' corresponding guid
    if result_file_type is not None:
        result_file_ids = []
        for r in result_file_type:
            result_file_ids.append(result_filetype_to_guid(r))
    _validate_abstraction_params(title, description, result_file_ids,
                                 additional_files)
    validate_abstraction_app_path(app_filepath)
    with tempfile.TemporaryDirectory() as tmpdirname:
        aobj = AbstractionAppImg(app_filepath=app_filepath,
                                 hero_image=image,
                                 title=title,
                                 description=description,
                                 work_dir=tmpdirname,
                                 result_file_ids=result_file_ids)

        # POST to hydration and save the static image
        resp = aobj.send_static_image_post(aobj.create_static_image_url(),
                                           aobj.create_image_dict())

        # copy files to tmp dir and tar the bad boy up and upload
        cu.prompt_user(CONFIG["PROMPTS"]["ABSTRACTION"])
        aobj.copy_files_to_tmp(aobj.abstraction_config_filenames +
                               aobj.user_filenames + additional_files)
        aobj.create_tarball()
        resp = parse_hise_response(
            aobj.send_post(aobj.create_url(aobj.create_args(resp)),
                           aobj.create_file_arg()))

        return {
            "message": resp["Message"],
            "AbstractionId": resp["AbstractionId"],
            "configFileId": resp["ConfigFileId"]
        }
