import json
import os
import pathlib
import urllib
import uuid

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
    for k in list(new_query_dict):
        prefix = q_df.loc[q_df['field'].eq(k), 'field_type'].unique()[0]
        new_query_dict.update({'{}.{}'.format(prefix, k): new_query_dict[k]})

    # remove old keys
    for ok in list(user_query):
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
        raise TypeError("Response %s contained an empty payload!" % resp.test)
    return obj["payload"]


def get_file_descriptors(
        file_list: list = None,
        query_id: str = None,
        query_dict: dict = None):  # TBD on actual name of this
    """ 
    Retrieves file descriptors based on user's query.

    Parameters:
        file_list (list): list of file_ids
        query_id (str): query_id obtained from HISE's Advanced Search
        query_dict (dict): dictionary that contains query parameters
    Returns:
        dictionary of data.frame objects
    Examples:
        df_dict = get_file_descriptors(file_list)
        df_dict.keys() # print keys of dict
        df_dict['descriptors'] # to view descriptors
        df_dict['labResults'] # lab results
        df_dict['specimens'] # specimen df
    """
    obj = post_query(file_list, query_id, query_dict)

    # do parsing
    hise_file_list = []
    for f in obj:
        batch_id = "unknown"
        if "batchID" in f['descriptors'][
                'file'] and f['descriptors']['file']["batchID"] != "":
            batch_id = f['descriptors']['file']["batchID"]
        file_dir = "%s/%s" % (CONFIG['IDE']['CACHE_DIR'], batch_id)
        file_name = f['descriptors']['file']["name"].split("/")[-1]
        filetype = cu.get_filetype(file_name)
        hise_file_list += [
            hise_file(file_id=f['descriptors']['file']['id'],
                      file_path=file_dir,
                      descriptors=f["descriptors"],
                      file_type=filetype)
        ]
    desc_df = hf.descriptors_to_df(hise_file_list)
    return desc_df


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
        for i in range(0, len(payload)):
            file_list += [payload[i]['file']['id']]

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
    for f in obj:
        if "id" not in f:
            f["id"] = uuid.UUID(int=0)

        if "error" in f:
            fobj = hise_file(f["id"])
            fobj.message = f["error"]["Message"]
            response.append(fobj)
            continue
        else:
            response.append(cache_and_convert_file_data(f))
    cu.log_downloaded_files(response)
    if to_df:
        return hf.descriptors_to_df(response)
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


def cache_file(url: str, file_name: str, file_dir: str):
    if not os.path.exists(file_dir):
        pathlib.Path(file_dir).mkdir(parents=True, exist_ok=True)

    f_path = "%s/%s" % (file_dir, file_name)
    resp = requests.request("GET", url, headers=get_bearer_token_header())
    if resp.status_code != 200:
        raise SystemError(
            "Request to get file %s from %s failed with status %d. %s" %
            (file_name, resp.status_code, resp.text))
    open(f_path, 'wb').write(resp.content)


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
        raise TypeError("Response %s contained an empty payload!" % resp.test)
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
