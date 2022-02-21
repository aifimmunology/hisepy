''' common_utils.py

Description: common methods for SDK development, but not available for end/HISE users

Methods: 

Contributors: James Harvey 
'''

# libraries 
import yaml 


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