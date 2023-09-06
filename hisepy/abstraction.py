import json
import os
import requests
import hisepy.common_utils as cu
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, instance_name_path
from hisepy.reader import parse_hise_response, hise_url

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


def _validate_abstraction_params(config: str, title: str, description: str,
                                 input_ids: list):
    """ validates parameters are coming in as expected """

    # required params check
    if config is None:
        raise ValueError("Cannot save an abstraction without a config")
    if title is None:
        raise ValueError("must provide a title for the abstraction")
    if description is None:
        raise ValueError("A description for the abstraction is required")
    if input_ids is None or len(input_ids) < 1:
        raise ValueError("You must provide at least 1 input file ID")

    # type check
    if type(config) is not str:
        raise TypeError("layout config must be a filepath string")
    if type(title) is not str:
        raise TypeError("title must be a string")
    if type(description) is not str:
        raise TypeError("description must be a string")
    if type(input_ids) is not list:
        raise TypeError("input file Ids must be a list")

    # filepaths truly exist check
    #if not os.path.exists(config):
    #    raise ValueError("%s is not a valid file." % config)
    return


# TODO: combine this with the original save_static.
# this is only separated because one is uploading to an account-specific location
def save_abstraction_static_image(image, title, viz_type):
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

    # TODO: I think I need a hydration endpoint...?
    # an endpoint that points to the bucket or some download url
    """
    if not os.path.exists(image):
        raise ValueError("%s is not a valid file." % image)

    img_dict = {
        'bytes': (image, open(image,
                              'rb'), "image/%s" % (cu.get_filetype(image)))
    }
    args = {"title": title}
    return parse_hise_response(
        requests.post(hise_url("hydration", "hise-wide-upload-path", args=args),
                      headers=get_bearer_token_header(),
                      files=img_dict))
    """
    result_img_dict = {
        'scRNA-seq-labeled':
        'https://storage.googleapis.com/aifi-static-assets/abstraction-static-images-test/scrna-abstraction.png',
        'Cytometry - Supervised Gating Population Counts':
        'https://storage.googleapis.com/aifi-static-assets/abstraction-static-images-test/flow-abs.png'
    }
    # For now... I'll just hard-code where these files live
    # cyto image used: return 'https://storage.googleapis.com/aifi-static-assets/abstraction-static-images-test/flow-abs.png'
    return result_img_dict[viz_type]


# TODO: placeholder
def create_abstraction_image():
    """
    TODO: this info has to persist somewhere and not just in the abstraction payload, right...? 
    """
    return


# TODO: what is this layout config going to look like for vitessce vs dash vs other viz frameworks??
# for dash-apps, we require a layout.py script, but it only defines layout of dashboard...?
# what about
# for vitessce, require a config_view.json file and it defines layout as well as as where data lives in remote server
def save_abstraction(layout_config: str = None,
                     title: str = None,
                     viz_framework: str = None,
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
    # TODO: bundling and creating the image based of user's framework selection
    # for now... nothing
    layout_config = "fake config"

    # some stuff I hard-coded at the time
    # TODO: users are not going to know the result ids.
    # can we have the widget handle this conversion of result-filetype to ID?

    # parameter check
    _validate_abstraction_params(layout_config, title, description,
                                 result_file_ids)

    # prompt user that they're creating an abstraction
    cu.prompt_user(CONFIG["PROMPTS"]["ABSTRACTION"])

    # set up POST request
    qargs = {
        "title": title,
        "description": description,
        "appDetails": layout_config,
        "inputResultFiles": result_file_ids,
        "notebook": current_notebook(),
        "homedir": IDE_HOME_DIR,
        "instanceId": get_from_metadata_server(instance_name_path)
    }

    # save static image if user passes some in
    if image is not None:
        img_resp = save_abstraction_static_image(image=image,
                                                 title=title,
                                                 viz_type=viz_framework)
        """ comment out until this imaginary endpoint exists...
        if img_resp['error'] is not False:
            raise SystemError(
                "Something went wrong when saving the static image")
        """
        qargs['heroImages'] = img_resp

    # send it; parse response
    url = hise_url("toolchain", "abstraction_path", args=qargs)
    resp = parse_hise_response(
        requests.post(url, headers=get_bearer_token_header()))
    return resp
