import json
import requests
import urllib
import plotly.io as pio
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path, instance_name_path
from hisepy.reader import parse_hise_response, hise_url
from hisepy.scheduler import current_notebook

def get_study_spaces():
    return parse_hise_response(
        requests.request("GET",
                         hise_url("tracer","study_space_path"),
                         headers = get_bearer_token_header()))

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
                 inputFileIds = [],
                 inputSampleIds = []):
    trace_id = None
    if study_space_id is None:
        study_space_id = default_study_space_id()
    
    for f in files:
        file_dict = {'file':
                     (f, open(f, 'rb'),
                      'application/json', {'Expires': '0'})}
        qargs = None
        if trace_id is not None:
            qargs = {"traceId": trace_id}
        else:
            qargs = {"studySpaceId": study_space_id,
                     "title": title,
                     "fileType": f.split(".")[-1],
                     "saveIDE": True,
                     "instanceId": get_from_metadata_server(instance_name_path),
                     "notebook": current_notebook()}
        df_data = parse_hise_response(
            requests.request("POST", 
                             hise_url("toolchain", "upload_file_path", args = qargs),
                             headers = get_bearer_token_header(),
                             files = file_dict))
        if "TraceId" not in df_data:
            raise(SystemError("Trace was not found in response to file upload. Cannot continue"))
        trace_id = df_data["TraceId"]

    return trace_id

def save_visualization(pl_obj,
                       study_space_id = None,
                       title = None,
                       inputFileIds = [],
                       inputSampleIds = []):

    tmp_data_file = "/tmp/plotly_data.json"
    tmp_plotly_file = "/tmp/plotly.json"
    exp_obj = json.loads(pl_obj.to_json())

    f = open(tmp_data_file, "w")
    f.write(json.dumps(exp_obj["data"]))
    f.close()

    #now null out the data and save the plotly without it
    exp_obj["data"] = []
    f = open(tmp_plotly_file, "w")
    f.write(json.dumps(exp_obj))
    f.close()
    
    if study_space_id is None:
        study_space_id = default_study_space_id()
    trace_id = upload_files([tmp_data_file],
                           study_space_id,
                           title,
                           inputFileIds,
                           inputSampleIds)
    args = {"traceId": trace_id}
    vis_dict = {'file':
                (tmp_plotly_file, open(tmp_plotly_file, 'rb'),
                 'application/json', {'Expires': '0'})}
    
    v_data = parse_hise_response(
        requests.request("POST",
                         hise_url("toolchain", "visualization_path", args = args),
                         headers = get_bearer_token_header(),
                         files = vis_dict))
    return trace_id

def load_visualization(trace_id):
    data = None
    trace = get_trace(trace_id)    
    if "steps" in trace and "dataReference" in trace["steps"]:
        fileId = trace["steps"]["dataReference"]
        try:
            data = parse_hise_response(
                requests.request("GET",
                                 hise_url("hydration", "download_path", fileId),
                                 headers = get_bearer_token_header()))
        except Exception as e:
            print("Failed to load data reference %s: %s" % (fileId, format(e)))
    
    obj = parse_hise_response(
        requests.request("GET",
                         hise_url("toolchain", "visualization_path", trace_id),
                         headers = get_bearer_token_header()))
    if data is not None:
        obj["data"] = data
        
    #I'm sure there's a way to do this directly, but...what...is...it?
    tmp_output_file = "/tmp/plotly_loaded"
    f = open(tmp_output_file, "w")
    f.write(json.dumps(obj))
    f.close()
    return pio.read_json(tmp_output_file)

