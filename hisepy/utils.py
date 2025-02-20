'''
useful utility methods for HISE IDE users 
'''

import os 
import time 
from resource import  RLIMIT_AS, getrlimit, setrlimit 
import hisepy.common_utils as cu
from hisepy.instances import IDEInstance
import shutil
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
