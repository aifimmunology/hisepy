''' common_utils.py

Description: common methods for SDK development, but not available for end/HISE users

Methods: 

Contributors: James Harvey 
'''

# libraries 
import yaml 
import tarfile 
import os 


def read_yaml(file_path):
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

def get_filetype(this_filename): 
    '''
    '''
    if "." in this_filename:
        return this_filename.split(".")[-1]
    else:
        return "json"

def tardir(output_filename, source_dir):
    ''' Utility function that will create a tar file for an entire directory and its' children 
    '''
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))