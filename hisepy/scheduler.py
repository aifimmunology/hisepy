import requests
import os
import inspect
import json

from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path, instance_name_path
from hisepy.reader import read_files

home = os.getenv("HOME") or "/root"
is_instance_flag_file = "%s/.hsneinstance" % (home)
job_submitted_file = "%s/.notebookschedulerjobid" % (home)

trace_path = "tracer/trace"
scheduler_path = "toolchain/scheduler"

job_id_field = "id"
file_ids_field = "fileIds"
trace_id_field = "trace_id"
status_field = "status"
title_field = "title"

job_complete_status = "Completed"


def schedule_notebook(output_files,
                      args = dict(),                      
                      function = None,
                      function_args = None,
                      do_verification = True):
    
    if type(output_files) is not list:
        raise(TypeError("output_files must be a list, not a %s" % (type(output_files))))
    elif len(output_files) == 0:
        raise(TypeError("output_files must contain at least on expected output file"))
    else:
        for i,of in enumerate(output_files):
            output_files[i] = os.path.abspath(of)
    
    if function is not None:
        if not inspect.isfunction(function):
            raise(TypeError("function must be a function, not a %s" % (type(function))))
        else:
            paramct = len(inspect.signature(function).parameters)
            if paramct > 1:
                raise(TypeError("Function %s expects %d parameters. On execution, we will only pass a single argument as an argument to %s" % (function.__name__,paramct,function.__name__)))
            elif paramct == 1 and function_args is None:
                raise(TypeError("Function %s expects 1 parameter, but no arguments were specified" % (function.__name__)))
            elif paramct == 0 and function_args is not None:
                raise(TypeError("Function %s expects 0 parameter, but a %s was specified as input" % (function.__name__, type(function_args))))
            
    if os.path.exists(job_submitted_file):
        #you've already scheduled this/a notebook
        job = notebook_job(id = open(job_submitted_file, "r").read().rstrip())
        if job.is_completed(False):
            print("Downloading output from completed job")
            output = job.download_output()
            clear_notebook_job()
            return output
        else:
            print("Job %s submitted and is currently in status %s." % (job.id, job.status))
            print("To load a notebook job, run:")
            print("\tjob = hisepy.get_notebook_job(\"%s\")" % (job.id))
            print("To download output from that job (if it is completed) run:")
            print("\tfiles = job.download_output()")
            print("To clear this job and schedule another job from this IDE instance, run:")
            print("\thisepy.clear_notebook_job()")
        return
    elif os.path.exists(is_instance_flag_file):
        #we're on the scheduled instance. Run the thing if the thing is there to be run
        if function is not None:
            if function_args is not None:
                return function(function_args)
            else:
                function()
        else:
            #no-op here
            return None
    
    payload = {
        "notebook_name": notebook_name(),
        "instance_name": get_from_metadata_server(instance_name_path),
        "notebook_path": os.getcwd(),
        "output_files": output_files,
    }
    
    for key, val in args.items():
        payload[key] = val

    nb_file = "%s/%s" % (payload["notebook_path"],payload["notebook_name"])        
    if not os.path.exists(nb_file) or not os.path.isfile(nb_file):
        raise(TypeError("Notebook %s does not exist. Check values for notebook_path and notebook_name and try again" % (nb_file)))

    if do_verification:
        print("About to schedule notebook %s for run on a large instance." % (nb_file))
        print("I will run all the cells in the notebook.")
        if function is not None:
            print("When I reach this cell, I will execute the code contained in function %s" % (function.__name__))
        print("I expect this notebook to produce the following output files:")
        for f in output_files:
            print("\t%s" % (f))
        print("I will copy those files back to HISE where they will be available for later download into this or another IDE instance.")
        print("OK? ")
        resp = input()
        if len(resp) == 0 or resp.lower()[0] != "y":
            print("Not scheduling.")
            return None

    print("Scheduling...")
    headers = get_bearer_token_header()
    endpoint = "https://%s/%s" % (get_from_metadata_server(server_id_path), scheduler_path)
    resp = requests.request("POST", endpoint, json = payload, headers = headers)
    if resp.status_code != 200:
        raise(Exception("Request to %s failed with status %d. %s" % (endpoint,resp.status_code,resp.text)))
    job = notebook_job(obj = json.loads(resp.text))
    f = open(job_submitted_file, "w")
    f.write(job.id)
    f.close()
    print("Scheduled.")    
    return job

def get_notebook_job(job_id = None):
    if job_id is None:
        if os.path.exists(job_submitted_file):
            job_id = open(job_submitted_file, "r").read().rstrip()
        else:
            raise(Exception("Job Id not specified, and no schedule record found on instance"))
    return notebook_job(id = job_id)
    
def clear_notebook_job():
    if os.path.exists(job_submitted_file):
        job_id = open(job_submitted_file, "r").read().rstrip()
        os.remove(job_submitted_file)
        print("Cleared job %s" % (job_id))
    else:
        print("No job currently available")

def notebook_name():
    name = os.popen("ls -t | grep -F .ipynb | head -1").read().rstrip()
    if name is None or name == "":
        raise(TypeError("Cannot get name of the current notebook. Please specify using the \"notebook_name\" argument."))
    return name

class notebook_job:
    def __init__(self, id = None, obj = None):
        self.id = id
        self.trace_id = None
        self.status = "Unknown"
        
        if obj is not None:
            self.init_from_object(obj)
        else:
            self.reload()

    def init_from_object(self,obj):
        if job_id_field in obj:        
            self.id = obj[job_id_field]        
        else:
            raise(Exception("No job id found in json object"))
        
        if trace_id_field in obj:
            self.trace_id = obj[trace_id_field]
        else:
            raise(Exception("No trace id found in json object"))
        
        if status_field in obj:
            self.status = obj[status_field]
        else:
            raise(Exception("No status found in json object"))
        
    def reload(self):
        headers = get_bearer_token_header()
        endpoint = "https://%s/%s/%s" % (get_from_metadata_server(server_id_path),
                                         scheduler_path,
                                         self.id)
        resp = requests.request("GET", endpoint, headers = headers)
        if resp.status_code != 200:
            raise(Exception("Request to %s failed with status %d. %s" % (endpoint,
                                                                         resp.status_code,
                                                                         resp.text)))
        self.init_from_object(json.loads(resp.text))

    def trace(self):
        return trace(self.trace_id)
    
    def is_completed(self, reload = True):
        if reload:
            self.reload()
        return self.status == job_complete_status

    def download_output(self):
        if self.is_completed():
            trace = self.trace()
            if len(trace.file_ids) > 0:
                return read_files(trace.file_ids)
            else:
                raise(
                    Exception("Job is in completed status, but trace contains no output files"))
        else:
            print("Job %s is currently in status %s. Try again later." % (self.id, self.status))
            return None
        
class trace:
    def __init__(self, id):
        self.id = id
        self.file_ids = []
        self.reload()

    def reload(self):
        headers = get_bearer_token_header()
        endpoint = "https://%s/%s/%s" % (get_from_metadata_server(server_id_path),
                                         trace_path,
                                         self.id)
        resp = requests.request("GET", endpoint, headers = headers)
        if resp.status_code != 200:
            raise(Exception("Request to %s failed with status %d. %s" % (endpoint,
                                                                         resp.status_code,
                                                                         resp.text)))
        j_obj = json.loads(resp.text)
        if type(j_obj) is list and len(j_obj) > 0:
            j_obj = j_obj[0]

        if file_ids_field in j_obj:
            for f in j_obj[file_ids_field]:
                self.file_ids.append(f)
        
        if title_field in j_obj:
            self.title = j_obj[title_field]
        else:
            self.title = "Trace %s" % self.id

