import json
import os
import requests
import tempfile
import tarfile
import shutil
import hisepy.common_utils as cu
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, instance_name_path
from hisepy.reader import parse_hise_response, hise_url
from hisepy.scheduler import current_notebook

from hisepy import auth

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))
IDE_HOME_DIR = CONFIG['IDE']['HOME_DIR'] if not auth.debug() else os.getcwd()

accepted_abstraction_results = {
    "Cytometry - Supervised Gating Population Counts":
    "264d2dae-0934-423f-88a1-1e1d348db653",
    "scRNA seq labeled": "58e1b1fd-3cd8-408e-868e-a22104d86b12"
}


def get_abstraction_result_files(result_names: list):
    """ Returns available result files for the user's current account/projects """
    assert type(result_names) is list, "input must be a list of strings"

    # make sure we support abstractions for the selected result
    ids = []
    for rn in result_names:
        this_id = map_result_friendly_name_to_id(rn)
        ids += [this_id]
    tmp = "%s" % (', '.join(['"{}"'.format(v) for v in ids]))
    resp = requests.post(hise_url("ledger", "result_file_search_path"),
                         json={"filter": {
                             "id": {
                                 "$in": ids
                             }
                         }},
                         headers=get_bearer_token_header())
    return parse_hise_response(resp)


def is_result_supported(result_name: str):
    """ Returns a boolean determining whether a result file is allowed to be used for abstractions
    """
    if result_name not in accepted_abstraction_results.keys():
        return False
    else:
        return True


def map_result_friendly_name_to_id(result_name: str):
    """ 
    this function will take a resultFile.FriendName string value and return you 
    its corresponding resultFile.ID 
    """
    if not is_result_supported(result_name):
        raise SystemError(
            "The result file type is not current supported for visualization work. The following are supported results for visualizations: %s"
            % (accepted_abstraction_results.keys()))
        return
    else:
        return accepted_abstraction_results[result_name]


def _validate_abstraction_params(title: str, description: str,
                                 input_ids: list):
    """ validates parameters are coming in as expected """

    # required params check
    if title is None:
        raise ValueError("must provide a title for the abstraction")
    if description is None:
        raise ValueError("A description for the abstraction is required")
    if input_ids is None or len(input_ids) < 1:
        raise ValueError("You must provide at least 1 input file ID")

    # type check
    if type(title) is not str:
        raise TypeError("title must be a string")
    if type(description) is not str:
        raise TypeError("description must be a string")
    if type(input_ids) is not list:
        raise TypeError("input file Ids must be a list")
    return True


class AbstractionAppImg:
    """ Class representing an Abstraction App Object """
    abstraction_app_name = 'app.py'
    abstraction_image_name = 'abstraction_app.tar.gz'

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
        self.filepaths = {
            os.path.abspath(path)
            for path in [self.viz_configs_path, self.app_filepath]
        }

    def save_abstraction_static_image(self):
        """
        Saves PNG image to a hise-wide bucket
        
        Parameters: 
            image (str): absolute path to image 
            title (str): title of image being uploaded 
        Returns:
            Response from server 

        Example: 
            hp.save_static_image()
        """
        if not os.path.exists(self.hero_image):
            raise ValueError("%s is not a valid file." % self.hero_image)
        img_dict = {
            'bytes': (self.hero_image, open(self.hero_image, 'rb'),
                      "image/%s" % (cu.get_filetype(self.hero_image)))
        }
        args = {"title": self.title}
        hh = get_bearer_token_header()
        return parse_hise_response(
            requests.post(hise_url("hydration", "hise_wide_static_img_path"),
                          headers=get_bearer_token_header(),
                          files=img_dict))

    def create_abstraction_image(self):
        """
        TODO: this info has to persist somewhere and not just in the abstraction payload, right...? 
        """
        tarfile_path = '{wd}/{an}'.format(wd=self.work_dir,
                                          an=self.abstraction_image_name)
        with tarfile.open(tarfile_path, 'w:gz') as tar:
            tar.add(self.work_dir, arcname="")
        return True

    def export_abstraction_image(self):
        img_resp = self.save_abstraction_static_image()
        if img_resp['error'] is not False:
            print("Error uploading image: ", img_resp['error'])

        # set up POST request
        qargs = {
            "title": self.title,
            "description": self.description,
            "inputResultFiles": self.result_file_ids,
            "notebook": current_notebook(),
            "homedir": IDE_HOME_DIR,
            "instanceId": get_from_metadata_server(instance_name_path)
        }
        app_path = '{wd}/{an}'.format(wd=self.work_dir,
                                      an=self.abstraction_image_name)
        abstraction_img = {
            'file': (app_path, open(app_path, 'rb'), 'application/json', {
                'Expires': '0'
            })
        }
        url = hise_url('toolchain', 'abstraction_path', args=qargs)

        # prompt user; send it; parse response
        cu.prompt_user(CONFIG["PROMPTS"]["ABSTRACTION"])
        url = hise_url("toolchain",
                       "abstraction_path",
                       args=qargs,
                       files=abstraction_img)
        resp = parse_hise_response(
            requests.post(url, headers=get_bearer_token_header()))
        return resp


def validate_abstraction_app_path(app_path):
    if os.path.basename(app_path) != 'app.py':
        raise ValueError("App file must be called `app.py`")
    if not os.path.exists(app_path):
        raise ValueError("%s is not a valid file" % app_path)
    abspath = os.path.abspath(app_path)
    if not abspath.startswith(IDE_HOME_DIR):
        raise ValueError("App file must be within %s" % IDE_HOME_DIR)


# TODO: are users still passing in additional files? what else would they need to send for release 1?
def save_abstraction(app_filepath: str = None,
                     title: str = None,
                     description: str = None,
                     result_file_ids: list = None,
                     image: str = None):  # optional
    """ 
    Save an abstraction to current user's account.
    
    Parameters:

    Returns:
        server response 
    Example: 
        hp.save_abstraction()
    """
    # parameter check
    _validate_abstraction_params(title, description, result_file_ids)
    validate_abstraction_app_path(app_filepath)
    with tempfile.TemporaryDirectory() as tmpdirname:
        aobj = AbstractionAppImg(app_filepath=app_filepath,
                                 hero_image=image,
                                 title=title,
                                 description=description,
                                 work_dir=tmpdirname,
                                 result_file_ids=result_file_ids)

        shutil.copytree(aobj.viz_configs_path, tmpdirname, dirs_exist_ok=True)
        app_dst = os.path.normpath(tmpdirname +
                                   os.path.dirname(aobj.app_filepath))
        if not os.path.exists(app_dst):
            os.makedirs(app_dst)
        shutil.copy(aobj.app_filepath, app_dst)

        # tar the bad boy up and upload
        aobj.create_abstraction_image()
        resp = aobj.export_abstraction_image()

        print("abstraction image was successfully uploaded!")
        return resp
