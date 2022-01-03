import json
import requests
import urllib
import uuid
import os
import importlib
import plotly.graph_objects as go
import dash
from flask_frozen import Freezer
from dash.fingerprint import build_fingerprint

from hisepy.auth import get_from_metadata_server, get_bearer_token_header, instance_name_path, debug
from hisepy.reader import parse_hise_response, hise_url
from hisepy.scheduler import current_notebook

#NB: Javascript-generated visualizations have data and layout fields that aren't recognized
#by Python. If you run into errors loading visualizations from the UI, add unknown elements here
#Format is list of field names, or dictionaries and subfields
#  e.g. data["xField"] is invalid, as are
#       data["marker"]["color"] and
#       data["marker"]["size"]
unknown_data_fields = ["xField","yField",{"marker": ["color","size"]}]
unknown_layout_fields = [{"layout": ["margin", "autocolorscale"]}]

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
                         hise_url("tracer","tracer_path", trace_id),
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
                 input_sample_ids = []):
    if type(files) is not list or len(files) == 0:
        raise(ValueError("No files specified for upload"))
    
    trace_id = None
    study_space_id = validate_upload_data(study_space_id, title, input_file_ids)
    i = 0
    for f in files:
        if not os.path.exists(f):
            raise(ValueError("%s is not a valid file." % (f)))
        
        file_dict = {'file':
                     (f, open(f, 'rb'),
                      'application/json', {'Expires': '0'})}
        qargs = None
        if trace_id is not None:
            qargs = {"traceId": trace_id,
                     "fileType": get_file_type(f)}
        else:
            qargs = {"studySpaceId": study_space_id,
                     "title": title,
                     "fileType": get_file_type(f),
                     "saveIDE": True,
                     "instanceId": get_from_metadata_server(instance_name_path),
                     "inputFileIds": input_file_ids,
                     "sampleIds": input_sample_ids,
                     "notebook": current_notebook()}
        url = hise_url("toolchain", "upload_file_path", args = qargs)
        headers = get_bearer_token_header()
        if debug():
            url = url.replace("https", "http")
            url = url.replace("dev.allenimmunology.org","localhost:2082")
            headers["hise_invoker_token"] = headers["Authorization"].split(" ")[-1]
            headers.pop("Authorization")
            
        df_data = parse_hise_response(
            requests.request("POST", url, headers = headers, files = file_dict))
        if "TraceId" not in df_data:
            raise(SystemError("Trace was not found in response to file upload. Cannot continue"))
        trace_id = df_data["TraceId"]
        i = i + 1
        print("Did %d" % (i))
    return trace_id

def save_visualization(pl_obj,
                       study_space_id = None,
                       title = None,
                       input_file_ids = [],
                       input_sample_ids = []):

    tmp_data_file = "/tmp/plotly_data.json"
    tmp_plotly_file = "/tmp/plotly.json"
    exp_obj = json.loads(pl_obj.to_json())

    f = open(tmp_data_file, "w")
    f.write(json.dumps(exp_obj["data"]))
    f.close()

    trace_id = upload_files([tmp_data_file],
                           study_space_id,
                            title,
                           input_file_ids,
                           input_sample_ids)
    args = {"traceId": trace_id}

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
    return trace_id

def freeze_dash_app(app,
                    study_space_id = None,
                    title = None,
                    input_file_ids = [],
                    input_sample_ids = []):
    study_space_id = validate_upload_data(study_space_id, title, input_file_ids)
    build_dir = "%s/build" % (app.server.root_path)
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
    filenames = recursive_dir_walk(build_dir)
    tr = upload_files(filenames,
                      study_space_id,
                      title,
                      input_file_ids,
                      input_sample_ids)
    
    for f in filenames:
        os.remove(f)
    os.rmdir(build_dir)
    return tr
    
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
                data = load_visualization_data(format(datauuid))
            else:
                #dataReference was empty UUID. Ignore
                pass
        except Exception as e:
            print("Failed to load data reference %s: %s" % (ref, format(e)))
    
    obj = load_visualization_layout(trace_id)
    if data is not None:
        if type(data) is not list:
            raise(
                ValueError("Visualization data for trace %s is a %s, not a list. Cannot render" %
                           (trace_id, type(data))))
        for d in data:
            clean_vis_data(d, unknown_data_fields)
            obj.add_trace(d)
    return obj        

def load_visualization_layout(trace_id):
    fig = parse_hise_response(
        requests.request("GET",
                         hise_url("toolchain", "visualization_path", trace_id),
                         headers = get_bearer_token_header()))
    clean_vis_data(fig, unknown_layout_fields)
    return go.Figure(fig)

def load_visualization_data(file_id):
    return parse_hise_response(
        requests.request("GET",
                         hise_url("hydration", "download_path", file_id),
                         headers = get_bearer_token_header()))

def recursive_dir_walk(start):
    found = []
    for root, dirs, files in os.walk(start):
        for f in files:
            found.append("%s/%s" % (root, f))
        for d in dirs:
            found += recursive_dir_walk("%s/%s" % (root,d))
    return found

def get_file_type(filename):
    if "." in filename:
        return filename.split(".")[-1]
    else:
        return "json"

def clean_vis_data(vis_data, fields_to_clean):
    if type(vis_data) is not dict:
        #your code is bad -- you tried to clean a thing that's not a dictionary
        raise(ValueError("Cannot clean visualization of type %s" % (type(vis_data))))
    elif type(fields_to_clean) is not list:
        #your code is bad -- somewhere you've got a thing that's not a list
        raise(ValueError("Cannot use a %s as list of visualization fields to clean" %
                         (type(vis_data))))

    for f in fields_to_clean:
        if type(f) is str and f in vis_data:
            vis_data.pop(f)
        elif type(f) is dict:
            for k in f.keys():
                if k in vis_data:
                    clean_vis_data(vis_data[k], f[k])
