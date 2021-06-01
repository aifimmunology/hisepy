import requests
import json
import os
import pathlib
import uuid
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path

search_path = "hydration/analysis/files"
trace_path = "tracer/trace"
scheduler_path = "toolchain/scheduler"
cache_dir = "cache"

class hise_file:
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
        obj = read_files([str(self.id)])
        if len(obj) == 0:
            raise(TypeError("Failed to load file %s" % self.id))
        
        self.descriptors = obj[0].descriptors
        self.path = obj[0].path
        self.status = True
        self.message = "OK"

def read_files(file_list):
    if type(file_list) is not list:
        raise(TypeError("You must pass a list of file ids to read_files"))
    
    qstr = "&".join(map(lambda x: "id=%s" % (x), file_list))
    endpoint = "https://%s/%s?%s" % (get_from_metadata_server(server_id_path), search_path, qstr)
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

def cache_and_convert_file_data(file_data):
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
    ddir = "%s/%s" % (cache_dir, batch_id)
    if not os.path.exists(ddir):
        pathlib.Path(ddir).mkdir(parents=True, exist_ok=True)
        
    f_path = "%s/%s" % (ddir, f_desc["name"].split("/")[-1])
    resp = requests.request("GET", file_data["url"], headers = get_bearer_token_header())
    if resp.status_code != 200:
        raise(SystemError("Request to get file %s from %s failed with status %d. %s" %
                          (f_path,resp.status_code,resp.text)))
    open(f_path, 'wb').write(resp.content)
    return hise_file(file_id = f_desc["id"],
                     file_path = f_path,
                     descriptors = file_data["descriptors"])
