import requests
import os
import inspect
import json

from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path, instance_name_path
from hisepy.reader import read_files

ideHome = os.getenv("IDE_HOME") or "/home/jupyter"
is_instance_flag_file = "%s/.scheduledinstance" % (ideHome)
job_record_file = "%s/.notebookschedulerjobid" % (ideHome)

trace_path = "tracer/trace"
scheduler_path = "toolchain/scheduler"

job_id_field = "id"
file_ids_field = "fileIds"
trace_id_field = "trace_id"
status_field = "status"
title_field = "title"
ledger_output_field = "ledger_output"

job_complete_status = "Completed"

def schedule_notebook(output_files,
                      platform = None,
                      project = None,
                      prompt = True):
    ''' 
    Schedule a notebook to run on a seperate, and larger instance.

        Parameters: 
            output_files : list
                List of expected outputs.
            platform : str 
                Optional. Used to specify what platform the job should be scheuled on.
            project : str 
                Optional. Specify the project short name for this job, if you belong to more than one.
            prompt : bool 
                Optional. Print a prompt before scheduling the notebook.

        Returns: 
            An instance of a job object.
    ''' 
    
    if type(output_files) is not list:
        raise(TypeError("output_files must be a list, not a %s" % (type(output_files))))
    elif len(output_files) == 0:
        raise(TypeError("output_files must contain at least on expected output file"))
    else:
        for f in output_files:
            if " " in f:
                raise(TypeError("%s is an invalid output file. Spaces are not allowed in output file names." % (f)))

    if os.path.exists(job_record_file):
        #you're on a cloned instance that was created from this job
        job = notebook_job(id = open(job_record_file, "r").read().rstrip())
        print("You are on a cloned instance created from notebook job %s in status %s." %
              (job.id, job.status))
        if len(job.ledger_output) > 0:
            print("The following output files are available in the curent directory of this IDE:")
            for f in job.ledger_output:
                print(f)
        print("To clear this job and schedule another job from this IDE instance, run:")
        print("hisepy.clear_notebook_job()")
        return job
    elif os.path.exists(is_instance_flag_file):
        #we're on a scheduled instance, so return an empty job
        return notebook_job()
    notebook = current_notebook()
    nbtokens = notebook.split("/")
    
    payload = {
        "notebook_name": nbtokens[-1],
        "instance_name": get_from_metadata_server(instance_name_path),
        "notebook_path": "/".join(nbtokens[0:-1]),
        "output_files": output_files
    }
    if platform is not None:
        payload["notebook_platform"] = platform
    if project is not None:
        payload["project"] = project
        
    nb_file = "%s/%s" % (payload["notebook_path"],payload["notebook_name"])        
    if not os.path.exists(nb_file) or not os.path.isfile(nb_file):
        raise(TypeError("Notebook %s does not exist. Check values for notebook_path and notebook_name and try again" % (nb_file)))

    if prompt:
        print("About to schedule notebook %s for run on a large instance." % (nb_file))
        print("I will run all the cells in the notebook, only skipping this schedule function.")
        print("I expect this notebook to produce the following output files:")
        for f in output_files:
            print("\t%s" % (f))
        print("I will copy those files back to HISE where they will be available for later download into this or another IDE instance.")
        print("OK? (y/n) ", end = "")
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
    print("Scheduled.")    
    return job

def get_notebook_job(job_id = None):
    '''
    Get the instance of a particular notebook job.

        Parameters:
            job_id : str

        Returns: 
            A job object (see documentation on notebook_job class).
    '''

    if job_id is None:
        if os.path.exists(job_record_file):
            job_id = open(job_record_file, "r").read().rstrip()
        else:
            raise(Exception("Job Id not specified, and no schedule record found on instance"))
    return notebook_job(id = job_id)
    
def clear_notebook_job():
    '''
    Clear the record of most recent job. This will not delete the job or have any effect on its status. Using this function will allow to to schedule another job.
    '''
    if os.path.exists(job_record_file):
        job_id = open(job_record_file, "r").read().rstrip()
        os.remove(job_record_file)
        print("Cleared job %s" % (job_id))
    else:
        print("No job record found")

def current_notebook():
    '''
    Return the name of a notebook.

        Returns: 
            name : str 
                Name of notebook.
    '''
    test_notebook = os.getenv("TEST_SCHEDULER_NOTEBOOK")
    if test_notebook is not None and test_notebook != "":
        return test_notebook
    
    name = os.popen("find /home -iname \"*.ipynb\" -printf \"%T@ %p\n\" -amin 5 | grep -v .ipynb_checkpoints | sort -nr | head -n 1 | cut -f2- -d ' '").read().rstrip()
    if name is None or name == "":
        raise(TypeError("Cannot get name of the current notebook. Make sure you are working somewhere within the /home directory, save the notebook you're working in, and try again"))
    return name

class notebook_job:
    '''
    A class representing a notebook job.

    Attributes
    __________
    id : str 
        UUID for notebook job.
    status : string 
        Status of notebook job.
    
    Methods
    _______

    check_status(): 
        Returns status of job.
    is_completed(): 
        Determines whether job is running or not.
    download_output(): 
        Downloads all expected outputs if job produced any.
    '''
    def __init__(self, id = None, obj = None):
        self.id = id
        self.trace_id = None
        self.status = "Unknown"
        self.ledger_output = []
        
        if obj is not None:
            self.init_from_object(obj)
        elif self.id is not None:
            self.reload()

    def init_from_object(self,obj):
        if job_id_field in obj:        
            self.id = obj[job_id_field]        
        else:
            raise(Exception("No job id found in json object"))

        if ledger_output_field in obj:
            for fid in obj[ledger_output_field]:
                  self.ledger_output.append(obj[ledger_output_field][fid])
                  
        if trace_id_field in obj:
            self.trace_id = obj[trace_id_field]
        else:
            raise(Exception("No trace id found in json object"))
        
        if status_field in obj:
            self.status = obj[status_field]
        else:
            raise(Exception("No status found in json object"))
        
    def reload(self):
        if self.id is None:
            print("job id is empty, not reloading")
            return
        
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

    def check_status(self):
        self.reload()
        return self.status
    
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
    '''
    A class representing a trace object. Used to allow re-execution or file retrieval for a particular job id 

    Attributes
    __________ 
    id : str 
        UUID for scheduled notebook 
    file_ids : list 
        List of file_ids 

    Methods 
    _______
    reload():
        Reload job object 
    '''
    def __init__(self, id):
        self.id = id
        self.file_ids = []
        self.reload()

    def reload(self):
        if self.id is None:
            print("Trace Id is empty, not reloading")
            return
        
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

