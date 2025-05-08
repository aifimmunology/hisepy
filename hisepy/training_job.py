import os 
import json 
import requests 
import hisepy.common_utils as cu
from hisepy.auth import get_bearer_token_header

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def list_all_jobs():
    return TrainingJob().list_all_jobs()

def get_job(job_id):
    return TrainingJob(job_id).get_job()

def stop_training_job():
    return 

def get_training_job_status():
    return

    
class TrainingJob: 
    """
    Class representing a Training Job
    
    Attributes: 
        id (str)
    """

    def __init__(self, job_id = None):
        self.__url = cu.hise_url('tracer', 'training_job_filter')
        if job_id is not None:
            self.job_id = job_id
        """
            try: 
                query = {'id': job_id,
                        'accountGuid' : HiseUser().current_account_guid,
                        }
                training_job = requests.post(self.__url,
                                            headers=get_bearer_token_header(),
                                            data=json.dumps({'filter': query}))
                for key, value in training_jobs.items():
                    setattr(self, key, value)
            except: 
                raise Exception(
                    "Something went wrong when trying to get the training job. "
                ) # TODO: what validations are in place from backend? 
        else: 
            self.__all_jobs_url = cu.hise_url('tracer', 'training_job_filter')
            try: 
                training_jobs = cu.hise_get(self.__all_jobs_url) # TODO: maybe POST + filter? 
                for key, value in training_jobs.items():
                    setattr(self, key, value)
            except: 
                raise Exception(
                    "Something went wrong when trying to get the training job. "
                ) # TODO: what validations are in place from backend? 
        """
    
    # load the training job object and return info to the user 
    def reload(self): 
        return 

    def check_status(self): 
        self.reload()
        return self.status 
    
    def get_job(self): 
        query = {'id': self.job_id,
                'accountGuid' : HiseUser().current_account_guid
                }
        return cu.parse_hise_response(requests.post(self.__url,
                                            headers=get_bearer_token_header(),
                                            data=json.dumps({'filter': query})))
    
    def list_all_jobs(self):

        # filter for user/account
        query = {'accountGuid' : HiseUser().current_account_guid,
                "auditInfo.addedUser" : HiseUser().Email # TODO: filter on visibility field instead 
                }
        return cu.parse_hise_response(requests.post(self.__url,
                            data=json.dumps({'filter': query}),
                            headers=get_bearer_token_header()))

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
