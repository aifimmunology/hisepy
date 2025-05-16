import os 
import json 
import requests 
import tempfile 
import subprocess
import pandas as pd 
import shutil
import tarfile
import hisepy.common_utils as cu
import hisepy.formatter as fmt
import hisepy.ray_transformer as rt
from hisepy.auth import get_bearer_token_header, HiseUser, IDEInstance, ide_instance_guid

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
                               review_notes : str):
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
                        cpu_count : int, 
                        gpu_count : int, 
                        memory_size : int,
                        worker_count: int,
                        training_job_file_path : str, 
                        title : str,
                        description : str,
                        file_set_id: str, 
                        additional_dirs : list = None, 
                        additional_files : list = None,           
                        requirements_file_path : str = None,
                        image_id : str = None, 
                        ): 
    '''
    '''
    
    # create training_job temp directory
    training_job_temp_dir = '{}/{}'.format(CONFIG['STORES']['TEMP_STORE'], CONFIG['TEMP_FOLDERS']['TRAINING_JOB_TMP'])
    if not os.path.exists(training_job_temp_dir):
        os.makedirs(training_job_temp_dir)
    tmpdirname = tempfile.mkdtemp(prefix='{}/'.format(training_job_temp_dir))

    # set permissions so job-orchestrator can read and copy this file
    os.chmod(tmpdirname, 0o777)

    job_obj = TrainingJob(cpu_count=cpu_count,
                            gpu_count=gpu_count,
                            memory_size=memory_size,
                            worker_count=worker_count,
                            title=title,
                            description=description,
                            file_set_id=file_set_id,
                            requirements_file_path=requirements_file_path,
                            training_job_file_path=training_job_file_path,
                            additional_dirs=additional_dirs,
                            additional_files=additional_files,
                            image_id = image_id,
                            work_dir=tmpdirname)
    job_obj._validate_params()

    # fork on provider
    if provider == 'ray':
        # conform to ray and save to temp directory
        job_obj.convert_training_job_file_to_ray() 

        # write requirements.txt file to temp directory
        job_obj.create_req_txt()

        # copy any additional scripts or modules the user supplies 
        job_obj.copy_scripts_and_dirs_to_temp()

        # create tar file of artifacts
        job_obj.create_training_job_image()

        # submit ray job
        job_response = job_obj.submit_ray_workflow() 

    elif provider == 'beaker':
        
        # copy training job file to temp directory 
        shutil.copy(job_obj.training_job_file_path, '{}/{}'.format(job_obj.work_dir, CONFIG['TEMP_FILES']['JOB_ENTRYPOINT_FILE']))

        # write requirements.txt file to temp directory
        job_obj.create_req_txt()

        # copy any additional scripts or modules the user supplies 
        job_obj.copy_scripts_and_dirs_to_temp()

        # create tar file of artifacts
        job_obj.create_training_job_image()

        # submit beaker workflow 
        job_response = job_obj.submit_beaker_workflow()

    else: 
        raise Exception("Provider must be either 'ray' or 'beaker'")
    
    # clean up temp directory 
    if os.path.exists(tmpdirname):
        shutil.rmtree(tmpdirname)
    return job_response
    
class TrainingJob: 
    """
    Class representing a Training Job
    
    Attributes: 
        id (str)
    """

    def __init__(self,
                 provider : str = 'ray',
                 cpu_count : int = 1, 
                 gpu_count : int = 0,
                 memory_size : int = 0,
                 worker_count : int = 1,
                 title : str = None,
                 description : str = None,
                 tags : list = [],
                 file_set_id : str = None, # TODO: training job needs to work with this param after MVP presentation
                 requirements_file_path : str = None,
                 training_job_file_path : str = None,
                 additional_dirs : list = None,
                 additional_files : list = None, 
                 image_id : str = None, 
                 work_dir : str = None,
                 job_id = None):
        self.__url = cu.hise_url('tracer', 'training_job')
        self.__ray_workflow_url = cu.hise_url('job_orchestrate', 'ray_workflow')
        self.__beaker_workflow_url = cu.hise_url('job_orchestrate', 'beaker_workflow')

        # initialize attributes
        self.provider = provider
        self.cpu_count = cpu_count
        self.gpu_count = gpu_count
        self.memory_size = memory_size
        self.worker_count = worker_count
        self.title = title
        self.description = description
        self.tags = tags
        self.file_set_id = file_set_id
        self.requirements_file_path = requirements_file_path
        self.training_job_file_path = training_job_file_path
        self.additional_dirs = additional_dirs
        self.additional_files = additional_files
        self.additional_files = additional_files
        self.image_id = image_id
        self.work_dir = work_dir
        self.artifacts_path = tarfile_path = '{wd}/artifacts.tar.gz'.format(wd=self.work_dir)

        if job_id is not None:
            self.job_id = job_id
    
    def _validate_params(self):
        # check types 
        if type(self.cpu_count) is not int:
            raise Exception("cpu_count must be an int")
        elif type(self.gpu_count) is not int:
            raise Exception("gpu_count must be an int")
        elif type(self.memory_size) is not int:
            raise Exception("memory_size must be an int")
        elif type(self.worker_count) is not int:
            raise Exception("worker_count must be an int")
        elif self.title is not None and type(self.title) is not str:
            raise Exception("title must be a string")
        elif self.description is not None and type(self.description) is not str:
            raise Exception("description must be a string")
        elif self.tags is not None and type(self.tags) is not list:
            raise Exception("tags must be a list")
        elif self.file_set_id is not None and type(self.file_set_id) is not str:
            raise Exception("file_set_id must be a string")
        elif self.additional_dirs is not None and type(self.additional_dirs) is not list: 
            raise Exception("additional_dirs must be a list")
        elif self.additional_files is not None and type(self.additional_files) is not list:
            raise Exception("additional_files must be a list")
        elif self.image_id is not None and type(self.image_id) is not str:
            raise Exception("image_id must be a string")

        # no white spaces in filepaths 
        if self.requirements_file_path is not None:
            if cu.string_contains_whitespaces(self.requirements_file_path):
                raise Exception("requirements_file_path must not contain spaces")
        if self.training_job_file_path is not None: 
            if cu.string_contains_whitespaces(self.training_job_file_path):
                raise Exception("training_job_file_path must not contain spaces")
        if self.additional_dirs is not None: 
            for d in self.additional_dirs:
                if cu.string_contains_whitespaces(d):
                    raise Exception("additional_dirs must not contain spaces")
        if self.additional_files is not None:
            for f in self.additional_files:
                if cu.string_contains_whitespaces(f):
                    raise Exception("additional_files must not contain spaces")
        
        # check that the file exists
        if self.requirements_file_path is not None:
            if not os.path.exists(self.requirements_file_path):
                raise Exception("requirements_file_path does not exist")
        if self.training_job_file_path is not None:
            if not os.path.exists(self.training_job_file_path):
                raise Exception("training_job_file_path does not exist")
        return 

    def get_job(self): 
        return cu.parse_hise_response(requests.get(self.__url,
                                            headers=get_bearer_token_header()))
    
    def list_all_jobs(self):
        return cu.parse_hise_response(requests.get(self.__url,
                            headers=get_bearer_token_header()))
    
    
    def convert_training_job_file_to_ray(self):

        # first check if the file is a notebook or a script
        if self.training_job_file_path.endswith('.ipynb'):
            # convert notebook to script
            python_script_to_convert = '{}/{}'.format(self.work_dir, CONFIG['TEMP_FILES']['NBCONVERT_TMP_FILE'])
            cu.convert_notebook_to_script(self.training_job_file_path,
                                          python_script_to_convert)
        elif self.training_job_file_path.endswith('.py'): 
            # get the script file name
            python_script_to_convert = self.training_job_file_path
        else: 
            raise Exception("training_job_file_path must be a .ipynb or .py file")
        
        # transform script to conform to Ray
        rt.transform_to_ray(python_script_to_convert, 
                            '{}/{}'.format(self.work_dir, CONFIG['TEMP_FILES']['JOB_ENTRYPOINT_FILE']))
        return 

    def copy_scripts_and_dirs_to_temp(self): 

        # master list of directories and additional files 
        app_files = self.additional_files + self.additional_dirs

        # copy each directory and file to the temp directory, preserving the relative path to training_job_file_path
        for f in app_files:
            # check if the file is a directory or a file
            if os.path.isdir(f):
                # copy the directory to the temp directory
                shutil.copytree(f, '{}/{}'.format(self.work_dir, os.path.basename(f)))
            elif os.path.isfile(f):
                # copy the file to the temp directory
                shutil.copy(f, '{}/{}'.format(self.work_dir, os.path.basename(f)))
            else:
                raise Exception("additional_files must be a list of files or directories") 
        return 

    def create_training_job_image(self): 
        with tarfile.open(self.artifacts_path, 'w:gz') as tar: 
            tar.add(self.work_dir, arcname='')
        return 
        
    def create_req_txt(self):
        """
        Create requirements.txt file based on the conda environment
        """
        # TODO: does this work if a requirements.txt file is passed in?

        # check that we have a training job file 
        if self.training_job_file_path is None:
            raise Exception("training_job_file_path is not set")

        # if the user doesn't pass one, use pip-compile and pip-tools to create one 
        if self.requirements_file_path is None:
            subprocess.run([
                'pipreqs', '--savepath', '{wd}/requirements.in'.format(
                    wd=self.work_dir),
                '{}'.format(self.work_dir)
            ],
                           check=True,
                           capture_output=True)
            subprocess.run([
                'pip-compile', '--no-annotate', '--no-header', '--quiet',
                '--strip-extras', '{wd}/requirements.in'.format(
                    wd=self.work_dir)
            ],
                           check=True)
        else:
            subprocess.run([
                'pip-compile', '--no-annotate', '--no-header', '--quiet',
                '--strip-extras',
                '--output-file={wd}/{app}/requirements.txt'.format(
                    wd=self.work_dir, app=os.path.dirname(
                        self.app_filepath)), self.requirements
            ],
                           check=True)

    def submit_ray_workflow(self):
        ray_args = {'accountGuid': HiseUser().current_account_guid,
                    'projectGuid': IDEInstance().destinationProjectGuid,
                    'fileSetId': self.file_set_id,
                    'instanceId': ide_instance_guid(), 
                    'title': self.title,
                    'description': self.description,
                    'tags': self.tags,
                    'jobRequest' : {
                        'headConfig' : { # TODO: what should this headconfig actually be based from user's params
                            "cpus": 1,
                            "gpu":0,
                            "memory" :"1"
                        },
                        'workerConfig' : { 
                            'replicas' : self.worker_count,
                            'cpus' : self.cpu_count,
                            'gpu' : self.gpu_count,
                            'memory': str(self.memory_size),
                        }
                    },
                    "harvestArtifactsRequest": {
                        "artifactsFileName": self.artifacts_path,
                        "packageManager": "pip"
                    }}
        if self.image_id is not None: 
            ray_args['imageId'] = self.image_id
        return cu.parse_hise_response(requests.post(self.__ray_workflow_url,
                            json=ray_args,
                            headers=get_bearer_token_header()))

    def submit_beaker_workflow(self): 
        beaker_args = {'accountGuid': HiseUser().current_account_guid,
                       'projectGuid': IDEInstance().destinationProjectGuid,
                       'fileSetId': self.file_set_id,
                       'instanceId': ide_instance_guid(), 
                       'title': self.title,
                       'description': self.description,
                       'tags': self.tags,
                       'jobRequest' : {
                            'headConfig' : { # TODO: what should this headconfig actually be based from user's params
                                "cpus": 1,
                                "gpu":0,
                                "memory" :"1"
                            },
                        'workerConfig' : { 
                            'replicas' : self.worker_count,
                            'cpus' : self.cpu_count,
                            'gpu' : self.gpu_count,
                            'memory': str(self.memory_size),
                            }
                        },
                        "harvestArtifactsRequest": {
                            "artifactsFileName": self.artifacts_path,
                            "packageManager": "pip"
                    }}
        if self.image_id is not None:
            beaker_args['imageId'] = self.image_id
        return cu.parse_hise_response(requests.post(self.__beaker_workflow_url,
                            json=beaker_args,
                            headers=get_bearer_token_header()))


    """
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

        def get_all_images(self):
            return 
            