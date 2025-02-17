'''
useful utility methods for HISE IDE users 
'''

import os 
import time 
from resource import  RLIMIT_AS, getrlimit, setrlimit 
import psutil

def set_memory_limit(max_size_gb : int): 
    ''' 
    Caps memory for a kernel/process. Call this method at the top of your notebook or script.
    If the current kernel reaches the limit, an error message will be raised, preventing OOM scenarios.
    
    Parameters: 
        max_size (int) : memory limit (in GB) for a kernel/process.
    '''
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