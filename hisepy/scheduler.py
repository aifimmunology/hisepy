import json
import os
import random

import pandas
import requests
import time

import hisepy.common_utils as cu
import hisepy.reader_utils as ru
from hisepy.auth import hise_server, get_bearer_token_header, IDEInstance
from hisepy.common_utils import current_notebook
from hisepy.logging import with_default_logging, logger

the_current_notebook = None
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))
derived_instance_flag_file = "/%s/.derivedinstance" % (
    CONFIG['IDE']['HOME_DIR'])
job_record_file = "/%s/.notebookschedulerjobid" % (CONFIG['IDE']['HOME_DIR'])


def download_files(file_dict: dict):
    """
    Read the contents of a dictionary of non-result file ids into hise_file objects
    These files will contain NULL descriptors (since they are not result files)

    Parameters:
        file_dict (dict): a dictionary of file_uuid: file_name

    Returns:
        a list of hise_file objects with empty descriptors

    """
    if type(file_dict) is not dict:
        raise TypeError(
            "You must pass a dictionary of file_uuid: file_name to download_files"
        )

    response = []
    #use a dummy batch id for these files
    download_cache = "%s/%s" % (CONFIG['IDE']['CACHE_DIR'], "downloadable")
    for f_id in file_dict:
        endpoint = "https://%s/%s/%s" % (
            hise_server(), CONFIG['HYDRATION']['DOWNLOAD_PATH'], f_id)
        hf = ru.hise_file(f_id)
        try:
            ru.cache_file(endpoint, file_dict[f_id], download_cache)
            hf.status = True
            hf.message = "OK"
            hf.path = "%s/%s" % (download_cache, file_dict[f_id])
        except Exception as e:
            hf.status = False
            hf.message = str(e)
        response.append(hf)

    return response


@with_default_logging
def schedule_notebook(output_files=None,
                      input_data=None,
                      platform=None,
                      project=None,
                      prompt=True):
    """
    Schedule a notebook to run on a seperate, virtual machine instance.

    Parameters:
        output_files (list): List of expected outputs.
        input_data (list): List of input datasets
        platform (str) specify what platform the job should be scheuled on.
        project (str): Specify the project short name for this job, if you belong to more than one.
        prompt (bool): whether to prompt user before scheduling the notebook.
    Returns:
        An instance of a notebook_job class.
    Example: 
        hp.schedule_notebook(output_files=['/home/jupyter/output.rds'], 
                             input_data=['/home/jupyter/input_data.h5'],
                             platform='Seurat',
                             project='cohorts')
    """

    if os.path.exists(job_record_file):
        #you're on a cloned instance that was created from this job
        job = notebook_job(id=open(job_record_file, "r").read().rstrip())
        print(
            "You are on a cloned instance created from notebook job %s in status %s."
            % (job.id, job.status))
        if len(job.ledger_output) > 0:
            print(
                "The following output files are available in the curent directory of this IDE:"
            )
            for f in job.ledger_output:
                print(f)
        print(
            "To clear this job and schedule another job from this IDE instance, run:"
        )
        print("hisepy.clear_notebook_job()")
        return job
    elif is_derived_instance():
        #we're on a scheduled instance, so return an empty job
        return notebook_job()
    notebook = current_notebook()
    payload = validate_schedule_input(output_files, input_data, platform,
                                      project, notebook)

    if prompt:
        if not prompt_for_platform(
                payload[CONFIG['SCHEDULER']['PLATFORM_FIELD']], output_files,
                notebook):
            print("Not scheduling.")
            return None

    print("Scheduling...")
    headers = get_bearer_token_header()
    endpoint = "https://%s/%s" % (hise_server(),
                                  CONFIG['TOOLCHAIN']['SCHEDULER_PATH'])
    resp = requests.post(endpoint, json=payload, headers=headers)
    if resp.status_code != 200:
        raise Exception("Request to %s failed with status %d. %s" %
                        (endpoint, resp.status_code, resp.text))
    job = notebook_job(obj=json.loads(resp.text))
    print("Scheduled.")
    return job


#are we running on an instance that's purpose-built for the task we're already doing?
#e.g. notebook scheduler, dash app?
def is_derived_instance():
    return os.path.exists(derived_instance_flag_file)


def validate_schedule_input(output_files, input_data, platform, project,
                            notebook):
    nbtokens = notebook.split("/")

    if platform is None:
        platform = CONFIG['SCHEDULER']['PLATFORM_DEFAULT']

    payload = {
        CONFIG['SCHEDULER']['NOTEBOOK_NAME_FIELD']: nbtokens[-1],
        CONFIG['SCHEDULER']['INSTANCE_NAME_FIELD']: IDEInstance().friendlyName,
        CONFIG['SCHEDULER']['NOTEBOOK_PATH_FIELD']: "/".join(nbtokens[0:-1]),
        CONFIG['SCHEDULER']['PLATFORM_FIELD']: platform
    }
    if project is not None:
        payload[CONFIG['SCHEDULER']['PROJECT_FIELD']] = project

    if platform == CONFIG['SCHEDULER']['PLATFORM_LOUVAIN']:
        if input_data is None or type(input_data) is not pandas.DataFrame:
            raise TypeError(
                "Notebook platform %s requires input_data of type pandas.DataFrame"
                % (CONFIG['SCHEDULER']['PLATFORM_LOUVAIN']))
        elif output_files is not None:
            raise TypeError("Notebook platform %s does not take output files" %
                            (CONFIG['SCHEDULER']['PLATFORM_LOUVAIN']))
        else:
            #this might take a bit, so give the user some notice
            print("Converting and normalizing input data...")
            payload[CONFIG['SCHEDULER']['INPUT_FILES_FIELD']] = [
                convert_and_normalize_dataframe(input_data)
            ]

    else:
        if output_files is None or type(output_files) is not list or len(
                output_files) == 0:
            raise TypeError(
                "You must specify a list of at least one expected output file using the output_files argument"
            )
        else:
            for f in output_files:
                if " " in f:
                    raise TypeError(
                        "%s is an invalid output file. Spaces are not allowed in output file names."
                        % (f))
            payload[CONFIG['SCHEDULER']['OUTPUT_FILES_FIELD']] = output_files

    return payload


def convert_and_normalize_dataframe(df):
    #TODO: actually normalize
    dfcsv = "scheduler_input_data_%06d.csv" % random.randint(0, 1000000)
    df.to_csv(dfcsv)
    return dfcsv


def prompt_for_platform(platform, output_files, nb_file):
    if platform == CONFIG['SCHEDULER']['PLATFORM_LOUVAIN']:
        print(
            "About to execute a louvain dimension reduction of your data on a DataProc cluster."
        )
        print(
            "I expect this job to produce a csv file that I will copy into HISE"
        )
        print(
            "and which you can download using the job object this function returns."
        )
        print(
            "You can also close this instance down and clone it later to return to this point,"
        )
        print(
            "or you can download the resulting csv into any other IDE instance using the read_files method."
        )

    else:
        print("About to schedule notebook %s for run on a large instance." %
              (nb_file))
        print(
            "I will run all the cells in the notebook, only skipping this schedule function."
        )
        print("I expect this notebook to produce the following output files:")
        for f in output_files:
            print("\t%s" % (f))
        print(
            "I will copy those files back to HISE where they will be available for later download into this or another IDE instance."
        )

    print("OK? (y/n) ", end="")
    resp = input()
    return len(resp) > 0 and resp.lower()[0] == "y"


@with_default_logging
def get_notebook_job(job_id=None):
    """
    Get the instance of a particular notebook job.

    Parameters:
        job_id (str): string of job_id. This job_id is created when making a 
            hp.schedule_notebook()
    Returns:
        A notebook_job object.
    """

    if job_id is None:
        if os.path.exists(job_record_file):
            job_id = open(job_record_file, "r").read().rstrip()
        else:
            raise Exception(
                "Job Id not specified, and no schedule record found on instance"
            )
    return notebook_job(id=job_id)


@with_default_logging
def clear_notebook_job():
    """
    Clear the record of most recent job. This will not delete the job or have any effect on its status. Using this
    function will allow to to schedule another job.
    """
    if os.path.exists(job_record_file):
        job_id = open(job_record_file, "r").read().rstrip()
        os.remove(job_record_file)
        print("Cleared job %s" % (job_id))
    else:
        print("No job record found")


@with_default_logging
class notebook_job:
    """
    A class representing a notebook job.

    Attributes:
        id (str): UUID for notebook job.
        status (str): Status of notebook job.
    """

    def __init__(self, id=None, obj=None):
        self.id = id
        self.status = "Unknown"
        self.ledger_output = {}

        if obj is not None:
            self.init_from_object(obj)
        elif self.id is not None:
            self.reload()

    def init_from_object(self, obj):
        if CONFIG['SCHEDULER']['JOB_ID_FIELD'] in obj:
            self.id = obj[CONFIG['SCHEDULER']['JOB_ID_FIELD']]
        else:
            raise Exception("No job id found in json object")

        if CONFIG['SCHEDULER']['LEDGER_OUTPUT_FIELD'] in obj:
            for fid in obj[CONFIG['SCHEDULER']['LEDGER_OUTPUT_FIELD']]:
                self.ledger_output[fid] = obj[CONFIG['SCHEDULER']
                                              ['LEDGER_OUTPUT_FIELD']][fid]

        if CONFIG['SCHEDULER']['STATUS_FIELD'] in obj:
            self.status = obj[CONFIG['SCHEDULER']['STATUS_FIELD']]
        else:
            raise Exception("No status found in json object")

    def reload(self):
        if self.id is None:
            print("job id is empty, not reloading")
            return

        headers = get_bearer_token_header()
        endpoint = "https://%s/%s/%s" % (
            hise_server(), CONFIG['TOOLCHAIN']['SCHEDULER_PATH'], self.id)
        resp = requests.request("GET", endpoint, headers=headers)
        if resp.status_code != 200:
            raise Exception("Request to %s failed with status %d. %s" %
                            (endpoint, resp.status_code, resp.text))
        self.init_from_object(json.loads(resp.text))

    def trace(self):
        return trace(self.trace_id)

    def check_status(self):
        self.reload()
        return self.status

    def is_completed(self, reload=True):
        if reload:
            self.reload()
        return self.status == CONFIG['SCHEDULER']['JOB_COMPLETE_STATUS']

    def download_output(self):
        if len(self.ledger_output) > 0:
            return download_files(self.ledger_output)
        else:
            print(
                "Job %s in status %s currently has no output. Try again later."
                % (self.id, self.status))
            return None


class trace:
    """
    A class representing a trace object. Used to allow re-execution or file retrieval for a particular job id

    Attributes:
        id (str): UUID for scheduled notebook
        file_ids (list): List of file_ids
    """

    def __init__(self, id):
        self.id = id
        self.file_ids = []
        self.reload()

    def reload(self):
        if self.id is None:
            print("Trace Id is empty, not reloading")
            return

        headers = get_bearer_token_header()
        endpoint = "https://%s/%s/%s" % (hise_server(), trace_path, self.id)
        resp = requests.request("GET", endpoint, headers=headers)
        if resp.status_code != 200:
            raise Exception("Request to %s failed with status %d. %s" %
                            (endpoint, resp.status_code, resp.text))
        j_obj = json.loads(resp.text)
        if type(j_obj) is list and len(j_obj) > 0:
            j_obj = j_obj[0]

        if CONFIG['SCHEDULER']['FILE_IDS_FIELD'] in j_obj:
            for f in j_obj[CONFIG['SCHEDULER']['FILE_IDS_FIELD']]:
                self.file_ids.append(f)

        if CONFIG['SCHEDULER']['TITLE_FIELD'] in j_obj:
            self.title = j_obj[CONFIG['SCHEDULER']['TITLE_FIELD']]
        else:
            self.title = "Trace %s" % self.id
