import json
import os
from urllib import response
import uuid
import pandas as pd
from termcolor import colored
import requests
from hisepy.instances import IDEInstance
import hisepy.common_utils as cu
import hisepy.formatter as hf
import hisepy.lookup as hl
import hisepy.reader_utils as ru
from hisepy.auth import get_bearer_token_header, hise_server, debug, HiseUser
from hisepy.logging import with_default_logging, logger
from hisepy.upload_utils import valid_upload_stores

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


@with_default_logging
def cache_files(file_ids: list[str] | None = None,
                query_id: list[str] | None = None,
                query_dict: dict[str, any] | None = None,
                is_public: bool = False) -> list[str]:
    """ Downloads requested files to an IDE

    Parameters:
        file_ids (list): list of file IDs
        query_id (list): list of a single query ID
        query_dict (dict): query in the format of a dict
        is_public (bool): flag indicating if the files are public

    Returns:
        a list of filepaths that were successfully downloaded
    """

    try:
        ru.validate_download_params(file_ids, query_id, query_dict)

        # Determine how to get the response object
        if query_id:
            if not cu.prompt_user(CONFIG["PROMPTS"]["QUERY_ID_READ"].format("query_id", "cache_files")):
                logger.info("Cancelled cache_files call.")
                return []
            if is_public:
                raise ValueError("Query ID search not supported for public files.")
            resp_obj = ru.post_query(query_id=query_id[0])

        elif query_dict:
            if not cu.prompt_user(CONFIG["PROMPTS"]["QUERY_ID_READ"].format("query_dict", "cache_files")):
                logger.info("Cancelled cache_files call.")
                return []
            resp_obj = ru.post_query(query_dict=query_dict, is_public=is_public)

        else:
            resp_obj = ru.post_query(file_list=file_ids, is_public=is_public)

    except Exception as e:
        raise Exception(f"Failed to fetch file descriptors: {e}")

    dl_paths: List[str] = []
    fail_files: List[str] = []
    ide_name = IDEInstance().podName
    for idx, f in enumerate(resp_obj):
        try:
            if "error" in f:
                msg = f["error"].get("Message", "Unknown error")
                failed_file = f["error"].get("File", "Unknown file")
                logger.error("Error downloading file %s: %s", failed_file, msg)
                fail_files.append(failed_file)
                continue

            file_id, file_name, _, availability = ru.parse_file_descriptor_from_hise_file(f)

            if not ru.availability_matches_is_public(file_id, availability, is_public):
                fail_files.append(str(f))
                continue

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
                ru.cache_file(url=f["url"],
                              file_name=fname,
                              file_dir=download_dir)

            # download file to current IDE architecture
            else:
                log_dir = CONFIG["STORES"]["TEMP_STORE"]
                dl_endpoint = ru.get_download_path(file_id, ide_name)
                dl_resp = cu.parse_hise_response(
                    requests.request("GET",
                                     dl_endpoint,
                                     headers=get_bearer_token_header()))
                this_path = os.path.join(CONFIG["IDE"]["HOME_DIR_V2"],
                                         dl_resp["Path"])
                dl_paths.append(this_path)

            # Log downloads
            this_file_id = ru.parse_file_id_from_hise_file(f)
            this_sample_id = cu.parse_sample_id_from_hise_file(f)
            cu.log_downloaded_files(this_file_id, this_sample_id, log_dir)

            if file_ids:
                # ensure correct file mapping
                original_file_id = file_ids[idx]
                ru.log_replica_file_download(f, original_file_id, log_dir)

        # don't outright fail, but log the error
        except Exception as e:
            logger.error("Unexpected error processing file response: %s", f)
            fail_files.append(str(f))

    if fail_files:
        logger.warning("Some files failed to download: %s", fail_files)

    return dl_paths


@with_default_logging
def get_file_descriptors(query_dict: dict = None, is_public: bool = False):
    """
    Retrieves file descriptors based on user's query.

    Parameters:
        query_dict (dict): dictionary that contains query parameters
        is_public (bool): boolean to determine whether to query public files or not.
    Returns:
        dictionary of data.frame objects
    Examples:
        df_dict = get_file_descriptors(q_dict)
        df_dict.keys() # print keys of dict
        df_dict['descriptors'] # to view descriptors
        df_dict['labResults'] # lab results
        df_dict['specimens'] # specimen df
    """

    ## filetype required for non public files
    if 'fileType' not in query_dict.keys() and is_public == False:
        raise ValueError(
            'fileType field must be in the your query dictionary.')
    if type(query_dict) is not dict:
        raise ValueError("query_dict parameter must be a dictionary")
    for d in query_dict.keys():
        if type(query_dict[d]) is not list:
            raise ValueError("query dictionary values must be of type list")

    # get a list of descriptor objects
    try:
        obj = ru.query_files(query_dict, is_public)
    except Exception as e:
        raise Exception(f"failed to query for file descriptors: {e}")

    # create empty lists instead of DataFrames
    collectors = {
        'descriptors': [],
        'labResults': [],
        'specimens': [],
        'survey': []
    }
    for this_desc in obj:
        try:
            reshaped = hf.reshape_descriptors(this_desc)
            for key in collectors:
                collectors[key].append(reshaped[key])
        except Exception:
            raise Exception(
                f"appending descriptor failed. descriptor: {this_desc}")

    try:
        # concat once per key
        dict_df = {
            k: pd.concat(v, ignore_index=True) if v else pd.DataFrame()
            for k, v in collectors.items()
        }

        # public files do not have a project guid
        if "projectGuid" in dict_df["descriptors"].columns:
            # attach project info to descriptors
            dict_df['descriptors'] = hf.attach_project_info_to_df(
                dict_df['descriptors'])
        return dict_df
    except Exception as e:
        raise Exception(f"failed to append all file descriptors: {e}")


@with_default_logging
def get_files_for_query(query_id: str):
    """ Returns a list of file_ids pertaining to a HISE query_id """
    resp = cu.parse_hise_response(
        requests.post(cu.hise_url("hydration", "query_search_path", query_id),
                      headers=get_bearer_token_header()))
    return list(map(lambda x: x['file']['id'], resp))


@with_default_logging
def read_files(file_list: list[str] | None = None,
               query_id: list[str] | None = None,
               query_dict: dict[str, any] | None = None,
               to_df: bool = True,
               is_public: bool = False):
    """
    Read the contents of a list of file ids into a hise_file object
    Note: users should only use 1 parameter per function call

    Parameters:
        file_list (list): a list of UUIDS to retrieve
        query_id (str): string value of queryID from Advanced Search
        query_dict (dict): dictionary that allows users to submit a query.
            Note: for each key:value pair, the value must be of type list
        to_df (bool):  boolean determining whether result should be returned as a data.frame.
        is_public (bool): boolean determining whether to query public files or not.

    Returns:
        a list of hise_file objects

    Example: hp.read_files(file_list=['6cb2f536-2d20-4e66-b04d-327dce6870f4'])
    """

    # validate params; resolve query method used
    try:
        ru.validate_download_params(file_list, query_id, query_dict)
        if query_id is not None:
            if not cu.prompt_user(CONFIG["PROMPTS"]["QUERY_ID_READ"].format("query_id", "read_files")):
                print("Cancelled read_files call.")
                return []
            if is_public:
                raise ValueError("Query ID search not supported for public files.")
            obj = ru.post_query(query_id=query_id[0])

        elif query_dict is not None:
            if not cu.prompt_user(CONFIG["PROMPTS"]["QUERY_ID_READ"].format("query_dict", "read_files")):
                print("Cancelled read_files call.")
                return []
            obj = ru.post_query(query_dict=query_dict)

        else:
            obj = ru.post_query(file_list=file_list)

    except Exception as e:
        raise Exception(f"Failed to fetch file descriptors: {e}")

    response = []
    ide_name = IDEInstance().podName
    temp_dir = CONFIG["STORES"]["TEMP_STORE"]
    home_dir_v2 = CONFIG["IDE"]["HOME_DIR_V2"]

    # download file loop
    for idx, f in enumerate(obj):
        try:
            # Initialize a default hise_file object
            if "id" not in f:
                f["id"] = uuid.UUID(int=0)

            if "error" in f:
                fobj = ru.hise_file(f["error"]["File"])
                fobj.message = f["error"]["Message"]
                fobj.status = False
                response.append(fobj)
                continue

            # parse file metadata
            file_id, _, desc, availability = ru.parse_file_descriptor_from_hise_file(f)

            if not ru.availability_matches_is_public(file_id, availability, is_public):
                fobj = ru.hise_file(file_id)
                fobj.message = "File skipped due to availability settings."
                fobj.status = False
                response.append(fobj)
                continue

            dl_endpoint = ru.get_download_path(file_id, ide_name)

            # method to download files in legacy IDEs
            if cu.is_legacy_ide():
                fobj = ru.cache_and_convert_file_data(f)
                log_dir = CONFIG["IDE"]["HOME_DIR"]
                download_filepath = fobj.path
            else:
                # download data to user's ide
                parsed_dl = cu.parse_hise_response(
                    requests.get(dl_endpoint, headers=get_bearer_token_header()))
                download_filepath = os.path.join(home_dir_v2,
                                                 parsed_dl["Path"])

                # Wait for async download completion
                ru.wait_for_file(download_filepath)

                fobj = ru.convert_file_data(f, parsed_dl["Path"])
                log_dir = temp_dir

            # update hise file object
            desc["file"]["name"] = download_filepath
            fobj.status = True
            fobj.descriptors = desc
            fobj.message = "OK"

            # log activity
            file_id = ru.parse_file_id_from_hise_file(f)
            sample_id = cu.parse_sample_id_from_hise_file(f)
            cu.log_downloaded_files(file_id, sample_id, log_dir)

            # attempt to log replica files for guest accounts
            if file_list:
                ru.log_replica_file_download(f, file_list[idx], log_dir)

            response.append(fobj)

        # log the error, as we're not raising an error and not outright stopping the function call
        except Exception as e:
            print(colored(f"Failed to process file {f.get('id')}: {e}", "red"))
            logger.error(f"Failed to process file {f.get('id')}: {e}")
            ru.append_error_response(response, f, str(e), idx)

    # let the user know what files failed to download
    failed_files = [
        str(f.id) for f in response if not getattr(f, "status", False)
    ]
    if failed_files:
        print(
            colored(f"The following files failed to download: {failed_files}",
                    "red"))

    # finally reshape to data.frame, if requested
    try:
        if to_df:
            return hf.hise_file_to_df(response)
        else:
            return response
    except Exception as e:
        raise RuntimeError(
            f"Failed to reshape file descriptors as data.frame: {e}")


@with_default_logging
def read_samples(sample_ids: list = None, query_dict: dict = None, to_df=True):
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

    # validate user params
    ru.validate_samples_subjects_params(sample_ids, query_dict)

    query = ru.gen_read_samples_subjects_query(sample_ids, query_dict)
    if query is None:
        raise TypeError(
            "Failed to generate query from user's parameters. You must specify either a list of sample_ids or a query"
        )

    # send request to ledger to get samples
    endpoint = "https://%s/%s" % (hise_server(),
                                  CONFIG['LEDGER']['SAMPLE_SEARCH_PATH'])
    payload = {"filter": query}
    try:
        obj = cu.parse_hise_response(
            requests.post(endpoint,
                          data=json.dumps(payload),
                          headers=get_bearer_token_header()))

        if obj['payload'] is None:
            raise ValueError("User's query resulted in 0 results")
        if not to_df:
            return obj['payload']

        dict_df = hf.sample_to_df(obj["payload"])
        dict_df['metadata'] = hf.attach_project_info_to_df(dict_df['metadata'])
        return dict_df

    except Exception as e:
        raise Exception(f"Failed to retrieve sample metadata: {e}")


@with_default_logging
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
    ru.validate_samples_subjects_params(subject_ids, query_dict)

    query = ru.gen_read_samples_subjects_query(subject_ids,
                                               query_dict,
                                               is_sample_query=False)
    if query is None:
        raise TypeError(
            "You must specify either a list of subject_ids or a query")

    # send thy request to ledger
    endpoint = "https://%s/%s" % (hise_server(),
                                  CONFIG['LEDGER']['SUBJECT_SEARCH_PATH'])
    payload = {"filter": query}

    try:
        obj = cu.parse_hise_response(
            requests.post(endpoint,
                          data=json.dumps(payload),
                          headers=get_bearer_token_header()))

        if obj['payload'] is None:
            raise ValueError("User's query resulted in 0 results")
        if not to_df:
            return obj["payload"]
        return hf.attach_project_info_to_df(hf.subject_to_df(obj["payload"]))
    except Exception as e:
        raise Exception(f"Failed to retrieve subject metadata: {e}")


@with_default_logging
def list_filesets(study_space_id: str) -> pd.DataFrame:
    """
    Returns a list of filesets for a given study

    Parameters:
        study_space_id (str) : a unique identifier for a study in the collaboration space

    Returns:
        data.frame with columns ['id', 'studySpaceId', 'title','description','fileIds']

    Example:
        hp.list_filesets(study_space_id='c39e3ae5-ec11-4f02-b89d-255945c5788e')
    """
    if type(study_space_id) is not str:
        raise ValueError("study_space_id must be of type str")

    try:
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
        obj_df_sub = obj_df.loc[
            obj_df['deleted'].eq('false'),
        ]
        return obj_df_sub[[
            'id', 'studySpaceId', 'title', 'description', 'fileIds'
        ]].reset_index(drop=True)
    except Exception as e:
        raise Exception(f"failed to list filesets: {e}")


@with_default_logging
def cache_fileset(fileset_id: str) -> list[str]:
    """
    Downloads all files pertaining to a fileset to a user's workspace.

    Parameters:
        fileset_id (str) : unique identifier for a fileset in a study

    Example:
        hp.cache_fileset(fileset_id='c39e3ae5-ec11-4f02-b89d-255945c5788e')

    Returns:
        list of filepaths of downloaded files. Files will be downloaded to /input/.../fileset/<fileset_id>
    """
    # validate
    if fileset_id is None:
        raise ValueError("You must specify a fileset_id")
    if type(fileset_id) is not str:
        raise ValueError("fileset_id must be of type string")

    # request to hydrate all files in set
    ide_name = IDEInstance().podName
    endpoint = "{}/{}/{}".format(cu.hise_url('hydration', 'file_set_download'),
                                 fileset_id, ide_name)

    try:
        # download files
        obj = cu.parse_hise_response(
            requests.get(endpoint, headers=get_bearer_token_header()))

        # gather fileIds within fileset
        # filter on fileset_id
        filter_endpoint = "{}".format(
            cu.hise_url('tracer', 'file_set', 'filter'))
        fileset_dict_query = {'id': [fileset_id]}
        fileset_query = ru.MongoQuery(
            fileset_dict_query).query_dict_to_mongo_query(fileset_dict_query)
        fileset_obj = cu.parse_hise_response(
            requests.post(filter_endpoint,
                          headers=get_bearer_token_header(),
                          data=json.dumps({"filter": fileset_query})))

        # log file ids
        for f in list(fileset_obj[0]['fileIds'].keys()):
            cu.log_downloaded_files(file_id=f,
                                    ide_dir=CONFIG['STORES']['TEMP_STORE'])

        # return the user all the files that were downloaded
        output_file_paths = cu.list_all_filepaths(
            '{input}/{crc}/fileset/{fsid}'.format(
                input=CONFIG['STORES']['INPUT_STORE'],
                crc=cu.crc32_from_string(HiseUser().email),
                fsid=fileset_id))

        return output_file_paths
    except Exception as e:
        raise Exception(f"failed to download fileset files: {e}")
