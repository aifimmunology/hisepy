''' config_utils.py 

Description: utility methods to interact with config file and retrieve global endpoints and variables 
Contributors: James Harvey 
'''

# libraries 
import yaml 

def read_yaml(file_path):
    with open(file_path, "r") as f:
        return yaml.safe_load(f)