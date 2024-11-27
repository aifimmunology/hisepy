import json
import os
import pathlib
import urllib
import uuid
import pandas as pd
import copy
from termcolor import colored

import requests
from hisepy.instances import IDEInstance
import hisepy.common_utils as cu
import time
import hisepy.formatter as hf
import hisepy.lookup as hl
from hisepy.auth import get_bearer_token_header, hise_server, debug

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


# TODO: flesh this out more if we want to enable power users even more
# as of now, users don't get to use this class directly, but we could allow them to
# create their own query w/ different operators
class MongoQuery:  # class to handle mongo query language translation

    def __init__(self, query_dict):
        if self.validate_query_dict(query_dict):
            self.query_dict = query_dict

        # take user's query and apply metadata scheme to it
        # TODO: this is gonna need to be updated to handle generalized metadata scheme
        # self.prefixed_query = self._add_prefix_to_query()

    # TODO: generalized metadata scheme will need to be implemented here
    def add_prefix_to_query(self):
        """ Takes user's query and adds the appropriate prefix to the field_names """
        # create data.frame of all queryable fields
        new_query_dict = self.query_dict.copy()
        q_df = hl.lookup_queryable_fields()
        q_df = q_df.loc[~q_df[['field_type', 'field']].duplicated(), ]

        # go through each key of user's dict and append the field_type as a prefix
        id_fields = [
            '{}.id'.format(i)
            for i in CONFIG['MATERIALIZED_VIEW']['QUERYABLE_FIELDS']
        ]
        for k in list(new_query_dict):
            # if it's an id field, skip
            if k in id_fields:
                continue
            prefix = q_df.loc[q_df['field'].eq(k), 'field_type'].unique()[0]
            new_query_dict.update(
                {'{}.{}'.format(prefix, k): new_query_dict[k]})

        # remove old keys
        for ok in list(self.query_dict):
            if ok in id_fields:
                continue
            new_query_dict.pop(ok)
        return new_query_dict

    def validate_query_dict(self, query_dict):
        for d in query_dict.keys():
            if type(query_dict[d]) is not list:
                raise Exception("query dictionary values must be of type list")

        # TODO: this part of the validation is gonna need to be able to handle
        # generalized metadata scheme in the near future
        user_field_names = set(query_dict.keys())
        acceptable_fields = hl.list_queryable_fields()
        setdiff = user_field_names.difference(acceptable_fields)
        if setdiff != set() and not debug():
            raise Exception("""The following field names are invalid: {uf}. \n
            Valid field names you can use in your query are: {ac}
            """.format(uf=setdiff, ac=acceptable_fields))
        return True

    # translate user's query dictionary to mongo query language
    def query_dict_to_mongo_query(self,
                                  query_dict: dict,
                                  operators: list = None):
        if operators is None:
            operators = ['in'] * len(query_dict)
        assert len(operators) == len(
            query_dict), "operators must be of same length as query_dict"

        # take the user's query and reformat it using mongo  query language
        idx = 0
        for k, v in query_dict.items():
            if operators[idx] == 'in':
                query_dict.update({k: {'$in': v}})
            elif operators[idx] == 'or':
                query_dict.update({k: {'$or': v}})
            elif operators[idx] == 'and':
                query_dict.update({k: {'$and': v}})
            elif operators[idx] == 'not':
                query_dict.update({k: {'$not': v}})
            idx += 1
        return query_dict

    # methods to handle boolean query logic
    def create_mongo_query_in(self):
        return

    def create_mongo_query_or(self):
        return

    def create_mongo_query_and(self):
        return

    def create_mongo_query_not(self):
        return


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

    query_instance = MongoQuery(user_query)
    formatted_query = query_instance.query_dict_to_mongo_query(
        query_instance.add_prefix_to_query())
    endpoint = "https://{s}/{de}".format(
        s=hise_server(), de=CONFIG['LEDGER']['FILE_SEARCH_PATH'])
    obj = cu.parse_hise_response(
        requests.post(endpoint,
                      data=json.dumps({"filter": formatted_query}),
                      headers=get_bearer_token_header()))
    return obj['payload']


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


def validate_post_query_params(file_list: list = None,
                               query_id: str = None,
                               query_dict: dict = None):
    """ 
    Validates user's query parameters for POST request to ledger
    """
    # make sure users only use 1 parameter
    assert file_list is not None or query_id is not None or query_dict is not None, "One of file_ids, query_dict, or query_id must be a non-null"
    if file_list is not None:
        assert type(file_list) is list
        assert (query_id is None) and (query_dict is
                                       None), "You must only use 1 parameter"
    elif query_id is not None:
        assert type(query_id) is str
        assert (file_list is None) and (query_dict is
                                        None), "You must only use 1 parameter"
    elif query_dict is not None:
        assert type(query_dict) is dict
        assert (file_list is None) and (query_id is
                                        None), "You must only use 1 parameter"

    if (file_list != None) & (type(file_list) is not list):
        raise TypeError("You must pass a list of file ids to read_files")

    return True


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
    # validate params
    assert validate_post_query_params(
        file_list, query_id, query_dict), "failed to validate query parameters"

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
            s=hise_server(),
            q=CONFIG['HYDRATION']['QUERY_SEARCH_PATH'],
            qid=query_id)
        resp_obj = cu.parse_hise_response(
            requests.request('POST',
                             q_endpoint,
                             headers=get_bearer_token_header()))
        file_list = []
        for o in resp_obj:
            file_list += [o['file']['id']]
        file_list = list(set(file_list))

    qstr = "&".join(map(lambda x: "id=%s" % x, file_list))
    endpoint = "https://%s/%s?%s" % (
        hise_server(), CONFIG['HYDRATION']['FILE_SEARCH_PATH'], qstr)
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
               query_id: list = None,
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

    # grab descriptors for requested files.
    # if we get returned descriptors, users are allowed to download the files
    cu.validate_download_params(file_list, query_id, query_dict)
    if query_id != None:
        if cu.prompt_user(CONFIG["PROMPTS"]["QUERY_ID_READ"]):
            obj = post_query(query_id=query_id[0])
        else:
            print("Canceling read_files call")
            return
    elif query_dict != None:
        if 'fileType' not in query_dict.keys() and not debug():
            raise Exception("fileType must be in your query dictionary")
        if cu.prompt_user(CONFIG["PROMPTS"]["QUERY_DICT_READ"]):
            obj = post_query(query_dict=query_dict)
        else:
            print("Canceling read_files call")
            return
    else:

        obj = post_query(file_list=file_list)

    # send request to hydration to download every file
    idx = 0
    response = []
    ide_name = IDEInstance().podName
    for f in obj:
        if "id" not in f:
            f["id"] = uuid.UUID(int=0)
        if "error" in f:
            fobj = hise_file(f['error']['File'])
            fobj.message = f["error"]["Message"]
            response.append(fobj)
            idx += 1
            continue
        else:
            # parse descriptors with info we need to send our request
            this_file_id, this_file_name, this_desc = cu.parse_file_descriptor_from_hise_file(
                f)

            endpoint = "https://%s/%s/%s/%s" % (hise_server(
            ), CONFIG['HYDRATION']['DOWNLOAD_PATHV2'], this_file_id, ide_name)
            # download the file to user's IDE
            try:
                dl_resp = requests.request("GET",
                                           endpoint,
                                           headers=get_bearer_token_header())
                parsed_dl_resp = cu.parse_hise_response(dl_resp)
                download_filepath = '{}/{}'.format(
                    CONFIG['IDE']['HOME_DIR_V2'], parsed_dl_resp['Path'])
                # if we succeeded, continually check for the file in /inputs
                if dl_resp.status_code == 200:
                    while (not os.path.exists(download_filepath)):
                        time.sleep(3)
                        print("Waiting for file to download...")
                    response.append(
                        convert_file_data(f, parsed_dl_resp['Path']))
                response[idx].status = True
                response[idx].descriptors = this_desc
                response[idx].message = "OK"
                cu.log_downloaded_files(f, CONFIG['STORES']['TEMP_STORE'])

                # if the user passes in a file_list, make sure they didn't get redirected because they
                # downloaded from a guest account
                if file_list is not None:
                    this_file_id = file_list[idx]
                    cu.log_replica_file_download(
                        f, this_file_id, CONFIG['STORES']['TEMP_STORE'])
            except:
                response[idx].status = False
                response[idx].message = "Failed to download file"
                idx += 1
                continue

        idx += 1

    # find which files where there were errors
    # and print that information to the end-user
    files_not_found = [str(f.id) for f in response if f.status is False]
    if to_df:
        if len(files_not_found) > 0:
            print(
                colored(
                    "The following files failed to download: {}".format(
                        files_not_found), "red"))
        return hf.hise_file_to_df(response)
    else:
        return response


def read_files_v1(file_list: list = None,
                  query_id: list = None,
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
    cu.validate_download_params(file_list, query_id, query_dict)
    if query_id != None:
        obj = post_query(query_id=query_id[0])
    elif query_dict != None:
        obj = post_query(query_dict=query_dict)
    else:
        obj = post_query(file_list=file_list)
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
            cu.log_downloaded_files(f, CONFIG["IDE"]["HOME_DIR"])

            # if the response's fileId is different than the ID we original made the request with, then toolchain
            # noticed the request came from a guest account. if that's the case, we just log both files
            if file_list is not None:
                this_file_id = file_list[idx]
                cu.log_replica_file_download(f, this_file_id,
                                             CONFIG["IDE"]["HOME_DIR"])
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


def convert_file_data(file_data: dict, path_to_file: str):
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
    file_name = f_desc["name"].split("/")[-1]
    this_filetype = cu.get_filetype(file_name)
    this_file_values = hf.convert_data_values(
        '{}/{}'.format(CONFIG['IDE']['HOME_DIR_V2'], path_to_file),
        this_filetype)
    return hise_file(file_id=f_desc["id"],
                     file_path=path_to_file,
                     descriptors=f_desc,
                     file_type=this_filetype,
                     data_values=this_file_values)


def cache_and_convert_file_data(file_data: dict, do_cache: bool = True):
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
    if do_cache:
        cache_file(file_data["url"], file_name, file_dir)
        this_file_values = hf.convert_data_values(
            '{}/{}'.format(file_dir, file_name), this_filetype)
    return hise_file(file_id=f_desc["id"],
                     file_path="%s/%s" % (file_dir, file_name),
                     descriptors=f_desc,
                     file_type=this_filetype)


def cache_files_v1(file_ids: list = None,
                   query_id: list = None,
                   query_dict: dict = None):
    """ 
    Downloads requested files to the following directory: "./cache/<fileID>"
    Parameters: 
        file_ids (list): list of file IDs
        query_id (list): list of a single query ID
    """
    cu.validate_download_params(file_ids, query_id, query_dict)
    # check if user submitted a query_id vs file_id
    if query_id is not None:
        # expand file_ids from query_id, if needed
        resp_obj = post_query(query_id=query_id[0])
    elif query_dict is not None:
        resp_obj = post_query(query_dict=query_dict)
    else:
        resp_obj = post_query(file_list=file_ids)

    # make request to hydration to download every file
    idx = 0
    fail_files = []
    for f in resp_obj:
        if 'error' in f:
            print("Error downloading file: {}".format(f['error']['Message']))
            fail_files += [f['error']['File']]
            continue

        this_file_id, this_file_name, this_desc = cu.parse_file_descriptor_from_hise_file(
            f)
        download_dir = '{h}/{c}/{id}'.format(h=CONFIG['IDE']['HOME_DIR'],
                                             c=CONFIG['IDE']['CACHE_DIR'],
                                             id=this_file_id)
        f_name = os.path.basename(this_file_name)
        print("downloading fileID: {}".format(this_file_id))
        cache_file(url=f['url'], file_name=f_name, file_dir=download_dir)
        cu.log_downloaded_files(f, CONFIG["IDE"]["HOME_DIR"])

        # if the user passes in a file_list, make sure they didn't get redirected because they
        # downloaded from a guest account
        if file_ids is not None:
            this_file_id = file_ids[idx]
            cu.log_replica_file_download(f, this_file_id,
                                         CONFIG["IDE"]["HOME_DIR"])

        idx += 1

    # alert user which files failed to download
    if len(fail_files) > 0:
        print("The following files failed to download: {}".format(fail_files))
    else:
        print("Files have been successfully downloaded!")
    return


def cache_files(file_ids: list = None,
                query_id: list = None,
                query_dict: dict = None):
    """ 
    Downloads requested files to the following directory: "./cache/<fileID>" # TODO: update path example 
    Parameters: 
        file_ids (list): list of file IDs
        query_id (list): list of a single query ID
    """
    cu.validate_download_params(file_ids, query_id, query_dict)
    # check if user submitted a query_id vs file_id
    if query_id is not None:
        # expand file_ids from query_id, if needed
        resp_obj = post_query(query_id=query_id[0])
    elif query_dict is not None:
        resp_obj = post_query(query_dict=query_dict)
    else:
        # TODO: don't need to call this since we already have the file_ids..
        # something to handle during refactoring
        resp_obj = post_query(file_list=file_ids)

    idx = 0
    fail_files = []
    dl_paths = []
    ide_name = IDEInstance().podName
    for f in resp_obj:
        if 'error' in f:
            print("Error downloading file: {}".format(f['error']['Message']))
            fail_files += [f['error']['File']]
            continue
        this_file_id, _, _ = cu.parse_file_descriptor_from_hise_file(f)
        endpoint = "https://%s/%s/%s/%s" % (hise_server(
        ), CONFIG['HYDRATION']['DOWNLOAD_PATHV2'], this_file_id, ide_name)
        dl_resp = cu.parse_hise_response(
            requests.request("GET",
                             endpoint,
                             headers=get_bearer_token_header()))

        cu.log_downloaded_files(f, CONFIG["STORES"]["TEMP_STORE"])

        # if the user passes in a file_list, make sure they didn't get redirected because they
        # downloaded from a guest account
        if file_ids is not None:
            this_file_id = file_ids[idx]
            cu.log_replica_file_download(f, this_file_id,
                                         CONFIG["STORES"]["TEMP_STORE"])
        this_path = "%s/%s" % (CONFIG['IDE']['HOME_DIR_V2'], dl_resp['Path'])
        dl_paths.append(this_path)
        idx += 1
    return dl_paths


def cache_file(url: str, file_name: str, file_dir: str):
    if not os.path.exists(file_dir):
        pathlib.Path(file_dir).mkdir(parents=True, exist_ok=True)

    f_path = "%s/%s" % (file_dir, file_name)
    with requests.request("GET",
                          url,
                          headers=get_bearer_token_header(),
                          stream=True) as resp:
        if resp.status_code != 200:
            raise SystemError(
                "Request to get file %s failed with status %d. %s" %
                (file_name, resp.status_code, resp.text))
        else:
            with open(f_path, 'wb') as file:
                for chunk in resp.iter_content(
                        chunk_size=CONFIG['IDE']["DOWNLOAD_CHUNK_SIZE"]):
                    file.write(chunk)


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
        endpoint = "https://%s/%s/%s" % (
            hise_server(), CONFIG['HYDRATION']['DOWNLOAD_PATH'], f_id)
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
        mg_instance = MongoQuery(query_dict)
        query = mg_instance.query_dict_to_mongo_query(
            mg_instance.add_prefix_to_query())
        #qdict = query_dict.copy()
        #qdict = _add_prefix_to_query(query_dict)
        # have to hardcode cohort
        if "cohort.cohortGuid" in query:
            query["subject.cohort"] = query["cohort.cohortGuid"]
            query.pop("cohort.cohortGuid")
    elif sample_ids is not None:
        if type(sample_ids) is not list:
            raise TypeError("sample_ids must be a list")
        query = {"id": {"$in": sample_ids}}
    if query is None:
        raise TypeError(
            "You must specify either a list of sample_ids or a query")
    endpoint = "https://%s/%s" % (hise_server(),
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

        # TODO: refactor to its' own validation function
        subject_fields = hl.lookup_queryable_fields('subject')['field']
        query_fields = query_dict.keys()
        field_diff = set(query_fields) - set(subject_fields)
        assert field_diff == set(
        ), 'the following fields are not part of sample materialized view...{}'.format(
            field_diff)

        # modify user's query and convert to mongo query language
        mg_instance = MongoQuery(query_dict)
        query = mg_instance.query_dict_to_mongo_query(
            mg_instance.add_prefix_to_query())

    elif subject_ids is not None:
        if type(subject_ids) is not list:
            raise TypeError("subject_ids must be a list")
        query = {"id": {"$in": subject_ids}}
    if query is None:
        raise TypeError(
            "You must specify either a list of subject_ids or a query")

    endpoint = "https://%s/%s" % (hise_server(),
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
    obj = cu.parse_hise_response(
        requests.get(cu.hise_url('tracer', 'file_set'),
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
