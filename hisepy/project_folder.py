''' project_folder.py 

Description: 

Contributors: James Harvey  
'''

# libraries 
import os
import pandas as pd 
import requests 
import json
import hisepy.common_utils as cu 
import urllib.request
import urllib.parse
from google.cloud import storage
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, server_id_path


# load config for global variables and endpoints 
CONFIG = cu.read_yaml('{}/hisepy/config.yaml'.format(os.getcwd()))


def list_project_folders():
    ''' 
    Lists all project folders a user has access to 

        Returns: 
            project_list : list 
                list of project short-names 
    '''
    url = 'https://{ser}/{hy}/{pfe}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'])
    resp = requests.request("GET",
                            url,                            
                            headers = get_bearer_token_header())
    if resp.status_code != 200: 
        raise(SystemError("Request to {} failed with status {}".format(url, resp.status_code)))
    project_list = json.loads(resp.text)['folders']
    
    if len(project_list) == 0: 
        ValueError("user doesn't have access to any project Folders. Please contact dev support if this shouldn't be the case.")
    return project_list


def list_files_in_project_folder(folder_name): 
    ''' 
    Returns information about what files are present in a given project folder 
        
        Parameters: 
            folder_name : str
                name of project folder 
        Returns: 
            df : pd.DataFrane
                data.frame containing fileIds and fileNames 
    '''
    folder = {'folders' : [folder_name]}
    url = 'https://{ser}/{hy}/{pfe}/{f}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'],
        f='files')
    resp = requests.request("POST", 
                            url,
                            data=json.dumps(folder),
                            headers=get_bearer_token_header())
    if resp.status_code != 200: 
        raise(SystemError("Request to {} failed with status {}".format(url, resp.status_code)))
    obj = json.loads(resp.text)[0] # only allow users to submit 1 folder_name at a time, so we always index the first entry 

    df = pd.DataFrame(obj['files'])
    df['folder_name'] = folder_name
    if len(df) == 0: 
        ValueError("No files were found in project folder... {}".format(folder_name))
    return df 


def download_from_project_folder(folder_name, file_name): 
    '''
    Downloads a given file onto a users' IDE. The filepath pattern is as follows: 
    '~/folder_name/file_name'. 
        NOTE: ~ denotes your home directory 

        Parameters:
            folder_name : str
                name of project folder 
            file_name : str 
                name of file that you see under 'name' when utilizing list_files_in_project_folder 

        Returns: bool
            True if download was successful 
    '''
    # create directory 
    try: 
        os.mkdir('{}/{}'.format(os.getcwd(), folder_name)) 
    except: # directory already exists, but we don't want to error out 
        pass

    # create url download 
    url = 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'],
        fol=folder_name,
        fil='files',
        fn=file_name)
    resp= requests.request("GET",
                            url,
                            headers=get_bearer_token_header())
    if resp.status_code != 200: 
        raise(SystemError("Request to {} failed with status {}".format(url, resp.status_code)))
    
    # remove time-stamp info from file_name which is assumed to be the first string before the first '/' character
    truncate_file_name = file_name.split('/', maxsplit=1)[1]
    with open('{}/{}/{}'.format(os.getcwd(), folder_name, truncate_file_name), 'wb') as f:
        f.write(resp.content)
    
    return True 


def upload_to_project_folder(watchfolder_bucket_url, file_path): 
    '''
    Uploads file via watchfolder_bucket_url so that it becomes available in the linked Project Folder 

        Parameters: 
            watchfolder_bucket_url : str 
                url link to dedicated watch folder for the Project Folder of interest 
            file_path : str 
                path to your file 

        Returns : bool
            True if file was downloaded 
    '''
    
    # ensure users' file actually exists 
    if ~os.path.exists(file_path): 
        raise(FileExistsError('submitted path {}, cannot be found'.format(file_path)))

    client = storage.Client()
    bucket = client.bucket(watchfolder_bucket_url)
    blob = bucket.blob(file_path)
    blob.upload_from_filename(file_path)
    return True


def archive_file_in_project_folder(folder_name, file_name):
    '''
    Mark a file in a project folder to be archived. This will not actually delete the file, 
    but will remove it from being seen or downloaded when utilizing any other project folder methods.

    NOTE: you can unarchive a file by using undo_archive_in_project_folder() method 

        Parameters: 
            folder_name : str
                name of project folder  
            file_name : str
                name of project folder 
        Returns: 
            boolean : True if function call was a success
    '''

    archive_tag = CONFIG['PROJECT_FOLDER']['ARCHIVE_TAG']
    tag_field = CONFIG['PROJECT_FOLDER']['TAG_FIELD_NAME']
    json_tag = {tag_field: archive_tag}
    url = 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'],
        fol=folder_name,
        fil='files',
        fn=file_name)
    resp = requests.request("PUT",
                            url,
                            data=json.dumps(json_tag),
                            headers=get_bearer_token_header())
    if resp.status_code != 200: 
        raise(SystemError('Request to {} failed with status {}'.format(url, resp.status_code)))
    return True


def undo_archive_in_project_folder(folder_name, file_name): 
    '''
    Unarchives files. any files that were tagged to be archived will now be visible through list_files_in_project_folder()

        Parameters: 
            folder_name : str
                name of project folder 
            file_name : str 
                name of project folder that you want unarchived and visible
        Returns: 
            boolean : True if function call was a success 

    '''

    available_tag = CONFIG['PROJECT_FOLDER']['AVAILABLE_TAG']
    tag_field = CONFIG['PROJECT_FOLDER']['TAG_FIELD_NAME']
    json_tag = {tag_field : available_tag}
    url = 'https://{ser}/{hy}/{pfe}/{fol}/{fil}/{fn}'.format(
        ser=get_from_metadata_server(server_id_path),
        hy=CONFIG['HYDRATION']['HYDRATION_NAME'],
        pfe=CONFIG['PROJECT_FOLDER']['PROJECT_FOLDER_ENDPOINT'],
        fol=folder_name,
        fil='files',
        fn=file_name)
    resp = requests.request("PUT", 
                            url,
                            data=json.dumps(json_tag), 
                            headers=get_bearer_token_header())
    if resp.status_code != 200: 
        raise(SystemError("Request to {} failed with status {}".format(url, resp.status_code)))
    return True 