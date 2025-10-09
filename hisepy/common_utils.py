""" common_utils.py

Description: common methods for SDK development, but not available for end/HISE users

Methods:

Contributors: James Harvey
"""

import os
import sys
import requests
import shutil
import urllib
import tarfile
import yaml
import pyreadr
import pandas as pd
import datetime
import json
import pathlib
import copy
import time
import inspect
import uuid
import subprocess
import zlib
from hisepy.auth import debug, get_bearer_token_header, hise_server, IDEInstance, ide_is_from_guest_account, guest_hise_server, instance_account_guid

# directory of hisepy package
_here = os.path.abspath(os.path.dirname(__file__))


def read_yaml(file_path):
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


CONFIG = read_yaml('{}/config.yaml'.format(_here))
num_printed_notebooks = 3  # number of options user gets when a save call is invoked
the_current_notebook = None


def convert_notebook_to_python(notebook_path, output_path=None):
    ''' Convert notebook to a python script
    '''

    def _validate_convert_notebook_params(notebook_path, output_path):
        # check if the notebook_path is a valid notebook file
        if not notebook_path.endswith('.ipynb'):
            raise ValueError(
                "notebook path must end in .ipynb: {}".format(notebook_path))
        elif not os.path.isfile(notebook_path):
            raise FileNotFoundError(
                "notebook path does not exist: {}".format(notebook_path))
        # check if the output path is a valid directory and ends in .py
        elif output_path is not None and not output_path.endswith('.py'):
            raise ValueError(
                "output path must end in .py: {}".format(output_path))
        return

    # TODO: ensure /temp/training_job exists
    if output_path is None:
        output_path = '{}/{}/{}'.format(
            CONFIG['STORES']['TEMP_STORE'],
            CONFIG['TEMP_FOLDERS']['TRAINING_JOB_TMP'],
            CONFIG['TEMP_FILES']['NBCONVERT_TMP_FILE'])

    # validate input params
    _validate_convert_notebook_params(notebook_path, output_path)

    subprocess.run("jupyter nbconvert --to python {i} --output {out}".format(
        i=notebook_path, out=output_path),
                   shell=True,
                   check=True)
    print("converted notebook to python script: {}".format(output_path))
    return


def copy_files(src, dst):
    """ Copies file src to dst """
    if not os.path.exists(src):
        raise FileNotFoundError("Source file does not exist: {}".format(src))

    # copy the file
    shutil.copy(src, dst)
    return


def crc32_from_string(s):
    return zlib.crc32(s.encode('utf-8')) & 0xFFFFFFFF


def current_notebook():
    """
    Return the name of a notebook.
    """
    global the_current_notebook
    if the_current_notebook is not None:
        #once you specify the notebook in a kernel it should,
        #by definition always be the same notebook
        #This does mean you will have to reset the kernel
        #in order to specify a different notebook
        #if you make a mistake.
        #Really what we should have is a jupyter plugin to figure out the notebook.
        return the_current_notebook

    test_notebook = os.getenv("TEST_SCHEDULER_NOTEBOOK")
    if test_notebook is not None and test_notebook != "":
        return test_notebook
    ambiguitySeconds = 15 * 60
    notebooks = os.popen(
        "find /home -iname \"*.ipynb\" -printf \"%T@ %p\n\" -amin 5 | grep -v .ipynb_checkpoints | sort -nr | head -n {} | cut -f2- -d ' '"
        .format(num_printed_notebooks)).read().rstrip().split("\n")
    if len(notebooks) == 0 or notebooks[0] == "":
        raise TypeError(
            "Cannot get name of the current notebook. Make sure you are working somewhere within the /home directory, save the notebook you're working in, and try again"
        )
    elif len(notebooks) > 1:
        olderIsNew = (time.time() - os.stat(notebooks[1]).st_mtime
                      < ambiguitySeconds)
        newerIsOld = (time.time() - os.stat(notebooks[0]).st_mtime
                      >= ambiguitySeconds)
        if newerIsOld or olderIsNew:
            resp = -1
            while (resp < 0 or resp >= len(notebooks)):
                print("Cannot determine the current notebook.")
                for idx in range(len(notebooks)):
                    print("%d) %s" % (idx + 1, notebooks[idx]))
                print("Please select (1-%d) " % (len(notebooks)))
                resp = int(input()) - 1
                if (resp < 0 or resp >= len(notebooks)):
                    print(
                        "Invalid option for current notebook. Please try again and choose a value between [1,%s]"
                        % (num_printed_notebooks))
            the_current_notebook = notebooks[resp]
            return notebooks[resp]
    return notebooks[0]


def debug_config_value(heading: str, key: str):
    #override config vars with environment variables of the form below
    #e.g. HISEPY_STORES_OUTPUT_STORE
    return os.getenv("HISEPY_%s_%s" % (heading.upper(), key.upper()))


def find_files(directory, filenames):
    """ Given a directory, find all files in a given list """
    files_list = []
    for (root, dir, file) in os.walk(directory):
        [
            files_list.append('{}/{}'.format(root, f)) for f in file
            if f in filenames
        ]
    return files_list


def get_environment_name():
    # get instance obj from tracer
    inst = IDEInstance()

    # parse out modality info from instance obj
    return inst.environment['condaEnvName']


def get_filetype(this_filename):
    if "." in this_filename:
        return this_filename.split(".")[-1]
    else:
        return "json"


def get_from_config(heading: str, key: str):
    if debug():
        v = debug_config_value(heading, key)
        if v is not None:
            return v
    if heading.upper() in CONFIG:
        if key.upper() in CONFIG[heading.upper()]:
            return CONFIG[heading.upper()][key.upper()]
    raise ValueError("config value %s:%s not found" % (heading, key))


def get_func_params():
    frame = inspect.currentframe()
    args_info = inspect.getargvalues(frame)
    return args_info.locals


def get_ide(ide_instance_guid):
    endpoint = "https://{s}/{de}/{ig}".format(s=hise_server(),
                                              de=CONFIG['TRACER']['IDE_PATH'],
                                              ig=ide_instance_guid)
    resp = parse_hise_response(
        requests.request("GET", endpoint, headers=get_bearer_token_header()))
    return resp


def get_organization():

    # get account from amds
    acct_guid = instance_account_guid()
    query_dict = {'guid': acct_guid}
    url = hise_url('amds', 'account_path', 'filter')
    account_info = parse_hise_response(
        requests.post(url,
                      headers=get_bearer_token_header(),
                      data=json.dumps({"filter": query_dict})))

    # get org guid
    return account_info[0]['organization']['guid']


def get_projects(to_df: bool = True):
    """
    Returns information on all projects in the current account

    Parameters:
        to_df (bool): reshape to tabular, if True
    """
    keep_cols = ['guid', 'short_name', 'name']
    resp = parse_hise_response(
        requests.get(hise_url("amds", "project_path"),
                     headers=get_bearer_token_header()))

    # reshape to tabular format and concatenate each entry
    if to_df:
        proj_df = pd.DataFrame()
        for p in resp:
            proj_df = pd.concat([proj_df, pd.json_normalize(p)[keep_cols]])
        return proj_df

    return resp


def get_sdk_version():
    url = hise_url("ide_management", "sdk_version", 'python')
    version_tag = hise_get(url)
    return version_tag


def is_legacy_ide():
    """
    """
    # grab IDE instance GUID from env var
    ide_instance_guid = os.getenv("IDE_INSTANCE_GUID")
    if ide_instance_guid is None:
        raise Exception(
            "The IDE Instance guid is not set. This IDE is misconfigured. Please contact support"
        )

    # try tracer/ide endpoint first
    # TODO: it might be the case that we just need to GET tracer/ideinstances endpoint
    try:
        resp = get_ide(ide_instance_guid)
    except:  # if that fails, try tracer/ideinstances endpoint
        resp = IDEInstance()

    # if this fails, send a system error to user
    if resp is None:
        raise SystemError(
            "Failed to get IDE instance information in order to determine if IDE is legacy vs nextgen"
        )

    if resp.type == CONFIG['IDE']['NEXTGEN_IDE_TAG']:
        return False
    elif resp.type == CONFIG['IDE']['LEGACY_IDE_TAG']:
        return True
    else:
        raise SystemError(
            "ide instance type is not recognized. Please contact support")


def is_valid_upload_kernel():
    ''' Validates if the current kernel is a valid one for uploading results
    '''
    # get instance obj from tracer
    inst = IDEInstance()
    ide_guid = inst.id

    # parse out modality info from instance obj
    modality_name = inst.environment['condaEnvName']
    conda_env_path = '%s/%s' % (CONFIG['STORES']['ENV_STORE'], modality_name)

    # determine what conda env was used for the kernel
    kernel_source = sys.prefix

    # compare conda env from instance obj to conda env from current kernel
    if conda_env_path != kernel_source:
        return False
    return True


def files_within_private(files):
    '''
    Returns a list of files within the private directory
    '''
    assert type(files) is list, "files must be a list"
    bad_files = []

    # check if the files are within the private directory
    for f in files:

        # absolute path if passed in a relative one
        if not os.path.isabs(f):
            f = os.path.abspath(f)
        if f.startswith(CONFIG['STORES']['PRIVATE_STORE']):
            bad_files.append(f)
    return bad_files


def list_all_filepaths(directory):
    filepaths = []
    for root, _, files in os.walk(directory):
        for filename in files:
            filepath = os.path.join(root, filename)
            filepaths.append(filepath)
    return filepaths


def parse_sample_id_from_hise_file(hise_file):
    """
    Takes a hise_file object and returns the sample_id

    Parameters:
        hise_file (hise_file): hisepy.reader.hise_file object
    Returns:
        a string sample_id
    """
    # descriptors can have > 1 entry if filetype == Olink
    if type(hise_file['descriptors']) is list:
        this_sample_id = hise_file['descriptors'][0]['sample']['id']
    elif type(hise_file['descriptors']) is dict:
        this_sample_id = hise_file['descriptors']['sample']['id']
    return this_sample_id


def project_guid_to_shortname(proj_guid):
    """
    Takes a string, looks up if there's a Project guid with the passed in value. If there is, return the corresponding short name.
    Otherwise, let the user know the Project doesn't exist.

    Parameters:
        proj_guid (str) : the guid of a HISE Project
    """
    proj_df = get_projects()

    # chosen project must be in there, right?
    if proj_guid not in proj_df['guid'].values:
        raise ValueError("%s is not a valid project guid." % proj_guid)
    else:
        this_proj = proj_df.loc[
            proj_df['guid'].eq(proj_guid),
        ].reset_index(drop=True)

    return this_proj.loc[0, 'short_name']


def project_shortname_to_guid(proj_name):
    """
    Takes a string, looks up if there's a Project shortname with the passed in value. If there is, return the corresponding
    guid. Otherwise, let the user know the Project doesn't exist.

    Parameters:
        proj_name (str) : the short-name of a HISE Project
    """
    proj_df = get_projects()

    # chosen project must be in there, right?
    if proj_name not in proj_df['short_name'].values:
        raise ValueError(
            "%s is not a valid project name. The following is a list of valid projects: %s"
            % (proj_name, proj_df['short_name'].values))
    else:
        this_proj = proj_df.loc[
            proj_df['short_name'].eq(proj_name),
        ].reset_index(drop=True)

    # error if collisions exist
    if len(this_proj) > 1:
        raise SystemError(
            "Looks like there multiple Projects named %s. Please contact the software team."
            % (proj_name))
    else:
        proj_guid = this_proj.loc[0, 'guid']
        return proj_guid


def get_server(service):
    test_hydration_server = os.getenv("TEST_HYDRATION_SERVER")
    test_toolchain_server = os.getenv("TEST_TOOLCHAIN_SERVER")
    test_tracer_server = os.getenv("TEST_TRACER_SERVER")
    test_ledger_server = os.getenv("TEST_LEDGER_SERVER")
    if service == "hydration" and test_hydration_server is not None:
        return test_hydration_server
    elif service == "toolchain" and test_toolchain_server is not None:
        return test_toolchain_server
    elif service == "tracer" and test_tracer_server is not None:
        return test_tracer_server
    elif service == "ledger" and test_ledger_server is not None:
        return test_ledger_server
    else:
        return hise_server()


def hise_get(url: str):
    return parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))


def hise_url(service: str,
             config_path: str,
             resource: str = None,
             args: dict = None):
    if service.upper() not in CONFIG:
        raise ValueError("%s is not a known HISE service" % service)
    if config_path.upper() not in CONFIG[service.upper()]:
        raise ValueError("%s is not a known path in %s service" %
                         (config_path, service))

    server = get_server(service)
    protocol = "http" if "localhost" in server else "https"
    url = "%s://%s/%s" % (protocol, server,
                          CONFIG[service.upper()][config_path.upper()])
    if resource is not None:
        if type(resource) is not str:
            raise ValueError("resource argument was a %s, not a string" %
                             (type(resource)))
        url += "/%s" % resource

    if args is not None:
        if type(args) is not dict:
            raise ValueError("query string argument was a %s, not a dict" %
                             (type(args)))
        url += "?%s" % (urllib.parse.urlencode(args, doseq=True))
    return url


def list_files_and_dirs(directory):
    """ Lists all files and directories in a given path """
    return os.listdir(directory)


def log_downloaded_files(file_id: str,
                         sample_id: str = None,
                         ide_dir: str = None,
                         replica_file_id: str = None,
                         replica_sample_id: str = None):
    """
    Attaches fileId for the project folder file that was downloaded

    Parameters:
        file_id (str) : file_id of file in project folder
    """
    # fileID must not be null at least
    if file_id is None:
        raise ValueError("must pass in a file_id to log_download_files()")

    # if null, assume ide directory is (/home/jupyter)
    if ide_dir is None:
        ide_dir = CONFIG['IDE']['HOME_DIR']

    cache_file_path = '{h}/{c}'.format(h=ide_dir,
                                       c=CONFIG['IDE']['CACHE_LOG_NAME'])
    cache_df = pd.DataFrame(columns=[
        'fileId', 'sampleId', 'downloadSourceDir', 'downloadTimeStamp'
    ])
    download_workdir = os.getcwd()
    if os.path.exists(cache_file_path):
        cache_file = pyreadr.read_r(cache_file_path)

        # extract out the data.frame
        cache_df = cache_file[None]

    # check if the file_id is already logged
    if file_id in cache_df['fileId'].values:
        pass
    else:
        new_entry = pd.DataFrame(
            data={
                'fileId': [file_id],
                'replicaFileId': [replica_file_id],
                'sampleId': [sample_id],
                'replicaSampleId': [replica_sample_id],
                'downloadSourceDir': [download_workdir],
                'downloadTimeStamp': [str(datetime.datetime.now())]
            })

        cache_df = pd.concat([cache_df, new_entry])
        pyreadr.write_rds(
            '{h}/{d}'.format(h=ide_dir, d=CONFIG['IDE']['CACHE_LOG_NAME']),
            cache_df)
    return


def parse_hise_response(resp):
    obj = None
    try:
        obj = json.loads(resp.text)
        if "Errors" in obj and len(obj["Errors"]) > 0:
            msg = obj["Errors"][0]["Message"]
        else:
            msg = resp.reason
    except:
        msg = resp.reason

    if resp.status_code != 200:
        raise SystemError(
            "%s request to %s returned with status %d. %s" %
            (resp.request.method, resp.url, resp.status_code, msg))
    return obj


def prompt_from_options(prompt: str, opts: list, returnIndex: bool = False):
    print(prompt)
    if len(opts) == 0:
        raise ValueError("Cannot prompt for '%s' with no options" % prompt)
    if len(opts) == 1:
        return 0 if returnIndex else opts[0]

    selected = -1
    while True:
        for i, o in enumerate(opts):
            print("%2d) %s" % ((i + 1), o))
        try:
            selected = int(input("[1 - %d]" % len(opts)))
        except ValueError:
            selected = 0
        if selected > 0 and selected <= len(opts):
            return selected - 1 if returnIndex else opts[selected - 1]
        print('Please enter a number.')


def prompt_user(msg: str = None, additional_fields=None):
    """ Prompts end users in order to continue """
    if msg is None:
        raise ValueError("Must provide a contextual message")
    if additional_fields is None:
        additional_fields = ""
    print("{m}: {af}".format(m=msg, af=additional_fields))
    user_input = input('Do you want to proceed? (y/n)')
    while user_input.lower() not in ['y', 'n']:
        print('please enter either "n" for no, or "y" for yes.')
        user_input = input('(y/n)')
    if user_input.lower() == 'y':
        return True
    elif user_input.lower() == 'n':
        return False


def prompt_for_input(msg: str = None):
    """ Prompts user for input """
    if msg is None:
        raise ValueError("Must provide a contextual message")
    try:
        user_input = input(msg)
    except (KeyboardInterrupt, EOFError):
        user_input = None
    return user_input


def prompt_user_custom(msg: str = None):
    """ Prompts end users and asks for custom input """
    if msg is None:
        raise ValueError("Must provide a contextual message")
    print(msg)
    user_input = input('Please enter your response {key:val}: ')
    while user_input == '':
        print('Input cannot be empty. Please try again.')
        user_input = input('Please enter your response: ')
    return user_input


def prompt_yn(prompt: str):
    print(prompt)
    user_input = None
    while True:
        user_input = input('(y/n)')
        if user_input.lower() == 'y':
            return True
        elif user_input.lower() == 'n':
            return False
        print('please enter either "n" for no, or "y" for yes.')


def remove_dir(directory):
    """ Removes entire directory, including any child files """
    shutil.rmtree(directory)
    return True


def replica_files_used(input_file_ids: list, ide_dir: str = None):
    '''
    '''
    replica_file_ids = []
    if ide_dir is None:
        ide_dir = CONFIG['IDE']['HOME_DIR']

    # read log file
    cache_file = pyreadr.read_r('{h}/{c}'.format(
        h=ide_dir, c=CONFIG['IDE']['CACHE_LOG_NAME']))

    # extract out the data.frame
    cache_df = cache_file[None]

    # subset to entries where input_file_ids have non-null replicaFileIds
    replica_subset = cache_df.loc[
        (cache_df['fileId'].isin(input_file_ids)) &
        (~cache_df['replicaFileId'].isnull()),
    ]
    replica_ids = replica_subset['replicaFileId'].unique().tolist()
    # assert that the length of replicas and input_file_ids are still the same
    if len(input_file_ids) != len(replica_ids):
        raise SystemError(
            "The number of replica Ids does not match the number of input fileIds. Please contact the support team to resolve"
        )
        return
    if len(replica_ids) == 0:
        return None
    else:
        return replica_ids


def string_contains_whitespaces(file_str):
    """ returns True if a string contains whitespaces"""

    # loop through the each string character and check if it's a whitespace
    if any(s.isspace() for s in file_str):
        return True
    else:
        return False


def tardir(output_filename, source_dir):
    """ Utility function that will create a tar file for an entire directory and its children """
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))


def uuid_string():
    return uuid.uuid4().hex  # 32 hex characters


def validate_upload_input_ids(input_file_ids: list, input_sample_ids: list,
                              ide_dir):
    """ Checks that files associated with a result have
        been seen in a user's IDE
    """
    if input_file_ids is not None:
        assert type(input_file_ids) is list
    if input_sample_ids is not None:
        assert type(input_sample_ids) is list

    cache_file_path = '{h}/{c}'.format(h=ide_dir,
                                       c=CONFIG['IDE']['CACHE_LOG_NAME'])

    if (not os.path.exists(cache_file_path)):
        raise FileNotFoundError(
            "No files have been downloaded into this IDE. You cannot upload results without utilizing any HISE input data."
        )

    cache_df = pyreadr.read_r(cache_file_path)[None]

    # loop through those ids and check they have been downloaded at some point
    invalid_file_ids = []
    mismatch_download_sources = dict()
    notebook_dir = os.getcwd()
    for f in input_file_ids:
        if (f not in cache_df['fileId'].unique()) and (
                f not in cache_df['replicaFileId'].unique()):
            invalid_file_ids += [f]

    invalid_sample_ids = []
    for s in input_sample_ids:
        if (s not in cache_df['sampleId'].unique()) and (
                s not in cache_df['replicaSampleId'].unique()):
            invalid_sample_ids += [s]

    if len(invalid_file_ids) > 0:
        raise AssertionError(
            "The following file Ids were not downloaded in this IDE. You cannot reference a file in a result without downloading it first. {}"
            .format(invalid_file_ids))
    if len(invalid_sample_ids) > 0:
        raise AssertionError(
            "The following sample Ids were not downloaded in this IDE. You cannot refernce a file in a result without downloading it first. {}"
            .format(invalid_sample_ids))

    return


def verify_file_count(dir, expected_num_files):
    """ Checks if the number of files in a directory is correct """

    file_count = 0
    # recursively walk down tree and check if current iteration is a file
    for root_dir, this_dir, file in os.walk(dir):
        file_count += len(file)
    if file_count != expected_num_files:
        raise ValueError("Expected to find %d files, but only %d were found" %
                         (expected_num_files, file_count))
    return True
