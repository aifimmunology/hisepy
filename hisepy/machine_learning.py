'''
Module for handling AI/ML SDK interactions 

TODO: better name for this module? remote_processer, training_scheduler, remote_job_handler, others...? 

'''

import os 
import json 
import requests 
import hisepy.common_utils as cu
from hisepy.auth import get_bearer_token_header

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def validate_cache_file_set_params(fileset_id, study_space_id):
    assert fileset_id is not None, "You must specify a fileset_id"
    assert study_space_id is not None, "You must specify a study_space_id"
    assert type(fileset_id) is str, "fileset_id must be of type string"
    assert type(study_space_id) is str, "study_space_id must be of type string"
    return 

def cache_file_set(file_set_id, study_space_id):
    '''
    Downloads all files to /home/workspace/input that pertains to a given file_set_id 

    Parameters: 
        file_set_id (str) : unique identifier for a bundle of files in a Study 
        study_space_id (str) : unique identifier for a study in the collaboration space
    '''
    # TODO: downloaded files need to follow /input/<fileSetID>/.../<downloaded_file>
    # TODO: I think a backend endpoint might be needed here..

    validate_cache_file_set_params(fileset_id, study_space_id)

    # list the filesets available
    fileset_df = list_filesets(study_space_id)

    # download all files in the fileset, making sure filesetid is somewhere in the download path 
    # TODO: separate endpoint needed to make sure we have file_set_id in the downloaded path (i.e .../input/.../<file_set_id>/...)

    return


def get_training_images(): 
    '''
    Returns a data.frame of training images the user has visibility on 

    Returns: 
        data.frame of accessible training images 
    '''
    endpoint = cu.hise_url('tracer', 'training_image')
    return cu.parse_hise_response(requests.request("GET",
                                                    endpoint,
                                                    headers=get_bearer_token_header()))


def get_training_job_output(job_id): 
    """
    Returns output of a training job. An error will be returned if the job queried was not successfully completed.

    Parameters:
        job_id (str): unique idenfifier for a training job

    Returns: 
        data.frame with columns [title, description, trainingImage, outputFileIds, model, availability, promoted]
    """
    return 


def get_training_job_status(job_id):
    """
    Returns status of a training job.

    Parameters:
        job_id (str): unique identifier for a training job

    Returns: 
        status (str): status of the training job
    """

    return 

def list_filesets(study_space_id):
    """ 
    Returns a list of filesets for a given study 

    Parameters:
        study_space_id (str) : a unique identifier for a study in the collaboration space

    Returns: 
        data.frame with columns ['id', 'studySpaceId', 'title','description','fileIds']
        
    Example: 
        hp.list_filesets(study_space_id='c39e3ae5-ec11-4f02-b89d-255945c5788e')
    """
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
    obj_df_sub = obj_df.loc[obj_df['deleted'].eq('false'), ]
    return obj_df_sub[[
        'id', 'studySpaceId', 'title', 'description', 'fileIds'
    ]].reset_index(drop=True)

def list_file_sets(study_space_id : str): 
    """ 
    Returns a list of filesets for a given study 

    Parameters:
        study_space_id (str) : a unique identifier for a study in the collaboration space

    Returns: 
        data.frame with columns ['id', 'studySpaceId', 'title','description','fileIds']
        
    Example: 
        hp.list_file_sets(study_space_id='c39e3ae5-ec11-4f02-b89d-255945c5788e')
    """
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
    obj_df_sub = obj_df.loc[obj_df['deleted'].eq('false'), ]
    return obj_df_sub[[
        'id', 'studySpaceId', 'title', 'description', 'fileIds'
    ]].reset_index(drop=True)


def list_training_jobs():
    """
    Returns a list of training jobs the user has visibility on

    Returns: 
        data.frame of available training jobs with the following columns: [ ] # TODO: columns to show
    """ 
    return

def validate_review_job_params(job_id, approve, review_notes, study_space_id): 
    assert job_id is not None, "You must specify a job_id"
    assert type(job_id) is str, "job_id must be of type string"
    assert approve is not None, "You must specify whether to approve the job"
    assert type(approve) is bool, "approve must be of type boolean"
    assert review_notes is not None, "You must specify review notes"
    assert type(review_notes) is str, "review_notes must be of type string"
    assert study_space_id is not None, "You must specify a study_space_id"
    assert type(study_space_id) is str, "study_space_id must be of type string"


    return

def review_job(job_id : str,
                approve : bool, 
                review_notes : str, 
                study_space_id : str):
    """
    Review a training job for approval or rejection.

    Parameters:
        job_id (str) : unique identifier for a training job
        approve (bool) : whether to approve the job
        review_notes (str) : notes for the review
        study_space_id (str) : unique identifier for the study space

    Returns: 
        None
    """
    # assert parameters are all good 
    validate_review_job_params(job_id,
                                approve,
                                review_notes,
                                study_space_id)

    if approve:
        pass
        # TODO: change availability field, studySPaceId of job, store injected code to GitHub 
    elif not approve: 
        pass
        # TODO: change availability field, delete resources 

    return 


def start_training_run(provider, gpu_count, worker_count, file_set_id, tags):
    """
    """
    return #return some job id 


def stop_training_job(job_id): 
    TrainingJob(job_id).stop_job({})
    return 



class TrainingJob: 
    """
    Class representing a Training Job
    
    Attributes: 
        id (str)
    """

    def __init__(self,
                 id: str, 
                 provider: str = 'ray', # TODO: url is going to depend on provider...? 
                 obj):
        self.id = id
        self.status = None
        self.file_availabilities = CONFIG['BIO_SDK_FILE_AVAILABILITIES']
        self.__url = cu.hise_url('') # TODO: what is the url for this?
        if obj is not None: 
    
    # load the training job object and return info to the user 
    def reload(self): 
        return 

    def check_status(self): 
        self.reload()
        return self.status 
    
    def stop_job(self, data):
        data['id'] = self.id 
        return requests.request({"POST",
                                self.__url, # URL to ray/beaker 
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})
    
    def promote_job(self, data): 
        data['id'] = self.id 
        return requests.request({"PUT",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})
    
    def approve_job(self, data): 
        data['id'] = self.id 
        return requests.request({"PUT",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})
    
    def reject_job(self, data): 
        data['id'] = self.id
        return requests.request({"PUT",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})
    
    def start_training_run(self, data): 
        data['id'] = self.id
        return requests.request({"POST",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})

    
# TODO: is this atually needed...? 
class traceJob:
    """
    querying tracer/trainingJob 
    """ 

    def __init__(self, training_job_id : str): 
        self.__url = cu.hise_url('tracer', 'training_job', training_job_id) # TODO: OR this needs to point to beaker/Ray in order to retrieve job status
        try: 
            job = cu.hise(get(self.__url))
            for key, value in job.items(): 
                setattr(self, key, value) 
        except: 
            raise Exception(
                "You do not have access to training job %s. Either you don't have access to the Study Space, or you don't have permission to view this job." % training_job_id
            )

    
    def __update(self, data): 
        data['id'] = self.id
        return requests.request("PUT", 
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header())

    def get_job_status(self):
        pass 


     




 

    
