'''
useful utility methods for HISE IDE users 
'''

import os 
import sys
import time 
from hisepy.auth import get_bearer_token_header
from resource import  RLIMIT_AS, getrlimit, setrlimit 
import hisepy.common_utils as cu
from hisepy.instances import IDEInstance
import shutil
import requests
import subprocess
import psutil

# directory of hisepy package
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))

def set_memory_limit(max_size_gb : int): 
    ''' 
    Caps memory for a kernel/process. Call this method at the top of your notebook or script.
    If the current kernel reaches the limit, an error message will be raised, preventing OOM scenarios.
    
    Parameters: 
        max_size (int) : memory limit (in GB) for a kernel/process.
    '''
    assert max_size_gb > 0, "Memory limit must be greater than 0"
    assert type(max_size_gb) == int, "Memory limit must be an integer"
    
    maxsize = max_size_gb *  (1024 ** 3) # in GB 
    soft, hard = getrlimit(RLIMIT_AS)    
    setrlimit(RLIMIT_AS, 
              (maxsize, hard))
    print("Memory limit set to ", max_size_gb, "GB")
    return 


def get_memory_usage():
    """Gets current memory usage (in MB)."""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return mem_info.rss / (1024 ** 3) # in GB 


def conda_env_builds(path_to_conda_env: str = None) -> bool:
    '''
    Returns True if conda env can build successfully, False otherwise.

    Parameters: 
        path_to_conda_env (optional) (str) : path to the conda env. 

    Returns:
        bool : True if conda env can build successfully, otherwise False.
    '''
    print("checking if conda environment can compile...")
    if path_to_conda_env is not None: 
        assert type(path_to_conda_env) == str, "Path to conda env must be a string"
        assert os.path.exists(path_to_conda_env), "Path to conda env does not exist"

    # use default conda env if none is provided
    if path_to_conda_env is None:
        modality_name = IDEInstance().environment['condaEnvName']
        path_to_conda_env = os.path.join(CONFIG['STORES']['ENV_STORE'], modality_name)
        
    # export conda env to temp directory 
    conda_export_dest = os.path.join(CONFIG['STORES']['TEMP_STORE'], 'temp_env.yml') 
    process = subprocess.run("conda env export -p {src} > {dst}".format(src=path_to_conda_env, dst=conda_export_dest),
                                 shell=True, capture_output=True)
    if process.returncode != 0:
        raise SystemError('Unable to export conda env: {}'.format(path_to_conda_env))
    
    # remove hisepy from exported yaml file, if it exists 
    process = subprocess.run("sed -i '/hisepy==*/d' {}".format(conda_export_dest),
                                 shell=True, capture_output=True)
    if process.returncode != 0:
        raise SystemError('Unable to remove hisepy from exported conda env: {}'.format(conda_export_dest))
    
    # attempt to build the env
    tmp_env_path = os.path.join(CONFIG['STORES']['TEMP_STORE'], 'tmp_env')
    process = subprocess.run('conda env create -f {dst} -p {env_dst}'.format(dst=conda_export_dest, env_dst=tmp_env_path),
                                 shell=True, capture_output=True)
    if process.returncode != 0:
        return False

    # clean up everything that was done 
    # delete exported yaml file 
    os.remove(conda_export_dest)

    # delete tmp env directory
    shutil.rmtree(tmp_env_path)

    return True 

def save_conda_environment(): 
    '''
    '''
    # grab current active Conda environment 
    active_conda_env_path = sys.prefix
    conda_env_name = os.path.basename(active_conda_env_path)

    # prompt on user's active conda env 
    cu.prompt_user(msg="You are attempting to save your current active Conda environment: {}. Proceed? (y/n)".format(active_conda_env_path))
    
     # export conda env to temp directory
    conda_export_dest = os.path.join(CONFIG['STORES']['TEMP_STORE'], '{}_env.yml'.format(conda_env_name))
    process = subprocess.run("conda env export -p {src} > {dst}".format(src=active_conda_env_path, dst=conda_export_dest))
    if process.returncode != 0:
        raise SystemError('Unable to export conda env: {}'.format(active_conda_env_path))
        return
    
    # attempt to build conda env 
    # TODO: do we need to do this if tracer/CondaPack is already doing this?
    if not conda_env_builds(active_conda_env_path):
        raise SystemError('Unable to build conda env: {}'.format(active_conda_env_path))
        return 
    
    # save Conda env to Tracer 
    url = CONFIG['Tracer']['CONDA_PACK'] 
    #resp = cu.parse_hise_response(requests.post(url, headers=get_bearer_token_header, files={'file': open(conda_export_dest, 'rb')}))


    # clean up created conda env 
    os.remove(conda_export_dest)
    #print(resp)
    return 