import os
import json
import requests
import tempfile
import subprocess
import pandas as pd
import shutil
import tarfile
import ast
import hisepy.common_utils as cu
import hisepy.formatter as fmt
import hisepy.reader as hpr
import hisepy.ray_transformer as rt
from hisepy.auth import get_bearer_token_header, HiseUser, IDEInstance, ide_instance_guid
from hisepy.upload import get_default_project
from hisepy.upload_utils import do_conda_export, get_ide_env_name, check_default_project
from hisepy.logging import with_default_logging, logger

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


@with_default_logging
def start_training_run(
    training_job_file_path: str,
    title: str,
    description: str,
    file_set_id: str,
    provider: str = 'ray',
    head_cpu_count: int = 1,
    head_gpu_count: int = 0,
    head_memory_size: int = 10,
    worker_cpu_count: int = 1,
    worker_gpu_count: int = 0,
    worker_memory_size: int = 10,
    worker_count: int = 0,
    additional_dirs: list = [],
    additional_files: list = [],
    project: str = None,
    requirements_file_path: str = None,
    image_id: str = None,
    use_conda: bool = False,
    output_file_size: int = 5,
):
    '''
    Starts a remote job for a python script

    Parameters: 
        training_job_file_path (str): path to training job script
        title (str): training job title
        description (str): training job description
        file_set_id (str): file set ID used as the training job input
        provider (str) (Optional): 'ray' or 'beaker'. default is ray
        head_cpu_count (int) (Optional): number of CPUs to use on the Ray head node. default is 1
        head_gpu_count (int) (Optional): number of GPUs to use on the Ray head node. default is 0
        head_memory_size (int) (Optional): memory size for the Ray head node (GB). default is 10
        worker_cpu_count (int) (Optional): number of CPUs to use on the Ray worker node(s). default is 1
        worker_gpu_count (int) (Optional): number of GPUs to use on the Ray worker node(s). default is 0 
        worker_memory_size (int) (Optional): memory size for the Ray worker node(s) (GB). default is 10
        worker_count (int) (Optional): number of workers to use. default is 0
        additional_dirs (list): (Optional) list of directories your script requires. default is []
        additional_files (list): (Optional) list of files your script requires. default is []
        project (str): (Optional) short name of project that Ray job cost will be billed under. default is project selected upon IDE creation        
        requirements_file_path (str): (Optional) path to requirements.in file
        image_id (str): (Optional) image ID for the training job. default is None
        use_conda (bool): (Optional) indicator of whether to use conda environment for training; default is False (pip)
        output_file_size (int): (Optional) estimated output file size (GB). default is 5 GB

    Returns: 
        dict with keys: [workflowName, executionId, status, message, providerDashboard, executionDetails]

    Examples: 
        # start a ray training job using the default settings (1 CPU, 0 GPUs, 1 GB memory, 1 worker)
        hp.start_training_run(
            training_job_file_path='/home/workspace/my_training_jobs/app.py',
            title='My Training Job',
            description='This is my training job',
            file_set_id='12345')

        # start a training run with the specified resources and helper scripts
        hp.start_training_run(
            cpu_count=2,
            gpu_count=1,
            memory_size=4,
            worker_count=2,
            training_job_file_path='/home/workspace/my_training_jobs/app.py',
            title='My Training Job',
            description='This is my training job',
            file_set_id='12345',
            additional_dirs=['/home/workspace/my_training_jobs/helpers'],
            additional_files=['/home/workspace/configs/config.json'])

    '''

    # create a training_job temp directory
    training_job_temp_dir = CONFIG['JOB_ORCHESTRATE'][
        'ARTIFACTS_PATH']  # '/home/workspace/.artifacts'
    if not os.path.exists(training_job_temp_dir):
        os.makedirs(training_job_temp_dir)

    # set destination project if not already set
    if project is None:
        project = get_default_project()
        print("Using default project: {}".format(project))
    check_default_project(project)

    job_obj = TrainingJob(use_conda=use_conda,
                          head_cpu_count=head_cpu_count,
                          head_gpu_count=head_gpu_count,
                          head_memory_size=head_memory_size,
                          worker_cpu_count=worker_cpu_count,
                          worker_gpu_count=worker_gpu_count,
                          worker_memory_size=worker_memory_size,
                          worker_count=worker_count,
                          title=title,
                          description=description,
                          file_set_id=file_set_id,
                          requirements_file_path=requirements_file_path,
                          training_job_file_path=training_job_file_path,
                          additional_dirs=additional_dirs,
                          additional_files=additional_files,
                          image_id=image_id,
                          work_dir=training_job_temp_dir,
                          output_file_size=output_file_size)
    job_obj._validate_params()

    # Branch based on provider
    if provider == 'ray':
        # prompt user if ray.init() or ray decorators exists
        # assuming if the user's script contains these, then they know what they're doing
        if rt.has_ray_init(job_obj.training_job_file_path):
            user_response = cu.prompt_user(
                CONFIG['PROMPTS']['RAY_INIT_EXISTS'])
            if not user_response:
                raise Exception("Training job submission cancelled by user")
            else:
                # prompt use
                cu.copy_files(
                    job_obj.training_job_file_path, '{}/{}'.format(
                        job_obj.work_dir,
                        CONFIG['TEMP_FILES']['JOB_ENTRYPOINT_FILE']))
        else:
            # conform to ray and save to temp directory
            job_obj.convert_training_job_file_to_ray()
    elif provider == 'beaker':
        # copy training job file to temp directory
        shutil.copy(
            job_obj.training_job_file_path,
            '{}/{}'.format(job_obj.work_dir,
                           CONFIG['TEMP_FILES']['JOB_ENTRYPOINT_FILE']))
    else:
        raise Exception("Provider must be either 'ray' or 'beaker'")

    if use_conda:
        # write environment.yml file to temp directory
        job_obj.create_env_yaml()
    else:
        # write requirements.txt file to temp directory
        job_obj.create_req_txt()

    # copy any user-supplied scripts or modules
    job_obj.copy_scripts_and_dirs_to_temp()

    # create tar file of artifacts
    job_obj.create_training_job_image()

    # submit job
    job_response = job_obj.submit_ray_workflow(
    ) if provider == 'ray' else job_obj.submit_beaker_workflow()
    return job_response


@with_default_logging
def review_training_job_run(job_id: str,
                            study_space_id: str,
                            review_notes: str = None):
    ''' 
    Approve or reject a training job run:

    Parameters: 
        job_id (str): ID of the training job to review
        study_space_id (str): ID of the study space that contains the job to be reviewed
        review_notes (str): notes for the review
    Returns: 
        dict with keys: [job, approved, message]
    Examples: 
        # approve a training job run
        hp.review_training_job_run(job_id='12345', study_space_id='67890', review_notes='Looks good!')

        # reject a training job run
        hp.review_training_job_run(job_id='12345', study_space_id='67890', review_notes='Needs more work')
    '''

    # validate params
    if job_id is not None and type(job_id) is not str:
        raise Exception("job_id must be a string")
    if study_space_id is not None and type(study_space_id) is not str:
        raise Exception("study_space_id must be a string")
    if review_notes is not None and type(review_notes) is not str:
        raise Exception("review_notes must be a string")

    # download outputs for review
    review_args = {
        'jobID': job_id,
        'accountGuid': HiseUser().current_account_guid,
        'instanceGuid': ide_instance_guid(),
    }
    dl_resp = cu.parse_hise_response(
        requests.post(cu.hise_url('hydration', 'review_job_output_path'),
                      json=review_args,
                      headers=get_bearer_token_header()))

    print("Training job output files downloaded to: {}".format(
        dl_resp['Path']))

    # prompt user to review the training job output
    user_response = cu.prompt_yn(
        CONFIG['PROMPTS']['REVIEW_JOB_OUTPUT'].format(job_id) +
        "\nWould you like to approve this job?")

    jobj = TrainingJob(job_id=job_id,
                       review_notes=review_notes,
                       approve=user_response,
                       study_space_id=study_space_id)
    return jobj.review_training_job()


class TrainingJob:
    """
    Class representing a training job
    
    Attributes: 
        id (str)
    """

    def __init__(
            self,
            provider: str = 'ray',
            use_conda: bool = False,
            head_cpu_count: int = 1,
            head_gpu_count: int = 0,
            head_memory_size: int = 10,
            worker_cpu_count: int = 1,
            worker_gpu_count: int = 0,
            worker_memory_size: int = 10,
            worker_count: int = 1,
            title: str = "",
            description: str = "",
            tags: list = [],
            file_set_id:
        str = "",  # TODO: training job needs to work with this param after MVP presentation
            requirements_file_path: str = "",
            training_job_file_path: str = "",
            additional_dirs: list = [],
            additional_files: list = [],
            image_id: str = "",
            work_dir: str = "",
            job_id: str = "",
            review_notes: str = "",
            approve: bool = None,
            study_space_id: str = "",
            output_file_size: int = 5):
        self.__url = cu.hise_url('tracer', 'training_job')
        self.__ray_workflow_url = cu.hise_url('job_orchestrate',
                                              'ray_workflow')
        self.__beaker_workflow_url = cu.hise_url('job_orchestrate',
                                                 'beaker_workflow')
        self.__review_job_url = cu.hise_url('job_orchestrate', 'review_job')

        # initialize attributes
        self.provider = provider
        self.package_manager = "conda" if use_conda else "pip"
        self.head_cpu_count = head_cpu_count
        self.head_gpu_count = head_gpu_count
        self.head_memory_size = head_memory_size
        self.worker_cpu_count = worker_cpu_count
        self.worker_gpu_count = worker_gpu_count
        self.worker_memory_size = worker_memory_size
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
        self.review_notes = review_notes
        self.approve = approve
        self.study_space_id = study_space_id
        self.artifacts_path = CONFIG['JOB_ORCHESTRATE'][
            'ARTIFACTS_TEMP_FILEPATH']  # '/home/workspace/temp/artifacts.tar.gz' #'{wd}/artifacts.tar.gz'.format(wd=self.work_dir)
        self.output_file_size = output_file_size

        if job_id is not None:
            self.job_id = job_id

    def _validate_params(self):
        # check types
        if type(self.head_cpu_count) is not int or self.head_cpu_count < 0:
            raise Exception("head_cpu_count must be a non-negative integer")
        elif type(self.head_gpu_count) is not int or self.head_gpu_count < 0:
            raise Exception("head_gpu_count must be a non-negative integer")
        elif type(
                self.head_memory_size) is not int or self.head_memory_size < 0:
            raise Exception("head_memory_size must be a non-negative integer")
        elif type(self.worker_count) is not int or self.worker_count < 0:
            raise Exception("worker_count must be a non-negative integer")
        elif self.head_cpu_count == 0 and (self.head_gpu_count > 0
                                           or self.head_memory_size > 0
                                           or self.worker_count == 0):
            raise Exception(
                "when head_cpu_count is 0, head_gpu_count and head_memory_size must be 0, "
                "and worker_count must be positive")
        elif self.worker_count > 0:
            if type(self.worker_cpu_count
                    ) is not int or self.worker_cpu_count <= 0:
                raise Exception("worker_cpu_count must be a positive integer")
            elif type(self.worker_gpu_count
                      ) is not int or self.worker_gpu_count < 0:
                raise Exception(
                    "worker_gpu_count must be a non-negative integer")
            elif type(self.worker_memory_size
                      ) is not int or self.worker_memory_size <= 0:
                raise Exception(
                    "worker_memory_size must be a positive integer")

        if self.title is not None and type(self.title) is not str:
            raise Exception("title must be a string")
        elif self.description is not None and type(
                self.description) is not str:
            raise Exception("description must be a string")
        elif self.tags is not None and type(self.tags) is not list:
            raise Exception("tags must be a list")
        elif self.file_set_id is not None and type(
                self.file_set_id) is not str:
            raise Exception("file_set_id must be a string")
        elif self.additional_dirs is not None and type(
                self.additional_dirs) is not list:
            raise Exception("additional_dirs must be a list")
        elif self.additional_files is not None and type(
                self.additional_files) is not list:
            raise Exception("additional_files must be a list")
        elif self.image_id is not None and type(self.image_id) is not str:
            raise Exception("image_id must be a string")

        # check for spaces in file paths
        if self.requirements_file_path is not None:
            if cu.string_contains_whitespaces(self.requirements_file_path):
                raise Exception("requirements_file_path cannot contain spaces")
        if self.training_job_file_path is not None:
            if cu.string_contains_whitespaces(self.training_job_file_path):
                raise Exception("training_job_file_path cannot contain spaces")
        if self.additional_dirs is not None:
            for d in self.additional_dirs:
                if cu.string_contains_whitespaces(d):
                    raise Exception("additional_dirs cannot contain spaces")
        if self.additional_files is not None:
            for f in self.additional_files:
                if cu.string_contains_whitespaces(f):
                    raise Exception("additional_files cannot contain spaces")

        # check that the file exists
        if self.requirements_file_path is not None:
            if not os.path.exists(self.requirements_file_path):
                raise Exception("requirements_file_path does not exist")
        if self.training_job_file_path is not None:
            if not os.path.exists(self.training_job_file_path):
                raise Exception("training_job_file_path does not exist")
        return

    def get_job(self):
        return cu.parse_hise_response(
            requests.get(self.__url, headers=get_bearer_token_header()))

    def list_all_jobs(self):
        return cu.parse_hise_response(
            requests.get(self.__url, headers=get_bearer_token_header()))

    def convert_training_job_file_to_ray(self):
        # first check if the file is a notebook or a script
        if self.training_job_file_path.endswith('.ipynb'):
            # if it's a notebook, convert it to script
            python_script_to_convert = '{}/{}'.format(
                self.work_dir, CONFIG['TEMP_FILES']['NBCONVERT_TMP_FILE'])
            cu.convert_notebook_to_python(self.training_job_file_path,
                                          python_script_to_convert)
        elif self.training_job_file_path.endswith('.py'):
            # get the script file name
            python_script_to_convert = self.training_job_file_path
        else:
            raise Exception(
                "training_job_file_path must be a .ipynb or .py file")

        # transform script to conform to Ray
        converted_script = '{}/{}'.format(
            self.work_dir, CONFIG['TEMP_FILES']['JOB_ENTRYPOINT_FILE'])
        rt.transform_to_ray(python_script_to_convert,
                            converted_script,
                            num_gpus=self.worker_gpu_count
                            if self.worker_count > 0 else self.head_gpu_count,
                            num_cpus=self.worker_cpu_count
                            if self.worker_count > 0 else self.head_cpu_count)

        # get list of ray remote targets
        ray_remote_targets = rt.get_ray_remote_targets(converted_script)
        target_names = [f[0] for f in ray_remote_targets]

        while True:
            # Prompt user for methods to remove decorators from
            rm_target = cu.prompt_from_options(
                "The following methods currently use Ray decorators: {}. "
                "Please select the methods from which you want to remove the Ray decorators"
                .format(target_names), target_names + ["None"])

            if not rm_target or rm_target == "None":
                # Exit loop if user chose no method
                break

            # Remove ray decorators from the selected targets
            rt.remove_ray_remote_decorator(converted_script, rm_target,
                                           converted_script)

        # prompt user on transformation, asking if they want to edit ray decorators
        # if the user selected targets, edit the ray decorators of those targets
        ray_remote_targets = rt.get_ray_remote_targets(converted_script)
        target_names = [f[0] for f in ray_remote_targets]
        while True:
            edit_target = cu.prompt_from_options(
                "The following methods currently use Ray decorators: {}. "
                "Please select the methods whose Ray decorator parameters you want to edit"
                .format(target_names), target_names + ["None"])

            if not edit_target or edit_target == "None":
                # Exit loop if user chose no method
                break

            # Prompt param values for the ray decorators
            edit_resp = rt.prompt_decorator_changes("")

            if edit_resp and len(edit_resp) > 0:
                rt.modify_ray_remote_decorator(converted_script, edit_target,
                                               ast.literal_eval(edit_resp),
                                               converted_script)
        return

    def copy_scripts_and_dirs_to_temp(self):
        # define master list of directories and additional files
        app_files = self.additional_files + self.additional_dirs

        # copy each path (file or directory) to the temp directory, preserving the relative path to training_job_file_path
        for f in app_files:
            # check if the path is a directory or a file
            if os.path.isdir(f):
                # check if the directory already exists, and remove it if so
                if os.path.exists('{}/{}'.format(self.work_dir,
                                                 os.path.basename(f))):
                    shutil.rmtree('{}/{}'.format(self.work_dir,
                                                 os.path.basename(f)))
                # copy the directory to the temp directory
                shutil.copytree(
                    f, '{}/{}'.format(self.work_dir, os.path.basename(f)))
            elif os.path.isfile(f):
                # copy the file to the temp directory
                shutil.copy(f, '{}/{}'.format(self.work_dir,
                                              os.path.basename(f)))
            else:
                raise Exception(
                    "additional_files must be a list of files or directories")
        return

    def create_training_job_image(self):
        with tarfile.open(self.artifacts_path, 'w:gz') as tar:
            tar.add(self.work_dir, arcname='artifacts')
        return

    def create_env_yaml(self):
        conda_export_dest = do_conda_export(self.work_dir)
        # remove hisepy from exported yaml file, if it exists
        process = subprocess.run(
            "sed -i '/hisepy==*/d' {}".format(conda_export_dest),
            shell=True,
            capture_output=True)
        if process.returncode != 0:
            raise SystemError(
                'Unable to remove hisepy from exported conda env: {}'.format(
                    conda_export_dest))

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
                    wd=self.work_dir), '{}'.format(self.work_dir)
            ],
                           check=True,
                           capture_output=True)
            subprocess.run([
                'pip-compile', '--no-annotate', '--no-header', '--quiet',
                '--strip-extras',
                '{wd}/requirements.in'.format(wd=self.work_dir)
            ],
                           check=True)
        else:
            subprocess.run([
                'pip-compile', '--no-annotate', '--no-header', '--quiet',
                '--strip-extras', '--output-file={wd}/requirements.txt'.format(
                    wd=self.work_dir), self.requirements_file_path
            ],
                           check=True)

    def submit_ray_workflow(self):
        ray_args = {
            'accountGuid': HiseUser().current_account_guid,
            'projectGuid': IDEInstance().destinationProjectGuid,
            'fileSetId': self.file_set_id,
            'instanceId': ide_instance_guid(),
            'title': self.title,
            'description': self.description,
            'tags': self.tags,
            'outputPvcSize': self.output_file_size,
            'jobRequest': {
                'headConfig': {
                    "cpus": self.head_cpu_count,
                    "gpus": self.head_gpu_count,
                    "memory": "{}G".format(str(self.head_memory_size))
                },
                'workerConfig': {
                    'replicas': self.worker_count,
                    'cpus': self.worker_cpu_count,
                    'gpus': self.worker_gpu_count,
                    'memory': "{}G".format(str(self.worker_memory_size))
                }
            },
            "harvestArtifactsRequest": {
                "artifactsFileName":
                self.artifacts_path,
                "condaEnvironmentName":
                "{}/{}".format(CONFIG["STORES"]["ENV_STORE"],
                               get_ide_env_name()),
                "packageManager":
                self.package_manager,
            }
        }
        if self.image_id is not None:
            ray_args['imageId'] = self.image_id
        return cu.parse_hise_response(
            requests.post(self.__ray_workflow_url,
                          json=ray_args,
                          headers=get_bearer_token_header()))

    def submit_beaker_workflow(self):
        beaker_args = {
            'accountGuid': HiseUser().current_account_guid,
            'projectGuid': IDEInstance().destinationProjectGuid,
            'fileSetId': self.file_set_id,
            'instanceId': ide_instance_guid(),
            'title': self.title,
            'description': self.description,
            'tags': self.tags,
            'outputPvcSize': self.output_file_size,
            'jobRequest': {
                'headConfig': {
                    "cpus": self.head_cpu_count,
                    "gpu": self.head_gpu_count,
                    "memory": "{}G".format(str(self.head_memory_size))
                },
                'workerConfig': {
                    'replicas': self.worker_count,
                    'cpus': self.worker_cpu_count,
                    'gpu': self.worker_gpu_count,
                    'memory': "{}G".format(str(self.worker_memory_size))
                }
            },
            "harvestArtifactsRequest": {
                "artifactsFileName":
                self.artifacts_path,
                "condaEnvironmentName":
                "{}/{}".format(CONFIG["STORES"]["ENV_STORE"],
                               get_ide_env_name()),
                "packageManager":
                self.package_manager,
            }
        }
        if self.image_id is not None:
            beaker_args['imageId'] = self.image_id
        return cu.parse_hise_response(
            requests.post(self.__beaker_workflow_url,
                          json=beaker_args,
                          headers=get_bearer_token_header()))

    def review_training_job(self):
        review_args = {
            'notes': self.review_notes,
            'accountGuid': HiseUser().current_account_guid,
            'projectGuid': IDEInstance().destinationProjectGuid,
            'approve': self.approve,
            'jobID': self.job_id,
            'studySpaceGuid': self.study_space_id
        }
        return cu.parse_hise_response(
            requests.post(self.__review_job_url,
                          json=review_args,
                          headers=get_bearer_token_header()))


def validate_review_run_params(study_space_id: str, job_id: str, image_id: str,
                               approve: bool, review_notes: str):
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
