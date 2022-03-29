import json
import requests
import urllib
import uuid
import os
import importlib
import plotly.graph_objects as go
import dash
import dill
import subprocess
import warnings
from shutil import rmtree
from flask_frozen import Freezer
from dash.fingerprint import build_fingerprint

import hisepy.common_utils as cu 
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, instance_name_path, debug
from hisepy.reader import parse_hise_response, hise_url, CONFIG
from hisepy.scheduler import current_notebook, is_derived_instance


dataframe_file_type = "Visualization-dataframe"
freezer_ignore_endpoints = {"shutdown": None}

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


def gen_dash_static_image(app_filepath : str,
                          filenames : list, 
                          plotly_objects : list, 
                          create_requirements : bool, 
                          study_space_id,
                          title,
                          input_file_ids) -> bool: 
    ''' Given a filepath to an app.py file, validate input files for the app exists, require a requirements.txt also exists,
    create static images of plotly objects, tar/zip everything together and upload the file utilizing uploadFiles() 

    Parameters:

    Returns:

    Examples: 

    NOTE: requirements.txt file also needs to exist in the same directory as app_filepath you pass in 
    '''

    # check app_filepath exists 
    if not os.path.exists(app_filepath): 
        raise(ValueError("%s is not a valid file" % (app_filepath)))

    # get dir of app 
    app_dir = os.path.dirname(app_filepath)

    # list all files in that directory 
    paths_and_dirs = os.listdir(app_dir) 
    
    # check all filenames exists before moving on 
    assert set(filenames) - set(paths_and_dirs) == set(), 'not all files listed under filenames were found. Please make sure...'

    # now walk down this app_dir and find those files
    fpaths_list = []  
    for (root, dir, file) in os.walk(app_dir): 
        [fpaths_list.append('{}/{}'.format(root, f)) for f in file if f in filenames]
    
    # move everything to a temporary dir 
    try: 
        os.mkdir('{}/dash_tmp'.format(app_dir))
    except: 
        pass 
    fpaths_list.append(app_filepath)
    for this_file in fpaths_list: 
        os.popen('cp {src} {des}/dash_tmp'.format(src=this_file, des=app_dir))
    
    if not create_requirements: 
        # TODO; more sound test here. I could have a random requirements.txt, (for whatever reason), file anywhere
        assert 'requirements.txt' in paths_and_dirs, '''requirements.txt is needed in order to deploy your dash app. This file lists all your app dependencies. \n
                                                        Please try again with create_requirements set to True.'''
    else: 
        # create the thing 
        subprocess.call("pip3 freeze > {}/dash_tmp/requirements.txt".format(app_dir), shell=True)

    # handle images users want to show up in their study space. 
    # 2 scenarios here. users should be using 1 or the other, and not both 
    # 1. list of plotly objects. 
    # 2. list of .png images in their working dir 
    plot_type = type(plotly_objects[0])
    if plot_type == 'str': 
        for this_plot in plotly_objects:
            assert type(this_plot) == str & cu.get_filetype(this_plot) == '.png', 'image must be a PNG'

            # move all to tmp dir
            os.popen('cp {src} {des}/dash_tmp'.format(src=this_plot, des=app_dir))
    else: 
        # this should handle if a plotly object is passed in. 
        pass
        #  take each object, convert to .png
        # 
     
    # test stuff below 
    # tar it up; upload; and clean up 
    cu.tardir('{}/dash_tmp/{}_test.tar.gz'.format(app_dir, title), '{}/dash_tmp'.format(app_dir))


    upload_files(files= ['{}/dash_tmp/{}_test.tar.gz'.format(app_dir, title)], 
                 study_space_id= study_space_id,
                 title= title,
                 input_file_ids=input_file_ids)

    print('dash image was successfully uploaded!')
    return True

def upload_files(files : list,
                 study_space_id : str = None,
                 title : str = None,                 
                 input_file_ids : list = [],
                 input_sample_ids : list = [],
                 file_types : list = []):

    def _user_prompt_upload(input_file_ids : list): 
        '''
        '''
        print('you are trying to upload file_ids... {}. Do you truly want to proceed?'.format(input_file_ids))
        user_input = input('(y/n)')
        while user_input.lower() not in ['y','n']: 
            print('please enter either "n" for no, or "y" for yes.')
            user_input = input('(y/n)')
        if (user_input.lower() == 'y'): 
                return True
        elif (user_input.lower() == 'n'): 
                return False   

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
        file_type = cu.get_filetype(f)
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
        if (_user_prompt_upload(input_file_ids = input_file_ids)): 
            df_data = parse_hise_response(
                requests.request("POST", url, headers = headers, files = file_dict))
            if "TraceId" not in df_data:
                raise(SystemError("Trace was not found in response to file upload. Cannot continue"))
            trace_id = df_data["TraceId"]
            uploaded.append(df_data["FileId"])
        else: 
            print('Uploading canceled.')
            break
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
    return up_res

def save_static_image(image,
                      study_space_id = None,
                      title = None):
    if not os.path.exists(image):
        raise(ValueError("%s is not a valid file." % (image)))
    
    img_dict = {'bytes': (image, open(image, 'rb'), "image/%s" % (cu.get_filetype(image)))}
    study_space_id = validate_upload_data(study_space_id, title, ["not a file"])
    args = {"studySpaceId": study_space_id,
            "title": title}
    return parse_hise_response(
        requests.request("POST",
                         hise_url("hydration", "upload_path", args = args),
                         headers = get_bearer_token_header(),
                         files = img_dict))

#NB (03/07/22): Freeze Dash App attempts to use Flask Freeze
#to turn a Dash app into a static website. It is probably insufficient for our purposes.
#Compare with save_dash_app below will initiate a container build
def freeze_dash_app(app,
                    study_space_id = None,
                    title = None,
                    input_file_ids = [],
                    input_sample_ids = []):
    study_space_id = validate_upload_data(study_space_id, title, input_file_ids)
    build_dir = "%s/build" % (app.server.root_path)
    if os.path.isdir(build_dir):
        rmtree(build_dir)
    dash_path_tokens = os.path.abspath(dash.__file__).split("/")
    dash_path = "/".join(dash_path_tokens[0:-1])
    mod_versions = {}
    app.server.config.setdefault('FREEZER_DEFAULT_MIMETYPE', 'application/json')
    app.css.config.serve_locally = True
    app.scripts.config.serve_locally = True
    freezer = Freezer(app = app.server,
                      with_no_argument_rules = False)
        
    @freezer.register_generator
    def component_suites():
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

    @freezer.register_generator
    def no_arg_generator():
        #replace the build-in no-arg generator with one that ignores the "shutdown" endpoint.
        #which, like, why would you try to freeze that? 
        for rule in app.server.url_map.iter_rules():
            if rule.endpoint in freezer_ignore_endpoints:
                continue
            if not rule.arguments and 'GET' in rule.methods:
                yield rule.endpoint, {}

    #NB on my local server I observed that registered_paths were empty when with_no_argument_rules was set to False
    #After tracing some code I figured out that they aren't generated until somebody asks for them,
    #and that the order in which things are asked for matters.
    #So I explicitly ask for the main index page before freezing the app to make sure all the other paths are set.
    #tl;dr: this next line is important, don't remove it
    app.index()
                
    with warnings.catch_warnings():
        if not debug():
            warnings.simplefilter("ignore")
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
    return ret

#See notes about freeze_dash_app above
def save_dash_app(app,
                  study_space_id = None,
                  title = None,
                  input_file_ids = [],
                  input_sample_ids = []):
    if is_derived_instance():
        #we're the running instance, so no-op
        return {}
    study_space_id = validate_upload_data(study_space_id, title, input_file_ids)
    qargs = {"studySpaceId": study_space_id,
             "title": title,
             "saveIDE": True,
             "instanceId": get_from_metadata_server(instance_name_path),
             "inputFileIds": input_file_ids,
             "sampleIds": input_sample_ids,
             "notebook": current_notebook(),
             "buildContainer": True}
    url = hise_url("toolchain", "save_dash_app_path", args = qargs)
    headers = get_bearer_token_header()
    ret = parse_hise_response(requests.request("POST", url, headers = headers))
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

