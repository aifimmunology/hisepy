import json
import requests
import urllib
import uuid
import os
import importlib
import plotly.graph_objects as go
import dash
from shutil import rmtree
from flask_frozen import Freezer
from dash.fingerprint import build_fingerprint

from hisepy.auth import get_from_metadata_server, get_bearer_token_header, instance_name_path, debug
from hisepy.reader import parse_hise_response, hise_url
from hisepy.scheduler import current_notebook

dataframe_file_type = "Visualization-dataframe"

def get_study_spaces():
    return parse_hise_response(
        requests.request("GET",
                         hise_url("tracer","study_space_path"),
                         headers = get_bearer_token_header()))

def get_files_for_query(query_id):
    resp = parse_hise_response(
        requests.request("POST",
                         hise_url("hydration", "query_search_path", query_id),
                         headers = get_bearer_token_header()))
    return list(map(lambda x: x['file']['id'], resp))
        
def get_trace(trace_id):
    trace = parse_hise_response(
        requests.request("GET",
                         hise_url("tracer","trace_path", trace_id),
                         headers = get_bearer_token_header()))
    if len(trace) == 0:
        raise(Exception("Trace id %s is invalid" % (trace_id)))
    return trace[0]

def default_study_space_id(must = True):
    return default_study_space(must)["id"]

def default_study_space(must = True):
    sspaces = get_study_spaces()
    if len(sspaces) == 0:
        if not must:
            return None
        raise(ValueError("User belongs to no study spaces! Cannot upload to HISE!"))
    if len(sspaces) > 1:
        if not must:
            return None
        for s in sspaces:
            print("%s: %s" % (s["id"], s["name"]))
        raise(ValueError("User belongs to multiple study spaces. Please specify with the study_space_id parameter"))
    return sspaces[0]
    
def upload_files(files,
                 study_space_id = None,
                 title = None,                 
                 input_file_ids = [],
                 input_sample_ids = [],
                 file_types = []):
    if type(files) is not list or len(files) == 0:
        raise(ValueError("No files specified for upload"))
    
    trace_id = None
    study_space_id = validate_upload_data(study_space_id, title, input_file_ids)
    uploaded = []
    for i, f in enumerate(files):
        if not os.path.exists(f):
            raise(ValueError("%s is not a valid file." % (f)))
        
        file_dict = {'file':
                     (f, open(f, 'rb'),
                      'application/json', {'Expires': '0'})}
        qargs = None
        file_type = get_file_type(f)
        if type(file_types) is list and len(file_types) > i:
            file_type = file_types[i]
        if trace_id is not None:
            qargs = {"traceId": trace_id,
                     "fileType": file_type}
        else:
            qargs = {"studySpaceId": study_space_id,
                     "title": title,
                     "fileType": file_type,
                     "saveIDE": True,
                     "instanceId": get_from_metadata_server(instance_name_path),
                     "inputFileIds": input_file_ids,
                     "sampleIds": input_sample_ids,
                     "notebook": current_notebook()}
        url = hise_url("toolchain", "upload_file_path", args = qargs)
        headers = get_bearer_token_header()
        df_data = parse_hise_response(
            requests.request("POST", url, headers = headers, files = file_dict))
        if "TraceId" not in df_data:
            raise(SystemError("Trace was not found in response to file upload. Cannot continue"))
        trace_id = df_data["TraceId"]
        uploaded.append(df_data["FileId"])
    return {"trace_id": trace_id, "files": uploaded}

def save_visualization(pl_obj,
                       study_space_id = None,
                       title = None,
                       input_file_ids = [],
                       input_sample_ids = []):

    tmp_data_file = "/tmp/plotly_data.json"
    tmp_plotly_file = "/tmp/plotly.json"
    tmp_img_file = "/tmp/plotly.png"

    pl_obj.write_image(tmp_img_file)
    img_data = save_static_image(tmp_img_file, study_space_id, title)
    os.remove(tmp_img_file)
    
    exp_obj = json.loads(pl_obj.to_json())

    f = open(tmp_data_file, "w")
    f.write(json.dumps(exp_obj["data"]))
    f.close()

    up_res = upload_files([tmp_data_file],
                          study_space_id,
                          title,
                          input_file_ids,
                          input_sample_ids,
                          [dataframe_file_type])
    args = {"traceId": up_res["trace_id"],
            "images": img_data["id"]}
    
    #now null out the data and save the plotly without it
    exp_obj["data"] = []
    f = open(tmp_plotly_file, "w")
    f.write(json.dumps(exp_obj))
    f.close()
    
    vis_dict = {'file':
                (tmp_plotly_file, open(tmp_plotly_file, 'rb'),
                 'application/json', {'Expires': '0'})}
    
    v_data = parse_hise_response(
        requests.request("POST",
                         hise_url("toolchain", "visualization_path", "json", args = args),
                         headers = get_bearer_token_header(),
                         files = vis_dict))
    os.remove(tmp_data_file)
    os.remove(tmp_plotly_file)
    return up_res["trace_id"]

def save_static_image(image,
                      study_space_id = None,
                      title = None):
    if not os.path.exists(image):
        raise(ValueError("%s is not a valid file." % (image)))
    
    img_dict = {'bytes': (image, open(image, 'rb'), "image/%s" % (get_file_type(image)))}
    study_space_id = validate_upload_data(study_space_id, title, ["not a file"])
    args = {"studySpaceId": study_space_id,
            "title": title}
    return parse_hise_response(
        requests.request("POST",
                         hise_url("hydration", "upload_path", args = args),
                         headers = get_bearer_token_header(),
                         files = img_dict))
    
def freeze_dash_app(app,
                    study_space_id = None,
                    title = None,
                    input_file_ids = [],
                    input_sample_ids = []):
    study_space_id = validate_upload_data(study_space_id, title, input_file_ids)
    build_dir = "%s/build" % (app.server.root_path)
    rmtree(build_dir)
    dash_path_tokens = os.path.abspath(dash.__file__).split("/")
    dash_path = "/".join(dash_path_tokens[0:-1])
    mod_versions = {}
    app.server.config.setdefault('FREEZER_DEFAULT_MIMETYPE',
                                 'application/json')
    freezer = Freezer(app.server)
    
    @freezer.register_generator
    def componentSuites():
        for p in app.registered_paths["dash"]:
            fpath = "%s/%s" % (dash_path, p)
            if not os.path.exists(fpath):
                continue
            ptokens = p.split("/")
            path = "/".join(ptokens[1:])            
            y = {"package_name": "dash/%s" % (ptokens[0]),
                 "fingerprinted_path": path}
            yield "/_dash-component-suites/<string:package_name>/<path:fingerprinted_path>", y
            if ".map" not in path:
                #also yield the fingerprinted version
                dash_import = "dash.%s" % (ptokens[0])

                pack_vers = None
                if dash_import in mod_versions:
                    pack_vers = mod_versions[dash_import]
                else:
                    try:
                        p = importlib.import_module(dash_import)
                        pack_vers = p.__version__
                    except Exception as e:
                        if debug():
                            print("Can't load %s. %s. Defaulting dash version" %
                                  (dash_import, format(e)))
                        pack_vers = dash.__version__
                    mod_versions[dash_import] = pack_vers

                mod = int(os.stat(fpath).st_mtime)
                y["fingerprinted_path"] = build_fingerprint(path, pack_vers, mod)
                yield "/_dash-component-suites/<string:package_name>/<path:fingerprinted_path>", y
            
    @freezer.register_generator
    def default():
        yield "/<path:path>", {"path": "index.html"} 

    freezer.freeze()
    
    qargs = {"studySpaceId": study_space_id,
             "title": title,
             "saveIDE": True,
             "instanceId": get_from_metadata_server(instance_name_path),
             "inputFileIds": input_file_ids,
             "sampleIds": input_sample_ids,
             "notebook": current_notebook(),
             "buildDirectory": build_dir}
    url = hise_url("toolchain", "save_dash_app_path", args = qargs)
    headers = get_bearer_token_header()
    ret = parse_hise_response(requests.request("POST", url, headers = headers))
    rmtree(build_dir)
    return ret
    
def validate_upload_data(study_space_id, title, input_file_ids):
    if study_space_id is None:
        study_space_id = default_study_space_id()
    if title is None:
        raise(ValueError("Title cannot be empty"))
    elif len(title) < 10:
        raise(ValueError("Title must be at least 10 characters"))
    if len(input_file_ids) == 0:
        raise(ValueError("You must specify at least one input file UUID"))
    return study_space_id
    
def load_visualization(trace_id):
    data = None
    trace = get_trace(trace_id)    
    if "steps" in trace and "dataReference" in trace["steps"]:
        ref = trace["steps"]["dataReference"]
        try:
            datauuid = uuid.UUID(ref)
            if datauuid != uuid.UUID(int = 0):
                data = parse_hise_response(
                    requests.request("GET",
                                     hise_url("hydration",
                                              "download_path",
                                              format(datauuid)),
                                     headers = get_bearer_token_header()))
            else:
                #dataReference was empty UUID. Ignore
                pass
        except Exception as e:
            print("Failed to load data reference %s: %s" % (ref, format(e)))
    
    obj = parse_hise_response(
        requests.request("GET",
                         hise_url("toolchain", "visualization_path", trace_id),
                         headers = get_bearer_token_header()))
    if data is not None:
        obj["data"] = data
    return go.Figure(obj, skip_invalid = True)        

def get_file_type(filename):
    if "." in filename:
        return filename.split(".")[-1]
    else:
        return "json"

