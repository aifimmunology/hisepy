import os
import copy
import json
import requests
import pathlib
import uuid
import time
import math
from hisepy.instances import IDEInstance
from hisepy.auth import get_bearer_token_header, hise_server, debug
import hisepy.lookup as hl
import hisepy.common_utils as cu
import hisepy.formatter as hf
from hisepy.logging import with_default_logging, logger

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


@with_default_logging
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

    def __init__(self, query_dict, is_public=False):
        self.is_public = is_public
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
        q_df = hl.lookup_queryable_fields(is_public=self.is_public)
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
        acceptable_fields = hl.list_queryable_fields(is_public=self.is_public)
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
        fobj = hise_file(file_id=file_meta['descriptors']['file']['id'])
    except Exception:
        fobj = hise_file(uuid.UUID(int=0))
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


def availability_matches_is_public(file_id: str, is_public: bool):
    fm = get_file_metadata(file_id)
    availability = fm.get("availability", "unknown")

    # file is public but user did not set is_public to True
    if is_public_file(availability) and not is_public:
        print(
            f"File {file_id} is public and will be skipped. Set is_public=True to download this file."
        )
        return False

    # file is not public but user set is_public to True
    if not is_public_file(availability) and is_public:
        print(
            f"File {file_id} is not a public file and will be skipped. Do not set is_public or set is_public=False to download this file."
        )
        return False
    return True


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


def cache_files_using_descriptors(file_descriptors: list[dict]):
    """ Helper function to cache files using file descriptors from ledger response """
    dl_paths: List[str] = []
    fail_files: List[str] = []
    ide_name = IDEInstance().podName
    for idx, f in enumerate(file_descriptors):
        try:
            if "error" in f:
                msg = f["error"].get("Message", "Unknown error")
                failed_file = f["error"].get("File", "Unknown file")
                logger.error("Error downloading file %s: %s", failed_file, msg)
                fail_files.append(failed_file)
                continue

            file_id, file_name, _ = parse_file_descriptor_from_hise_file(f)

            if cu.is_legacy_ide():
                log_dir = CONFIG["IDE"]["HOME_DIR"]
                download_dir = os.path.join(
                    CONFIG["IDE"]["HOME_DIR"],
                    CONFIG["IDE"]["CACHE_DIR"],
                    str(file_id),
                )
                fname = os.path.basename(file_name)
                logger.info("Downloading fileID %s -> %s", file_id,
                            download_dir)
                cache_file(url=f["url"],
                           file_name=fname,
                           file_dir=download_dir)

            # download file to current IDE architecture
            else:
                log_dir = CONFIG["STORES"]["TEMP_STORE"]
                endpoint = get_download_path(file_id, ide_name)
                dl_resp = cu.parse_hise_response(
                    requests.request("GET",
                                     endpoint,
                                     headers=get_bearer_token_header()))
                this_path = os.path.join(CONFIG["IDE"]["HOME_DIR_V2"],
                                         dl_resp["Path"])
                dl_paths.append(this_path)

            # Log downloads
            this_file_id = parse_file_id_from_hise_file(f)
            this_sample_id = cu.parse_sample_id_from_hise_file(f)
            cu.log_downloaded_files_or_samples(this_file_id, this_sample_id,
                                               log_dir)

        # don't outright fail, but log the error
        except Exception as e:
            logger.error("Unexpected error processing file response: %s", f)
            fail_files.append(str(f))

    if fail_files:
        logger.warning("Some files failed to download: %s", fail_files)

    return dl_paths


def count_payload_entries(query: dict, is_public: bool):
    """
    get the count of how many entries a file descriptor query will return
    Parameters:
        query (dict): the user's query reformatted into mongo query language
        is_public (bool): whether the query is for public files or not
    Returns:
        count (int): how many entries the query will return
    """
    count_endpoint = get_file_descriptor_count_endpoint(is_public)
    count = cu.parse_hise_response(
        requests.post(count_endpoint,
                      data=json.dumps({"filter": query}),
                      headers=get_bearer_token_header()))
    return count['payload']


def get_download_path(file_id: str, ide_name: str):
    return f"https://{hise_server()}/{CONFIG['HYDRATION']['DOWNLOAD_PATHV2']}/{file_id}/{ide_name}"


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


def get_file_descriptor_endpoint(is_public: bool):
    """
    get the endpoint for file descriptor request, check public bool to determine whether to go to ledger or publishing endpoint

    Parameters:
    is_public (bool): whether the query is for public files or not
    """
    if is_public:
        return "https://{s}/{de}".format(
            s=hise_server(), de=CONFIG['PUBLISHING']['FILE_SEARCH_PATH'])
    else:
        return "https://{s}/{de}".format(
            s=hise_server(), de=CONFIG['LEDGER']['FILE_SEARCH_PATH'])


def get_file_descriptor_count_endpoint(is_public: bool):
    """
    get the endpoint for counting how many entries a file descriptor query will return

    Parameters:
        is_public (bool): whether the query is for public files or not
    """
    return "{s}?_count=true".format(s=get_file_descriptor_endpoint(is_public))


def get_file_descriptor_paginated_endpoint(is_public: bool, page_size: int,
                                           page_number: int):
    """
    get the endpoint for paginated file descriptor request

    Parameters:
        is_public (bool): whether the query is for public files or not
        page_size (int): number of entries per page
        page_number (int): which page to access (starting from 1)
    """
    return "{s}?page_size={ps}&page_number={pn}".format(
        s=get_file_descriptor_endpoint(is_public),
        ps=page_size,
        pn=page_number)


def get_file_metadata(file_id: str):
    """
    """
    resp = cu.parse_hise_response(
        requests.get(cu.hise_url("ledger", "file_metadata_path", file_id),
                     headers=get_bearer_token_header()))
    return resp


def get_samples_for_query(query_dict: dict):
    """
    """
    return cu.parse_hise_response(
        requests.post(cu.hise_url("ledger", "sample_filter_path"),
                      headers=get_bearer_token_header(),
                      data=json.dumps({"filter": query_dict})))


def log_replica_file_download(hise_file, file_id: str, ide_dir: str):
    """
    Creates another log entry. If a file was downloaded in a guest workspace, then the replica fileID is logged

    Parameters:
        hise_file (hise_file): hisepy.reader.hise_file object
        file_id (str): original file_id that's passed in to read_files() or cache_files()
    """
    this_file_id, _, _ = parse_file_descriptor_from_hise_file(hise_file)
    if (this_file_id != file_id):
        cu.log_downloaded_files_or_samples(file_id, None, ide_dir,
                                           this_file_id, None)
    return


def is_public_file(availability: str):
    """
    Checks if a hise_file is a public file by looking at its descriptors

    Parameters:
        availability (str): availability status of the file
    Returns:
        bool: True if the file is public, False otherwise
    """
    public_availability = ["pre_public_staged", "retracted", "public"]
    if availability in public_availability:
        return True
    else:
        return False


def parse_file_descriptor_from_hise_file(hise_file):
    """
    Takes a hise_file object and returns its file_id, file_name, descriptor object

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


def post_query(file_list: list[str] | None = None,
               query_id: str | None = None,
               query_dict: dict[str, any] | None = None,
               is_public: bool = False) -> list[dict[str, any]]:
    """
    Submits a POST request to the hydration for query parameters to get file ids
    Submits a POST request to ledger to get actual file descriptors for those file ids

    Parameters:
        file_list (list[str]): list of file ids to retrieve descriptors for
        query_id (str): query_id that corresponds to a saved query in the HISE UI
        query_dict (dict): dictionary that contains the user's query parameters. The keys should be field
        names and the values should be lists of values the user wants to query for. For example: {'fileType': ['csv']}
        is_public (bool): whether the query is for public files or not
    Returns:
        list of file descriptor objects that match the query parameters
    """

    try:
        if query_dict is not None:
            if is_public:
                raise ValueError(
                    "Query search not supported for public files.")
            payload = query_files(query_dict, is_public)
            if not payload:
                raise LookupError("Query had no matching results.")
            file_list = {item["file"]["id"] for item in payload}

        elif query_id is not None:
            if is_public:
                raise ValueError(
                    "Query ID search not supported for public files.")
            q_endpoint = f"https://{hise_server()}/{CONFIG['HYDRATION']['QUERY_SEARCH_PATH']}/{query_id}"
            resp = requests.post(q_endpoint, headers=get_bearer_token_header())
            resp_obj = cu.parse_hise_response(resp)
            file_list = {o["file"]["id"] for o in resp_obj}

        elif file_list is not None:
            file_list = set(file_list)
        else:
            raise ValueError("No valid query parameters provided.")

        obj = []
        # query for file descriptors using file ids
        for fid in file_list:
            user_query = {"id": [fid]}
            query_instance = MongoQuery(user_query, is_public=is_public)
            formatted_query = query_instance.query_dict_to_mongo_query(
                query_instance.add_prefix_to_query())
            count = count_payload_entries(formatted_query, is_public)
            rep_obj = submit_file_descriptor_request(formatted_query, count,
                                                     is_public)
            obj.append({"descriptors": list(rep_obj['payload'])})
        return obj
    except requests.RequestException as e:
        raise SystemError(
            f"Network error while calling Hydration API: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to decode JSON response: {e}") from e


def query_files(user_query: dict, is_public: bool = False):
    """
    POST request to ledger by submitting user's query parameters

    Parameters:
        user_query (dict): dictionary where for each key:value pair, the value must be of type list.
        is_public (bool): flag indicating whether the query is for public files.
    Returns:
        response payload
    Example:
        query_files(user_query={'cohortGuid' : ['FH1']})
    """

    query_instance = MongoQuery(user_query, is_public=is_public)
    formatted_query = query_instance.query_dict_to_mongo_query(
        query_instance.add_prefix_to_query())

    # count how many entries are in query
    count = count_payload_entries(formatted_query, is_public)
    obj = submit_file_descriptor_request(formatted_query, count, is_public)
    return obj['payload']


def submit_file_descriptor_request(formatted_query: dict, count: int,
                                   is_public: bool):
    # paginate/chunk if count is greater than pagination_size we set in config
    if count > CONFIG['IDE']['PAGINATION_SIZE']:
        obj = submit_paginated_query(formatted_query, count, is_public)
    else:
        endpoint = get_file_descriptor_endpoint(is_public)
        obj = cu.parse_hise_response(
            requests.post(endpoint,
                          data=json.dumps({"filter": formatted_query}),
                          headers=get_bearer_token_header()))
    return obj


def submit_paginated_query(query: dict, number_entries: int, is_public: bool):
    """
    Submits multiple paginated requests and concatenates the results together if the number of entries a query will return exceeds the pagination size set in config.

    Parameters:
        query (dict): the user's query reformatted into mongo query language
        number_entries (int): how many entries the query will return
        is_public (bool): whether the query is for public files or not
    Returns:
        dict: concatenated response payload from all paginated requests
    """

    # determine how many chunks
    page_size = CONFIG['IDE']['PAGINATION_SIZE']
    obj = {'payload': []}
    num_chunks = math.ceil(number_entries / page_size)
    for i in range(0, num_chunks):
        endpoint = get_file_descriptor_paginated_endpoint(
            is_public, page_size, i + 1)
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
