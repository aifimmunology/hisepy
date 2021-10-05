import requests
import json
import os
import pathlib
import uuid
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path

query_search_path = 'hydration/analysis/query'
file_search_path = "hydration/analysis/files"
sample_search_path = "ledger/sample/q"
subject_search_path = "ledger/subject/q"
download_path = "hydration/source/server"
trace_path = "tracer/trace"
scheduler_path = "toolchain/scheduler"
cache_dir = "cache"

class hise_file:
    '''
    A class representing a hise_file.

    Attributes
    __________
    file_id : str 
        UUID for a file. 
    file_path : string 
        Path where physical file is saved.
    descriptors : dict
        Contains metadata.

    Methods
    _______
    load(): 
        attaches fields like path or descriptors to hise_file object 
    '''

    def __init__(self, file_id, file_path = None, descriptors = None):
        if type(file_id) is uuid.UUID:
            self.id = file_id
        else:
            try:
                self.id = uuid.UUID(file_id)
            except Exception as e:
                raise(TypeError("%s is not a valid UUID. %s" % (file_id, e)))
            
        self.status = False
        self.message = "Not loaded. Run file_obj.load() to load"
        if descriptors is not None and file_path is not None and os.path.exists(file_path):
            self.descriptors = descriptors
            self.path = file_path
            self.status = True
            self.message = "OK"
        else:
            self.descriptors = None
            self.path = None
            
    def load(self):
        if self.path is not None and os.path.exists(self.path):
            #already loaded
            return True
        
        obj = read_files([str(self.id)])
        if len(obj) == 0:
            raise(TypeError("Failed to load file %s" % self.id))
        
        self.descriptors = obj[0].descriptors
        self.path = obj[0].path
        self.status = True
        self.message = "OK"

def read_files(file_list=None, query_id=None):
    '''
    Read the contents of a list of file ids into a hise_file object 

        Parameters:
            file_list : list 
                a list of UUIDS to retrieve

        Returns: 
            response : a list of hise_file objects 

    '''
    # users should only use one or the other; but not both. 
    assert (((type(file_list) is list) & (query_id == None)) | 
            ((file_list == None) & (type(query_id) is str)))
            
    if (file_list != None) & (type(file_list) is not list):
       raise(TypeError("You must pass a list of file ids to read_files"))

    # if user submits a query_id, grab all fileIds associated with that query 
    if (file_list == None) & (query_id != None): 
        q_endpoint = 'https://{s}/{q}/{qid}'.format(s=get_from_metadata_server(server_id_path), 
                                                    q=query_search_path, 
                                                    qid=query_id)
        resp = requests.request('POST', q_endpoint, headers=get_bearer_token_header())
        resp_obj = json.loads(resp.text) 
        file_list = []
        for o in resp_obj: 
            file_list += [o['file']['id']]
    
    qstr = "&".join(map(lambda x: "id=%s" % (x), file_list))
    endpoint = "https://%s/%s?%s" % (get_from_metadata_server(server_id_path), file_search_path, qstr)
    resp = requests.request("GET", endpoint, headers = get_bearer_token_header())
    
    if resp.status_code != 200:
        raise(SystemError("Request to %s failed with status %d. %s" %
                          (endpoint,resp.status_code,resp.text)))
    
    obj = json.loads(resp.text)
    if type(obj) is not list:
        raise(TypeError("Response %s is not a list, it is a %s." % (resp.text, type(obj))))
    
    #each object should be a set of descriptors and a url to download a file
    response = []
    
    for f in obj:
        if "id" not in f:
            f["id"] = uuid.UUID(int = 0)

        if "error" in f:
            fobj = hise_file(f["id"])
            fobj.message = f["error"]["Message"]
            response.append(fobj)
            continue
        else:
            response.append(cache_and_convert_file_data(f))
            
    return response

def download_files(file_dict):
    '''
    Read the contents of a dictionary of non-result file ids into hise_file objects
    These files will contain NULL descriptors (since they are not result files)
    
        Parameters:
            file_dict : dictionary
                a dictionary of file_uuid: file_name

        Returns: 
            response : a list of hise_file objects with empty descriptors 

    '''
    if type(file_dict) is not dict:
        raise(TypeError("You must pass a dictionary of file_uuid: file_name to download_files"))

    response = []
    #use a dummy batch id for these files
    download_cache = "%s/%s" % (cache_dir, "downloadable")
    for f_id in file_dict:
        endpoint = "https://%s/%s/%s" % (get_from_metadata_server(server_id_path),
                                         download_path,
                                         f_id)
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

def cache_and_convert_file_data(file_data):
    '''
    Helper function to convert files into a hise_file object 
    '''
    if type(file_data) is not dict:
        raise(Exception("Item in response is not a dict, it is a %s." % (type(file_data))))
    elif "descriptors" not in file_data:
        raise(Exception("Descriptors not found in file data %s" % (file_data)))
    elif "url" not in file_data:
        raise(Exception("No download url found in file data %s" % (file_data)))

    f_desc = file_data["descriptors"]["file"]
    batch_id = "unknown"
    if "batchID" in f_desc and f_desc["batchID"] != "":
        batch_id = f_desc["batchID"]
    file_dir = "%s/%s" % (cache_dir, batch_id)
    file_name = f_desc["name"].split("/")[-1]
    cache_file(file_data["url"],
               file_name,
               file_dir)
    return hise_file(file_id = f_desc["id"],
                     file_path = "%s/%s" % (file_dir, file_name),
                     descriptors = file_data["descriptors"])

def cache_file(url, file_name, file_dir):
    if not os.path.exists(file_dir):
        pathlib.Path(file_dir).mkdir(parents=True, exist_ok=True)
    
    f_path = "%s/%s" % (file_dir, file_name)
    resp = requests.request("GET", url, headers = get_bearer_token_header())
    if resp.status_code != 200:
        raise(SystemError("Request to get file %s from %s failed with status %d. %s" %
                          (file_name,resp.status_code,resp.text)))
    open(f_path, 'wb').write(resp.content)

def read_samples(sample_ids = None, query = None):
    '''
    Read or search the SampleStatus materialized view. 
    User should specify one or the other of sample_ids or query

        Parameters:
            sample_ids : list
               a list of UUIDS to retrieve
            query:
               a dictionary object containing search parameters using mongo query language

        Returns: 
            response : a list of samples

    '''
    if sample_ids is not None:
        if type(sample_ids) is not list:
            raise(TypeError("sample_ids must be a list"))
        query = {"id": {"$in": sample_ids}}
    if query is None:
        raise(TypeError("You must specify either a list of sample_ids or a query"))
    endpoint = "https://%s/%s" % (get_from_metadata_server(server_id_path), sample_search_path)
    resp = requests.request("POST",
                            endpoint,
                            data = json.dumps({"filter": query}),
                            headers = get_bearer_token_header())
    
    if resp.status_code != 200:
        raise(SystemError("Request to %s failed with status %d. %s" %
                          (endpoint,resp.status_code,resp.text)))
    
    obj = json.loads(resp.text)
    if type(obj) is not dict:
        raise(TypeError("Response %s is not a list, it is a %s." % (resp.text, type(obj))))
    elif "payload" not in obj:
        raise(TypeError("Response %s contained an empty payload!" % (resp.test)))
    return obj["payload"]

def read_subjects(subject_ids = None, query = None):
    '''
    Read or search the Subject materialized view. 
    User should specify one or the other of subject_ids or query

        Parameters:
            subject_ids : list
               a list of UUIDS to retrieve
            query:
               a dictionary object containing search parameters using mongo query language

        Returns: 
            response : a list of subjects

    '''
    if subject_ids is not None:
        if type(subject_ids) is not list:
            raise(TypeError("subject_ids must be a list"))
        query = {"id": {"$in": subject_ids}}
    if query is None:
        raise(TypeError("You must specify either a list of subject_ids or a query"))
    
    endpoint = "https://%s/%s" % (get_from_metadata_server(server_id_path), subject_search_path)
    resp = requests.request("POST",
                            endpoint,
                            data = json.dumps({"filter": query}),                            
                            headers = get_bearer_token_header())
    
    if resp.status_code != 200:
        raise(SystemError("Request to %s failed with status %d. %s" %
                          (endpoint,resp.status_code,resp.text)))
    
    obj = json.loads(resp.text)
    if type(obj) is not dict:
        raise(TypeError("Response %s is not a list, it is a %s." % (resp.text, type(obj))))
    elif "payload" not in obj:
        raise(TypeError("Response %s contained an empty payload!" % (resp.test)))
    return obj["payload"]
