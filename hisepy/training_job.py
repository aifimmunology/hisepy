import os 
import json 
import requests 
import pandas as pd 
import hisepy.common_utils as cu
import hisepy.formatter as fmt
from hisepy.auth import get_bearer_token_header, HiseUser

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def list_all_training_jobs():
    '''
    '''
    cols_to_keep = CONFIG['TRACER']['TRAINING_JOB_COLS']
    jobs = TrainingJob().list_all_jobs()
    job_df = pd.DataFrame() 
    for j in jobs: 
        job_df = pd.concat([job_df, fmt.reshape_custom_metadata(j, False)])
    return job_df[cols_to_keep].sort_values(by='added', ascending=False) # NOTE: outputFileIds field is missing for some entries  

def get_training_job(job_id : str):
    '''
    '''
    cols_to_keep = CONFIG['TRACER']['TRAINING_JOB_COLS']
    try: 
        return fmt.reshape_custom_metadata(TrainingJob(job_id).get_job()[0], False)[cols_to_keep]
    except: 
        print("job has missing column that's expected: {}".format(job_id)) # TODO: fix endpoint 
        return 

def get_training_image(image_id : str): 
    '''
    '''
    return 

def validate_review_run_params(study_space_id : str,
                               job_id : str, 
                               image_id : str, 
                               approve : bool,
                               review_notes : str)
    '''
    '''
    if job_id is None and image_id is None: 
        raise Exception("job_id, or image_id must be submitted") 
    if type(study_space_id) is not str: 
        raise Exception("study_space_id must be a string") 
    elif type(job_id) is not str: 
        raise Exception("job_id must be a string") 
    elif type(image_id) is not str: 
        raise Exception("image_id must be a string") 
    elif type(approve) is not bool: 
        raise Exception("approve must be a boolean") 
    elif type(review_notes) is not str: 
        raise Exception("review_notes must be a str")
    return 
    
'''
def review_run(study_space_id, job_id, image_id, approve, review_notes):

    # validate params
    validate_review_run_params(study_space_id, job_id, image_id, approve, review_notes) 

    # get job or image 
    if job_id is not None: 
        job = get_training_job(job_id)
        job_availability = job['availability'] 

        # ensure availability flag is "bio_sdk_under_review"
        if job_availability != CONFIG['BIO_SDK_FILE_AVAILABILITIES']['UNDER_REVIEW']: 
            raise Exception("Can not review job: {}. job availability flag is not 'bio_sdk_under_review'".format(job['id']]))

    # TODO: implement
    if image_id is not None: 
        image = get_training_image(image_id) 
        image_availability = image['availability']

        # ensure availability flag is "bio_sdk_under_review"
        if image_availability != CONFIG['BIO_SDK_FILE_AVAILABILITIES']['UNDER_REVIEW']: 
            raise Exception("Can not review image: {}. image availability flag is not 'bio_sdk_under_review'".format(image['id']))

    if approve is True: 

        # update the Process.availability and the Files' availability fields to "available" and update their availability_notes field with the reviewNotes stuff
        
        return 
    elif approve is False: 
        return 
'''

# not needed for milestone 1
def stop_training_job():
    return 

def get_training_job_status(job_id):
    return get_training_job(job_id)[['status']]

def start_training_run(provider : str, 
                        comput_instance_count : int,
                        worker_count: int,
                        file_set_id: str): 
    '''
    '''
    return 
    
class TrainingJob: 
    """
    Class representing a Training Job
    
    Attributes: 
        id (str)
    """

    def __init__(self, job_id = None):
        self.__url = cu.hise_url('tracer', 'training_job')
        if job_id is not None:
            self.job_id = job_id
    
    def get_job(self): 
        return cu.parse_hise_response(requests.get(self.__url,
                                            headers=get_bearer_token_header()))
    
    def list_all_jobs(self):
        return cu.parse_hise_response(requests.get(self.__url,
                            headers=get_bearer_token_header()))
    
        def promote_job(self, data): 
        data['id'] = self.id 
        return requests.request({"PUT",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})
    
    def approve_job(self, data): 
        return requests.request({"PUT",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header()}

    def reject_job(self, data): 
        data['id'] = self.id
        return requests.request({"PUT",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})
    
    def start_training_run(self, data): 
        return 

    """
    def stop_job(self, data):
        data['id'] = self.id 
        return requests.request({"POST",
                                self.__url, # URL to ray/beaker 
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})
   
        data['id'] = self.id
        return requests.request({"POST",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header()})
    """


def get_training_image(image_id : str): 
    '''
    '''
    return 


class TrainingImage: 
    """
    Class representing a Training Image
    
    Attributes: 
        id (str)
    """

    def __init__(self, image_id = None):
        self.__url = cu.hise_url('tracer', 'training_image')
        if image_id is not None:
            self.image_id = image_id

        def get_image(self):
            return cu.parse_hise_response(requests.get(self.__url,
                    headers=get_bearer_token_header()))

        def get_all_images(self)