import requests
import os
import json

import hisepy.common_utils as cu
import hisepy.hise_requests as hreq
from hisepy.auth import get_bearer_token_header, hise_server, IDEInstance, ide_is_from_guest_account, guest_hise_server
from hisepy.common_utils import hise_url
from hisepy.upload_utils import valid_upload_stores, project_store, permanent_store
from hisepy.logging import with_default_logging, logger

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


@with_default_logging
def stop_ide():
    ''' Stops/Terminates the active instance that is calling this function. '''
    # get IDE name
    this_ide_name = IDEInstance().friendlyName
    url = "https://{s}/{tool}/{ide}/stop".format(
        s=guest_hise_server()
        if ide_is_from_guest_account() else hise_server(),
        tool=CONFIG['IDE_MANAGEMENT']['IDE_PATH'],
        ide=IDEInstance().id)
    obj = hreq.hise_post(url)
    if obj is None:
        raise SystemError('unable to find IDE: {}'.format(this_ide_name))
    else:
        logger.info(f'{this_ide_name} has successfully been stopped')
