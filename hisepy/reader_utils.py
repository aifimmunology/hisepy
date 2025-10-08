import os
import copy
import json
import requests
import pathlib
import uuid
import time
from hisepy.auth import get_bearer_token_header, hise_server
import hisepy.lookup as hl
import hisepy.common_utils as cu
import hisepy.formatter as hf

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
        q_df = q_df.loc[
            ~q_df[['field_type', 'field']].duplicated(),
        ]

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


def append_error_response(response: list, file_meta: dict, message: str,
                          idx: int):
    """Append an error placeholder hise_file to the response list."""
    try:
        fobj = hise_file(file_meta.get("file", {}).get("name", "unknown"))
    except Exception:
        fobj = hise_file("unknown")
    fobj.status = False
    fobj.message = message
    response.append(fobj)


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
        cache_file(file_data["url"], file_name,
                   '{}/{}'.format(CONFIG['IDE']['HOME_DIR'], file_dir))
        this_file_values = hf.convert_data_values(
            '{}/{}'.format(file_dir, file_name), this_filetype)
    return hise_file(file_id=f_desc["id"],
                     file_path="%s/%s" % (file_dir, file_name),
                     descriptors=f_desc,
                     file_type=this_filetype)


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
                     file_path='{}/{}'.format(CONFIG['IDE']['HOME_DIR_V2'],
                                              path_to_file),
                     descriptors=f_desc,
                     file_type=this_filetype,
                     data_values=this_file_values)


def count_payload_entries(query: dict):
    """
    """
    count_endpoint = "https://{s}/{de}?_count=true".format(
        s=hise_server(), de=CONFIG['LEDGER']['FILE_SEARCH_PATH'])
    count = cu.parse_hise_response(
        requests.post(count_endpoint,
                      data=json.dumps({"filter": query}),
                      headers=get_bearer_token_header()))
    return count['payload']


def gen_read_samples_subjects_query(ids_list: list = None,
                                    query_dict: dict = None,
                                    is_sample_query: bool = True):
    """
    Generates a query for the SampleStatus materialized view.
    """
    if query_dict is not None:
        # modify user's query and convert to mongo query language
        mg_instance = MongoQuery(query_dict)
        query = mg_instance.query_dict_to_mongo_query(
            mg_instance.add_prefix_to_query())

        # have to hardcode cohort
        # TODO: sanity check that this is still needed after refactor
        if "cohort.cohortGuid" in query and is_sample_query:
            query["subject.cohort"] = query["cohort.cohortGuid"]
            query.pop("cohort.cohortGuid")
    elif ids_list is not None:
        query = {"id": {"$in": ids_list}}
    return query


def log_replica_file_download(hise_file, file_id: str, ide_dir: str):
    """
    Creates another log entry. If a file was downloaded in a guest workspace, then the replica fileID is logged

    Parameters:
        hise_file (hise_file): hisepy.reader.hise_file object
        file_id (str): original file_id that's passed in to read_files() or cache_files()
    """
    this_file_id, this_file_name, _ = parse_file_descriptor_from_hise_file(
        hise_file)
    if (this_file_id != file_id):
        tmp_hise_file = copy.deepcopy(hise_file)
        cu.log_downloaded_files(file_id, None, ide_dir, this_file_id, None)
    return


def parse_file_descriptor_from_hise_file(hise_file):
    """
    Takes a hise_file object and returns its file_id, file_name and the descriptor object

    Parameters:
        hise_file (hise_file): hisepy.reader.hise_file object
    Returns:
        a tuple (file_id, file_name, descriptor object)
    """
    if type(hise_file['descriptors']) is list:
        this_file_id = hise_file['descriptors'][0]['file']['id']
        this_file_name = hise_file['descriptors'][0]['file']['name']
        this_desc = hise_file['descriptors'][0]
    elif type(hise_file['descriptors']) is dict:
        this_file_id = hise_file['descriptors']['file']['id']
        this_file_name = hise_file['descriptors']['file']['name']
        this_desc = hise_file['descriptors']
    return this_file_id, this_file_name, this_desc


def parse_file_id_from_hise_file(hise_file):
    """
    Takes a hise_file object and returns the file_id

    Parameters:
        hise_file (hise_file): hisepy.reader.hise_file object
    Returns:
        a string file_id
    """
    # descriptors can have > 1 entry if filetype == Olink
    if type(hise_file['descriptors']) is list:
        this_file_id = hise_file['descriptors'][0]['file']['id']
    elif type(hise_file['descriptors']) is dict:
        this_file_id = hise_file['descriptors']['file']['id']
    return this_file_id


def post_query(
    file_list: list[str] | None = None,
    query_id: str | None = None,
    query_dict: dict[str, any] | None = None,
) -> list[dict[str, any]]:
    """
    Create a response object from POST request to the Hydration endpoint.
    """
    # validate params
    validate_post_query_params(file_list, query_id, query_dict)

    try:
        if query_dict is not None:
            payload = query_files(query_dict)
            if not payload:
                raise LookupError("Query had no matching results.")
            file_list = {item["file"]["id"] for item in payload}

        elif query_id is not None:
            q_endpoint = f"https://{hise_server()}/{CONFIG['HYDRATION']['QUERY_SEARCH_PATH']}/{query_id}"
            resp = requests.post(q_endpoint, headers=get_bearer_token_header())
            resp_obj = cu.parse_hise_response(resp)
            file_list = {o["file"]["id"] for o in resp_obj}

        elif file_list is not None:
            file_list = set(file_list)

        else:
            raise ValueError("No valid query parameters provided.")

        # submit GET request
        qstr = "&".join(f"id={fid}" for fid in file_list)
        endpoint = f"https://{hise_server()}/{CONFIG['HYDRATION']['FILE_SEARCH_PATH']}?{qstr}"
        obj = cu.parse_hise_response(
            requests.get(endpoint, headers=get_bearer_token_header()))

        if not isinstance(obj, list):
            raise TypeError(
                f"Response is {type(obj).__name__}, expected list.")

        return obj

    except requests.RequestException as e:
        raise SystemError(
            f"Network error while calling Hydration API: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to decode JSON response: {e}") from e


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

    # count how many entries are in query
    count = count_payload_entries(formatted_query)
    obj = submit_file_descriptor_request(formatted_query, count)
    return obj['payload']


def submit_file_descriptor_request(formatted_query: dict, count: int):

    # paginate/chunk if count is greater than pagination_size we set in config
    if count > CONFIG['IDE']['PAGINATION_SIZE']:
        obj = submit_paginated_query(formatted_query, count)
    else:
        endpoint = "https://{s}/{de}".format(
            s=hise_server(), de=CONFIG['LEDGER']['FILE_SEARCH_PATH'])
        obj = cu.parse_hise_response(
            requests.post(endpoint,
                          data=json.dumps({"filter": formatted_query}),
                          headers=get_bearer_token_header()))
    return obj


def submit_paginated_query(query: dict, number_entries: int):
    """
    """

    # determine how many chunks
    page_size = CONFIG['IDE']['PAGINATION_SIZE']
    obj = {'payload': []}
    num_chunks = math.ceil(number_entries / page_size)
    for i in range(0, num_chunks):
        endpoint = "https://{s}/{de}?page_size={ps}&page_number={pn}".format(
            s=hise_server(),
            de=CONFIG['LEDGER']['FILE_SEARCH_PATH'],
            ps=page_size,
            pn=i + 1)
        this_chunk = cu.parse_hise_response(
            requests.post(endpoint,
                          data=json.dumps({"filter": query}),
                          headers=get_bearer_token_header()))
        obj['payload'] += this_chunk['payload']
    return obj


def validate_download_params(file_list: list, query_id: list,
                             query_dict: dict):
    # verify input parameters are sane
    if file_list is not None:
        if type(file_list) is not list:
            raise Exception("file_ids parameter must be a list")
        if query_id is not None and query_dict is not None:
            raise Exception(
                "You can only specify one of file_list, query_id, or query_dict per function call"
            )
    if query_id is not None:
        if type(query_id) is not list:
            raise Exception("query_id parameter must be a list")
        if len(query_id) > 1:
            raise Exception(
                "You can only specify a single query_id per function call")
        if file_list is not None or query_dict is not None:
            raise Exception(
                "You can only specify one of file_list, query_id, or query_dict per function call"
            )
    if query_dict is not None:
        if type(query_dict) is not dict:
            raise Exception("query_dict parameter must be a dictionary")
        for d in query_dict.keys():
            if type(query_dict[d]) is not list:
                raise Exception("query dictionary values must be of type list")
        if file_list is not None or query_id is not None:
            raise Exception(
                "You can only specify one of file_list, query_id, or query_dict per function call"
            )
        if "fileType" not in query_dict:
            raise Exception("query_dict must include fileType")
    if file_list is None and query_id is None and query_dict is None:
        raise Exception(
            "One of file_ids, query_dict, or query_id must be non-null")
    return True


def validate_post_query_params(
    file_list: list | None = None,
    query_id: str | None = None,
    query_dict: dict | None = None,
) -> bool:
    """ Validates user's query parameters for POST request to ledger"""

    # ensure exactly one parameter is provided
    provided = [p for p in (file_list, query_id, query_dict) if p is not None]
    if len(provided) == 0:
        raise ValueError(
            "You must provide one of file_list, query_id, or query_dict.")
    if len(provided) > 1:
        raise ValueError(
            "You must only use one of file_list, query_id, or query_dict.")

    # type checks
    if file_list is not None and not isinstance(file_list, list):
        raise TypeError("file_list must be a list of file IDs.")
    if query_id is not None and not isinstance(query_id, str):
        raise TypeError("query_id must be a string.")
    if query_dict is not None and not isinstance(query_dict, dict):
        raise TypeError("query_dict must be a dictionary.")

    return True


def validate_samples_subjects_params(ids_list: list = None,
                                     query_dict: dict = None):
    """
    Validates user's query parameters for POST request to ledger
    """
    if (ids_list is None) == (query_dict is None):
        raise TypeError(
            "Specify either `ids_list` or `query_dict`, but not both.")
    if ids_list is not None:
        if type(ids_list) is not list:
            raise ValueError("ids must be in a list")
    elif query_dict is not None:
        if type(query_dict) is not dict:
            raise ValueError("query_dict must be of type dict")
    return True


def wait_for_file(filepath: str, timeout: int = 60, interval: int = 3):
    """Wait until file exists on disk, with timeout."""
    start = time.time()
    while not os.path.exists(filepath):
        if time.time() - start > timeout:
            raise TimeoutError(f"Timed out waiting for {filepath} to appear.")
        print("Waiting for file to download...")
        time.sleep(interval)
