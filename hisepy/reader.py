import json
import os
import pathlib
import urllib
import uuid
import pandas as pd
import copy
from termcolor import colored

import requests

import hisepy.common_utils as cu
import hisepy.formatter as hf
import hisepy.lookup as hl
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


class hise_file:
    """ A class representing a hise_file.

    Attributes:
        file_id (str): UUID for a file.
        file_path (str): Path where physical file is saved.
        descriptors (dict): Contains metadata.
    """

    def __init__(self,
                 file_id,
                 file_path=None,
                 file_type=None,
                 descriptors=None,
                 data_values=None):
        """ Inits hise_file object """
        if type(file_id) is uuid.UUID:
            self.id = file_id
        else:
            try:
                self.id = uuid.UUID(file_id)
            except Exception as e:
                raise TypeError("%s is not a valid UUID. %s" % (file_id, e))

        self.status = False
        self.message = "Not loaded. Run file_obj.load() to load"
        if descriptors is not None and file_path is not None and os.path.exists(
                file_path):
            self.descriptors = descriptors
            self.path = file_path
            self.status = True
            self.message = "OK"
            self.filetype = cu.get_filetype(file_path)
            self.data_values = data_values
        else:
            self.descriptors = None
            self.path = None
            self.filetype = None
            self.data_values = None

    def load(self):
        """ Loads hise_file and downloads onto user's workspace. """
        if self.path is not None and os.path.exists(self.path):
            #already loaded
            return True

        obj = read_files([str(self.id)])
        if len(obj) == 0:
            raise TypeError("Failed to load file %s" % self.id)

        self.descriptors = obj[0].descriptors
        self.path = obj[0].path
        self.status = True
        self.message = "OK"


# TODO: refactor and expand logic to some mongo-human query translator class
def _add_prefix_to_query(user_query: dict):
    """ Takes user's query and adds the appropriate prefix to the field_names """
    # create data.frame of all queryable fields
    new_query_dict = user_query.copy()
    q_df = hl.lookup_queryable_fields()
    q_df = q_df.loc[~q_df[['field_type', 'field']].duplicated(),
                    ]  # drop duplicates
    # go through each key of user's dict and append the field_type as a prefix
    id_fields = [
        '{}.id'.format(i)
        for i in CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS']
    ]
    for k in list(new_query_dict):
        if k in id_fields:
            continue
        prefix = q_df.loc[q_df['field'].eq(k), 'field_type'].unique()[0]
        new_query_dict.update({'{}.{}'.format(prefix, k): new_query_dict[k]})

    # remove old keys
    for ok in list(user_query):
        if ok in id_fields:
            continue
        new_query_dict.pop(ok)
    return new_query_dict


# TODO: refactor and inlcude to future mongo query class
def _create_mongo_query_in(user_query: dict):
    """
    Takes a user's dictionary, and converts all entries and combines all 
    fields with boolean OR.
    """
    for key in user_query.keys():
        assert type(
            user_query[key]) == list, "key {} has values not in a list".format(
                key)

    # take the user's query and reformat it using mongo  query language
    user_query.update((k, {'$in': v}) for k, v in user_query.items())
    return user_query


def query_files(user_query: dict):
    """ 
    POST request to ledger by submitting user's query parameters
    
    Parameters:
        user_query (dict): dictionary where for each key:value pair, the value must be of type list.
    Returns:
        response payload
    Example: 
        query_files(user_query={'cohortGuid' : ['FH1']})
    """

    assert 'fileType' in user_query.keys(
    ), "fileType must be in your query dictionary"
    query_dict = user_query.copy()
    query_dict = _add_prefix_to_query(query_dict)
    for d in query_dict.keys():
        assert type(
            query_dict[d]) == list, "key {} has values not in a list".format(d)

    # take the user's query and reformat it using mongo  query language
    query_dict.update((k, {'$in': v}) for k, v in query_dict.items())

    endpoint = "https://{s}/{de}".format(
        s=get_from_metadata_server(server_id_path),
        de=CONFIG['LEDGER']['FILE_SEARCH_PATH'])
    resp = requests.post(endpoint,
                         data=json.dumps({"filter": query_dict}),
                         headers=get_bearer_token_header())
    obj = json.loads(resp.text)
    if type(obj) is not dict:
        raise TypeError("Response %s is not a list, it is a %s." %
                        (resp.text, type(obj)))
    elif "payload" not in obj:
        raise TypeError("Response %s contained an empty payload!" % resp.text)
    return obj["payload"]


def validate_user_query_fields(query):
    ''' Checks that keys of users' dictionary all are acceptable
    '''
    user_field_names = set(query.keys())
    acceptable_fields = hl.list_queryable_fields()
    setdiff = user_field_names.difference(acceptable_fields)
    if setdiff != set():
        raise Exception("""The following field names are invalid: {uf}. \n
        Valid field names you can use in your query are: {ac}
        """.format(uf=setdiff, ac=acceptable_fields))
    return


def get_file_descriptors(query_dict: dict = None):
    """ 
    Retrieves file descriptors based on user's query.

    Parameters:
        query_dict (dict): dictionary that contains query parameters
    Returns:
        dictionary of data.frame objects
    Examples:
        df_dict = get_file_descriptors(q_dict)
        df_dict.keys() # print keys of dict
        df_dict['descriptors'] # to view descriptors
        df_dict['labResults'] # lab results
        df_dict['specimens'] # specimen df
    """

    def _append_descriptors(dict_df, new_dict_desc):
        dict_df['descriptors'] = pd.concat(
            [new_dict_desc['descriptors'], dict_df['descriptors']], axis=0)
        dict_df['labResults'] = pd.concat(
            [new_dict_desc['labResults'], dict_df['labResults']], axis=0)
        dict_df['specimens'] = pd.concat(
            [new_dict_desc['specimens'], dict_df['specimens']], axis=0)
        return dict_df

    assert 'fileType' in query_dict.keys(
    ), 'fileType field must be in the your query dictionary.'
    # get a list of descriptor objects
    if query_dict is not None:
        validate_user_query_fields(query_dict)
    obj = query_files(query_dict)

    dict_df = {
        'descriptors': pd.DataFrame(),
        'labResults': pd.DataFrame(),
        'specimens': pd.DataFrame()
    }
    for this_desc in obj:
        try:
            dict_df = _append_descriptors(dict_df,
                                          hf.reshape_descriptors(this_desc))
        except:
            raise Exception(
                "appending descriptor failed. descriptor: {}".format(
                    this_desc))
    return dict_df


def post_query(file_list: list = None,
               query_id: str = None,
               query_dict: dict = None):
    """ 
    creates a response object from POST request to a Hydration endpoint
    Parameters:
        file_list : list
            - list of file_ids
        query_id : str
            - query_id obtained from HISE's Advanced Search
        query_dict : dict
            - dictionary that contains query parameters
    Output:
        obj : dict
            - JSON output from POST request
    """
    # make sure users only use 1 parameter
    if file_list is not None:
        assert (query_id is None) & (query_dict is None)
    elif query_id is not None:
        assert (file_list is None) & (query_dict is None)
    elif query_dict is not None:
        assert (file_list is None) & (query_id is None)

    if (file_list != None) & (type(file_list) is not list):
        raise TypeError("You must pass a list of file ids to read_files")

    # if user submits query, do the query and grab fileIds
    if query_dict is not None:
        payload = query_files(query_dict)
        file_list = []
        if payload is None:
            raise Exception("Query had no matching results")
        for i in range(0, len(payload)):
            file_list += [payload[i]['file']['id']]
        file_list = set(file_list)

    # if user submits a query_id, grab all fileIds associated with that query
    if query_id is not None:
        q_endpoint = 'https://{s}/{q}/{qid}'.format(
            s=get_from_metadata_server(server_id_path),
            q=CONFIG['HYDRATION']['QUERY_SEARCH_PATH'],
            qid=query_id)
        resp = requests.request('POST',
                                q_endpoint,
                                headers=get_bearer_token_header())
        resp_obj = json.loads(resp.text)
        file_list = []
        for o in resp_obj:
            file_list += [o['file']['id']]
        file_list = list(set(file_list))

    qstr = "&".join(map(lambda x: "id=%s" % x, file_list))
    endpoint = "https://%s/%s?%s" % (get_from_metadata_server(server_id_path),
                                     CONFIG['HYDRATION']['FILE_SEARCH_PATH'],
                                     qstr)
    resp = requests.request("GET", endpoint, headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError("Request to %s failed with status %d. %s" %
                          (endpoint, resp.status_code, resp.text))
    obj = json.loads(resp.text)
    if type(obj) is not list:
        raise TypeError("Response %s is not a list, it is a %s." %
                        (resp.text, type(obj)))
    return obj


def read_files(file_list: list = None,
               query_id: str = None,
               query_dict: dict = None,
               to_df: bool = True):
    """
    Read the contents of a list of file ids into a hise_file object
    Note: users should only use 1 parameter per function call

    Parameters:
        file_list (list): a list of UUIDS to retrieve
        query_id (str): string value of queryID from Advanced Search
        query_dict (dict): dictionary that allows users to submit a query.
            Note: for each key:value pair, the value must be of type list
        to_df (bool):  boolean determining whether result should be returned as a data.frame. 

    Returns:
        a list of hise_file objects

    Example: hp.read_files(file_list=['6cb2f536-2d20-4e66-b04d-327dce6870f4'])
    """
    obj = post_query(file_list, query_id, query_dict)
    #each object should be a set of descriptors and a url to download a file
    response = []
    idx = 0
    for f in obj:
        if "id" not in f:
            f["id"] = uuid.UUID(int=0)

        if "error" in f:
            fobj = hise_file(f['error']['File'])
            fobj.message = f["error"]["Message"]
            response.append(fobj)
            continue
        else:
            response.append(cache_and_convert_file_data(f))
            cu.log_downloaded_files(f)

            # if the response's fileId is different than the ID we original made the request with, then toolchain
            # noticed the request came from a guest account. if that's the case, we just log both files
            if f['descriptors']['file']["id"] != file_list[idx]:
                tmp_hise_file = copy.deepcopy(f)
                tmp_hise_file['descriptors']['file']["id"] = file_list[idx]
                cu.log_downloaded_files(tmp_hise_file)
        idx += 1

    # check if we have successfully read at least 1 file
    all_files_not_found = all(item.status is False for item in response)

    # find which files where there were errors
    # and print that information to the end-user
    files_not_found = [str(f.id) for f in response if f.status is False]
    if all_files_not_found:
        return response
    elif to_df:
        if len(files_not_found) > 0:
            print(
                colored(
                    "The following files failed to download: {}".format(
                        files_not_found), "red"))
        return hf.hise_file_to_df(response)
    else:
        return response


def download_files(file_dict: dict):
    """
    Read the contents of a dictionary of non-result file ids into hise_file objects
    These files will contain NULL descriptors (since they are not result files)

    Parameters:
        file_dict (dict): a dictionary of file_uuid: file_name

    Returns:
        a list of hise_file objects with empty descriptors

    """
    if type(file_dict) is not dict:
        raise TypeError(
            "You must pass a dictionary of file_uuid: file_name to download_files"
        )

    response = []
    #use a dummy batch id for these files
    download_cache = "%s/%s" % (CONFIG['IDE']['CACHE_DIR'], "downloadable")
    for f_id in file_dict:
        endpoint = "https://%s/%s/%s" % (get_from_metadata_server(
            server_id_path), CONFIG['HYDRATION']['DOWNLOAD_PATH'], f_id)
        hf = hise_file(f_id)
        try:
            cache_file(endpoint, file_dict[f_id], download_cache)
            hf.status = True
            hf.message = "OK"
            hf.path = "%s/%s" % (download_cache, file_dict[f_id])
        except Exception as e:
            hf.status = False
            hf.message = str(e)
        response.append(hf)

    return response


def cache_and_convert_file_data(file_data: dict):
    """ Helper function to convert files into a hise_file object """
    if type(file_data) is not dict:
        raise Exception("Item in response is not a dict, it is a %s." %
                        (type(file_data)))
    elif "descriptors" not in file_data:
        raise Exception("Descriptors not found in file data %s" % file_data)
    elif "url" not in file_data:
        raise Exception("No download url found in file data %s" % file_data)
    # always working with a single file-id at this point. but there may be multiple descriptor objects
    try:
        f_desc = file_data["descriptors"]["file"]
    except:
        f_desc = file_data['descriptors'][0]['file']

    batch_id = "unknown"
    if "batchID" in f_desc and f_desc["batchID"] != "":
        batch_id = f_desc["batchID"]
    file_dir = "%s/%s" % (CONFIG['IDE']['CACHE_DIR'], batch_id)
    file_name = f_desc["name"].split("/")[-1]
    this_filetype = cu.get_filetype(file_name)
    cache_file(file_data["url"], file_name, file_dir)
    this_file_values = hf.convert_data_values(
        '{}/{}'.format(file_dir, file_name), this_filetype)
    return hise_file(file_id=f_desc["id"],
                     file_path="%s/%s" % (file_dir, file_name),
                     descriptors=file_data["descriptors"],
                     file_type=this_filetype,
                     data_values=this_file_values)


def cache_files(file_ids: list = None, query_id: list = None):

    # verify input parameters are sane
    if file_ids is not None and type(file_ids) is not list:
        raise Exception("file_ids parameter must be a list")
    if query_id is not None and type(query_id) is not list:
        raise Exception("query_id parameter must be a list")
    if query_id is not None and len(query_id) > 1:
        raise Exception(
            "You can only specify a single query_if per function call")
    if file_ids is None and query_id is None:
        raise Exception("One of file_ids, or query_id must be non-null")

    # check if user submitted a query_id vs file_id
    if query_id is not None:
        # expand file_ids from query_id, if needed
        resp_obj = post_query(query_id=query_id[0])
    else:
        resp_obj = post_query(file_list=file_ids)

    # make request to hydration to download every file
    idx = 0
    for f in resp_obj:
        download_dir = '{h}/{c}/{id}'.format(h=CONFIG['IDE']['HOME_DIR'],
                                             c=CONFIG['IDE']['CACHE_DIR'],
                                             id=f['descriptors']['file']['id'])
        f_name = os.path.basename(f['descriptors']['file']['name'])
        cache_file(url=f['url'], file_name=f_name, file_dir=download_dir)

        # if the user passes in a file_list, make sure they didn't get redirected because they
        # downloaded from a guest account
        if file_ids is not None and f['descriptors']['file']["id"] != file_ids[
                idx]:
            tmp_hise_file = copy.deepcopy(f)
            tmp_hise_file['descriptors']['file']["id"] = file_ids[idx]
            cu.log_downloaded_files(tmp_hise_file)
        else:
            cu.log_downloaded_files(f)
        idx += 1
    print("Files have been successfully downloaded!")
    return


def cache_file(url: str, file_name: str, file_dir: str):
    if not os.path.exists(file_dir):
        pathlib.Path(file_dir).mkdir(parents=True, exist_ok=True)

    f_path = "%s/%s" % (file_dir, file_name)
    resp = requests.request("GET", url, headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError("Request to get file %s failed with status %d. %s" %
                          (file_name, resp.status_code, resp.text))
    open(f_path, 'wb').write(resp.content)
    return


def read_samples(sample_ids=None, query_dict=None, to_df=True):
    """
    Read or search the SampleStatus materialized view. User should specify one 
    or the other of sample_ids or query.

    Parameters:
        sample_ids (list): a list of UUIDS to retrieve.
        query_dict (dict): a dictionary object containing search 
            parameters using mongo query language.
        to_df (bool) : If true, returns a data.frame object

    Returns:
        response payload either in JSON or data.frame

    Example:
        hp.read_samples(sample_ids=['e82714e3-d0c9-46a1-9ea6-62a34cba3265'])

    """
    # check only 1 optional parameter is being assigned
    if sum(p is not None for p in [sample_ids, query_dict]) != 1:
        raise ValueError(
            "You must specify either sample_ids or query_dict, but not both.")
    if query_dict is not None:
        if type(query_dict) is not dict:
            raise TypeError('query_dict must be of type dictionary')
        # check that fields are within sample materialized view
        sample_fields = hl.lookup_queryable_fields(
            'sample')['field'].unique().tolist() + ['subjectGuid']
        query_fields = query_dict.keys()
        field_diff = set(query_fields) - set(sample_fields)
        assert field_diff == set(
        ), 'the following fields are not part of sample materialized view...{}'.format(
            field_diff)
        # modify user's query and convert to mongo query language
        qdict = query_dict.copy()
        qdict = _add_prefix_to_query(query_dict)
        # have to hardcode cohort
        if "cohort.cohortGuid" in qdict:
            qdict["subject.cohort"] = qdict["cohort.cohortGuid"]
            qdict.pop("cohort.cohortGuid")
        query = _create_mongo_query_in(qdict)
    elif sample_ids is not None:
        if type(sample_ids) is not list:
            raise TypeError("sample_ids must be a list")
        query = {"id": {"$in": sample_ids}}
    if query is None:
        raise TypeError(
            "You must specify either a list of sample_ids or a query")
    endpoint = "https://%s/%s" % (get_from_metadata_server(server_id_path),
                                  CONFIG['LEDGER']['SAMPLE_SEARCH_PATH'])
    resp = requests.post(endpoint,
                         data=json.dumps({"filter": query}),
                         headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError("Request to %s failed with status %d. %s" %
                          (endpoint, resp.status_code, resp.text))
    obj = json.loads(resp.text)
    if obj['payload'] is None:
        raise ValueError("User's query resulted in 0 results")
    if type(obj) is not dict:
        raise TypeError("Response %s is not a list, it is a %s." %
                        (resp.text, type(obj)))
    elif "payload" not in obj:
        raise TypeError("Response %s contained an empty payload!" % resp.text)
    if to_df:
        return hf.sample_to_df(obj["payload"])
    else:
        return obj['payload']


def read_subjects(subject_ids: str = None,
                  query_dict: dict = None,
                  to_df: bool = True):
    """
    Read or search the Subject materialized view.User should specify one or the 
    other of subject_ids or query

    Parameters:
        subject_ids (list): a list of UUIDS to retrieve
        query_dict (dict): a dictionary object containing search parameters 
            using mongo query language
        to_df (bool): If true, returns a data.frame 

    Returns:
        response payload as a data.frame or JSON 

    """
    if sum(p is not None for p in [subject_ids, query_dict]) != 1:
        raise ValueError(
            "You must specify either subject_ids or query_dict, but not both.")
    if query_dict is not None:
        # check that fields are within sample materialized view
        subject_fields = hl.lookup_queryable_fields('subject')['field']
        query_fields = query_dict.keys()
        field_diff = set(query_fields) - set(subject_fields)
        assert field_diff == set(
        ), 'the following fields are not part of sample materialized view...{}'.format(
            field_diff)

        # modify user's query and convert to mongo query language
        qdict = query_dict.copy()
        qdict = _add_prefix_to_query(query_dict)
        query = _create_mongo_query_in(qdict)
    elif subject_ids is not None:
        if type(subject_ids) is not list:
            raise TypeError("subject_ids must be a list")
        query = {"id": {"$in": subject_ids}}
    if query is None:
        raise TypeError(
            "You must specify either a list of subject_ids or a query")

    endpoint = "https://%s/%s" % (get_from_metadata_server(server_id_path),
                                  CONFIG['LEDGER']['SUBJECT_SEARCH_PATH'])
    resp = requests.post(endpoint,
                         data=json.dumps({"filter": query}),
                         headers=get_bearer_token_header())

    if resp.status_code != 200:
        raise SystemError("Request to %s failed with status %d. %s" %
                          (endpoint, resp.status_code, resp.text))

    obj = json.loads(resp.text)
    if obj['payload'] is None:
        raise ValueError("User's query resulted in 0 results")
    if type(obj) is not dict:
        raise TypeError("Response %s is not a list, it is a %s." %
                        (resp.text, type(obj)))
    elif "payload" not in obj:
        raise TypeError("Response %s contained an empty payload!" % resp.test)
    if to_df:
        return hf.subject_to_df(obj["payload"])
    else:
        return obj["payload"]


def get_server(service):
    test_hydration_server = os.getenv("TEST_HYDRATION_SERVER")
    test_toolchain_server = os.getenv("TEST_TOOLCHAIN_SERVER")
    test_tracer_server = os.getenv("TEST_TRACER_SERVER")
    if service == "hydration" and test_hydration_server is not None:
        return test_hydration_server
    elif service == "toolchain" and test_toolchain_server is not None:
        return test_toolchain_server
    elif service == "tracer" and test_tracer_server is not None:
        return test_tracer_server
    else:
        return get_from_metadata_server(server_id_path)


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


def list_filesets(study_space_id):
    """ 
    Returns a list of filesets for a given study 

    Parameters:
        study_space_id (str) : a unique identifier for a study in the collaboration space

    Returns: 
        data.frame with columns ['id', 'studySpaceId', 'title','description','fileIds']
        
    Example: 
        hp.list_filesets(study_space_id='c39e3ae5-ec11-4f02-b89d-255945c5788e')
    """
    # get me all the filesets
    query_dict = {'studySpaceId': study_space_id}
    obj = parse_hise_response(
        requests.get(hise_url('tracer', 'file_set'),
                     params=query_dict,
                     headers=get_bearer_token_header()))

    # transform to a data.frame
    obj_df = pd.DataFrame(obj)
    if len(obj_df) == 0:
        raise ValueError("There are no filesets in the study specified")

    # don't show users deleted entries
    obj_df_sub = obj_df.loc[obj_df['deleted'].eq('false'), ]
    return obj_df_sub[[
        'id', 'studySpaceId', 'title', 'description', 'fileIds'
    ]].reset_index(drop=True)


def cache_filesets(fileset_id, study_space_id):
    """ 
    Downloads all files pertaining to a fileset to a user's workspace.

    Parameters: 
        fileset_id (str) : unique identifier for a fileset in a study
        study_space_id (str) : unique identifier for a study in the collaboration space

    Example:
        hp.cache_filesets(fileset_title='Reports on why this study is worth it', 
                            study_space_id='a9ddcfa9-e36d-451e-9e00-0f582e09e696')
    """
    assert fileset_id is not None, "You must specify a fileset_id"
    assert study_space_id is not None, "You must specify a study_space_id"
    assert type(fileset_id) is str, "fileset_id must be of type string"
    assert type(study_space_id) is str, "study_space_id must be of type string"

    # get all the fileIds to download
    fileset_df = list_filesets(study_space_id)
    if fileset_id is not None:
        fileset_df_sub = fileset_df.loc[fileset_df['id'].eq(fileset_id), ]
        these_file_ids = list(fileset_df_sub['fileIds'].item().keys())
        fileset_title = str(fileset_df_sub['title'].item())

    # make sure we only have a single fileSet entry we're downloading from
    if len(fileset_df_sub) == 0:
        raise ValueError(
            "There is no fileset entry with the title and study specified")

    # make requests to hydration
    obj = post_query(file_list=these_file_ids)

    # save all files in ~/cache/<filesetName>/...
    cache_dir = "%s/%s" % (CONFIG['IDE']['CACHE_DIR'], fileset_title)
    for this_obj in obj:
        # split filepath string into path and filename.
        split_filename = os.path.split(this_obj['descriptors']['file']['name'])
        this_file_id = this_obj['descriptors']['file']['id']
        this_filename = split_filename[1]
        cache_file(
            url=this_obj['url'],
            file_name=this_filename,  # just grab the filename (could be a path)
            file_dir="%s/%s" % (cache_dir, this_file_id))

    return
