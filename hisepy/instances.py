import requests
import os
import json

import hisepy.common_utils as cu
from hisepy.auth import get_bearer_token_header, hise_server, IDEInstance, hise_url, get_projects, project_shortname_to_guid
from hisepy.upload import valid_upload_stores, project_store, permanent_store

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


def stop_ide():
    ''' Stops/Terminates the active instance that is calling this function. '''
    # get IDE name
    this_ide_name = IDEInstance().friendlyName
    obj = cu.parse_hise_response(
        requests.request("POST",
                         "https://{s}/{tool}/{ide}/stop".format(
                             s=hise_server(),
                             tool=CONFIG['TOOLCHAIN']['TOOLCHAIN_IDE'],
                             ide=this_ide_name),
                         headers=get_bearer_token_header()))
    if obj is None:
        raise SystemError('unable to find IDE: {}'.format(this_ide_name))
    else:
        print('{} has successfully been stopped'.format(this_ide_name))


def suspend_ide():
    ''' Suspends the active instance that is calling this function. '''
    # get IDE name
    this_ide_name = IDEInstance().friendlyName
    obj = cu.parse_hise_response(
        requests.request("POST",
                         "https://{s}/{tool}/{ide}/suspend".format(
                             s=hise_server(),
                             tool=CONFIG['TOOLCHAIN']['TOOLCHAIN_IDE'],
                             ide=this_ide_name),
                         headers=get_bearer_token_header()))
    if obj is None:
        raise SystemError('unable to find IDE: {}'.format(this_ide_name))
    else:
        print('{} has successfully been suspended'.format(this_ide_name))
