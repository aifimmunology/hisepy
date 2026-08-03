import os
import pandas as pd
import requests

from hisepy.auth import debug, get_bearer_token_header, ide_instance_guid
from hisepy.common_utils import hise_url, parse_hise_response, project_shortname_to_guid, read_yaml
from hisepy.logging import with_default_logging, logger
from hisepy.upload_utils import validate_files, validate_hero_image
from hisepy.viz_utils import create_visualization_tarball, enumerate_all_files, get_build_template_and_params

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = read_yaml('{}/config.yaml'.format(_here))
IDE_HOME_DIR = CONFIG['IDE']['HOME_DIR_V2'] if not debug() else os.getcwd()
any_project_urn = "urn:hise:project:any"
save_abstraction_conda_env_checked = False


@with_default_logging
def get_data_contracts(to_df: bool = True):
    """ 
        Returns available data contracts for the user's current account/projects.
        The object returned will be a json object, or a data.frame.
    
        Parameters: 
            to_df (bool): boolean, where if true, output will be a data.frame. Otherwise, 
            the object returned will be a json response. 
    
        """
    keep_cols = [
        'id', 'name', 'description', 'inputResultFileTypes', 'dockerImage',
        'inputFileMount', 'outputFileMount'
    ]
    data_contracts_resp = parse_hise_response(
        requests.get(hise_url("hydration", "data_contract_path"),
                     headers=get_bearer_token_header()))

    # map the inputResultFileTypes field from GUIDs to friendly names
    result_files_map = {
        result_file['id']: result_file['friendlyName']
        for result_file in get_result_files(to_df=False)
    }
    for data_contract in data_contracts_resp:
        data_contract['inputResultFileTypes'] = [
            result_files_map[irft]
            for irft in data_contract['inputResultFileTypes']
        ]

    try:
        if to_df:
            result_df = result_json_to_df(data_contracts_resp)
            return result_df[keep_cols]
        else:
            return data_contracts_resp
    except Exception as e:
        raise Exception(f"failed to retrieve data contracts: {e}")


@with_default_logging
def get_result_files(to_df: bool = True):
    """ 
    Returns available result files for the user's current account/projects.
    The object returned will be a json object, or a data.frame.

    Parameters: 
        to_df (bool): boolean, where if true, output will be a data.frame. Otherwise, 
        the object returned will be a json response. 

    """
    keep_cols = [
        'id', 'fileType', 'friendlyName', 'description', 'projectGuid',
        'isSearchable'
    ]
    resp = parse_hise_response(
        requests.get(hise_url("ledger", "result_file_search_path"),
                     headers=get_bearer_token_header()))
    try:
        if to_df:
            result_df = result_json_to_df(resp)
            return result_df[keep_cols]
        else:
            return resp
    except Exception as e:
        raise Exception(f"failed to retrieve result files: {e}")


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


@with_default_logging
def result_filetype_to_guid(filetype: str, proj_guid):
    ''' 
    Given a ResultFile.fileType, return the corresponding resultFile.ID
    '''

    # get all the resultFiles and concat
    agg_df = get_result_files()

    # check that the result file exists for the chosen project, or if the project is set to "urn:hise:project:any"
    results_in_proj_df = agg_df.loc[
        agg_df['projectGuid'].isin([proj_guid, any_project_urn]),
    ]
    if filetype not in results_in_proj_df[['fileType']].values:
        raise ValueError(
            "%s is not a valid resultFile name for project guid, %s. The following is a list of valid resultFile names for this project: %s"
            % (filetype, proj_guid, results_in_proj_df[['fileType']].values))
    else:
        # now filter on ResultFile.fileType
        desired_result = results_in_proj_df.loc[
            results_in_proj_df['fileType'].eq(filetype),
        ].reset_index(drop=True)

    # handle potential name collisions
    if len(desired_result) > 1:
        guid_val = user_prompt_select_result(desired_result, filetype)
        return guid_val
    else:
        guid_val = desired_result.loc[0, 'id']
        return guid_val


@with_default_logging
def save_abstraction(application_files: list[str],
                     application_dirs: list[str],
                     title: str,
                     data_contract_id: str,
                     png_image: str,
                     description: str = '',
                     project: str = '',
                     build_template_name: str = '',
                     build_template_major_version: int = -1,
                     build_template_minor_version: int = -1,
                     build_template_parameters: dict[str, str] | None = None,
                     infer_build_template_arguments: bool = True):
    """ 
    Given an app supported by HISE Visualization Build Templates, save it as an abstraction to current user's account.
    
    Parameters:
        application_files (list): list of individual files used by your app (e.g., custom CSS).
            Only files under /home/workspace can be included.
        application_dirs (list): list of directories used by your app. 
            Directories specified are for configs or scripts, not input data.
            Only directories under /home/workspace can be included.
        title (str): a 10+ character title for the app
        data_contract_id: a GUID of the Data Contract ID this Abstraction uses
        png_image (str): png thumbnail image for the abstraction
        description (str): description of app being uploaded (optional)
        project (str): the short name of the HISE project to save the Abstraction
            if left blank, defaults to the IDE's HISE project
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
        server response 
    Example: 
        hisepy.save_abstraction(application_files=['dash_app/app.py'],
                                application_dirs=['data'],
                                title="Hello world Dash app",
                                data_contract_id='f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                                png_image="dash_app/thumbnail.png",
                                description="An amazingly complex data visualization")
    """
    # parameter check
    title = title.strip()
    if len(title) < 10:
        raise RuntimeError('Your title must be at least 10 characters long')

    validate_files(application_files, application_dirs)
    png_image = validate_hero_image(png_image)
    validate_data_contract_id(data_contract_id)

    proj_guid = project_shortname_to_guid(project) if project != '' else None

    all_files = enumerate_all_files(application_files, application_dirs)
    vbt, template_params = get_build_template_and_params(
        build_template_name, build_template_major_version,
        build_template_minor_version, all_files, build_template_parameters
        or {}, infer_build_template_arguments)
    tarfile_path = create_visualization_tarball(CONFIG,
                                                list(all_files),
                                                is_abstraction=True)

    # POST to hydration and save the static image
    img_resp = parse_hise_response(
        requests.post(
            url=hise_url('hydration', 'hise_wide_static_img_path'),
            headers=get_bearer_token_header(),
            files={'bytes': (png_image, open(png_image, 'rb'), 'image/png')}))

    abstraction_workflow_url = hise_url('ide_management',
                                        'abstraction_workflow')
    logger.info('Creating Abstraction App workflow: %s',
                abstraction_workflow_url)
    resp = parse_hise_response(
        requests.post(url=abstraction_workflow_url,
                      json={
                          'artifactsFileName': tarfile_path,
                          'dataContractId': data_contract_id,
                          'description': description,
                          'images': [img_resp['id']],
                          'instanceGuid': ide_instance_guid(),
                          'projectGuid': proj_guid,
                          'title': title,
                          'visualizationBuildTemplateArgs': template_params,
                          'visualizationBuildTemplateId': vbt['id']
                      },
                      headers=get_bearer_token_header()))
    workflowId = resp['WorkflowId']
    logger.extra['_override']['workflow'] = workflowId
    return 'Abstraction App Workflow initiated: %s' % (hise_url(
        'workflow', 'ui_path', workflowId))


def validate_data_contract_id(id: str):
    parse_hise_response(
        requests.get(hise_url('hydration', 'data_contract_path', id),
                     headers=get_bearer_token_header()))
