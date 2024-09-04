import requests
import os
import json

import hisepy.common_utils as cu
from hisepy.auth import get_from_metadata_server, get_bearer_token_header
from hisepy.upload import valid_upload_stores, project_store, permanent_store
from hisepy.reader import hise_url
from hisepy.abstraction import get_projects, project_shortname_to_guid

_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))
DEFAULT_STORE_KEY = "default_store"
IDE_DEFAULT_TAG = "IDE_DEFAULT"


class HiseUser:

    def __init__(self):
        user_url = hise_url("amds", "user_path")
        user_resp = cu.hise_get(user_url)
        for key, value in user_resp.items():
            setattr(self, key, value)
        if self.current_account_guid != instance_account_guid():
            raise Exception(
                "User's current account %s does not match this IDE's account. You must change your current account to use this IDE."
                % self.current_account_name)


class IDEInstance:

    def __init__(self):
        self.__url = hise_url("tracer", "ide_instance",
                              instance_account_guid())
        ide = cu.hise_get(self.__url)
        for key, value in ide.items():
            setattr(self, key, value)

    def __update(self, data):
        data["id"] = self.id
        return requests.request("PUT",
                                self.__url,
                                data=json.dumps(data),
                                headers=get_bearer_token_header())

    def __tags(self):
        rd = {}
        if type(self.tags) is list:
            for t in self.tags:
                if t.startswith(IDE_DEFAULT_TAG):
                    key, value = t.split(":")[1].split(",")
                    rd[key] = value
        return rd

    def __set_tag(self, key: str, val: str):
        if len(key) == 0:
            raise ValueError("Tag key was empty")
        for f in [key, val]:
            for b in [":", ","]:
                if b in f:
                    raise ValueError("Cannot use %s in tag %s" % (b, f))

        new_tags = []
        for t in self.tags:
            if t.startswith("%s:%s" % (IDE_DEFAULT_TAG, key)):
                continue
            new_tags.append(t)
        new_tags.append("%s:%s,%s" % (IDE_DEFAULT_TAG, key, val))
        self.__update({"tags": new_tags})
        self.tags = new_tags

    def get_default_project(self):
        for p in get_projects(False):
            if self.destinationProjectGuid == p["guid"]:
                return p["short_name"]
        return None

    def set_default_project(self, projectShortName: str):
        g = project_shortname_to_guid(projectShortName)
        r = self.__update({"destinationProjectGuid": g})
        self.destinationProjectGuid = g
        return r

    def get_default_store(self):
        t = self.__tags()
        if DEFAULT_STORE_KEY in t:
            return t[DEFAULT_STORE_KEY]
        return project_store

    def set_default_store(self, store: str):
        if store not in valid_upload_stores:
            raise ValueError("Value for store must be in %s" %
                             (", ".join(valid_upload_stores)))
        self.__set_tag(DEFAULT_STORE_KEY, store)


def instance_account_guid():
    iguid = os.getenv("IDE_INSTANCE_GUID")
    if iguid is None:
        raise Exception(
            "The IDE Instance guid is not set. This IDE is misconfigured. Please contact support"
        )
    return iguid


def stop_ide():
    ''' Stops/Terminates the active instance that is calling this function. '''
    # get IDE name
    this_ide_name = get_from_metadata_server(
        CONFIG['AUTHORIZE']['INSTANCE_NAME_PATH'])
    obj = cu.parse_hise_response(
        requests.request("POST",
                         "https://{s}/{tool}/{ide}/stop".format(
                             s=get_from_metadata_server(
                                 CONFIG['AUTHORIZE']['SERVER_ID_PATH']),
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
    this_ide_name = get_from_metadata_server(
        CONFIG['AUTHORIZE']['INSTANCE_NAME_PATH'])
    obj = cu.parse_hise_response(
        requests.request("POST",
                         "https://{s}/{tool}/{ide}/suspend".format(
                             s=get_from_metadata_server(
                                 CONFIG['AUTHORIZE']['SERVER_ID_PATH']),
                             tool=CONFIG['TOOLCHAIN']['TOOLCHAIN_IDE'],
                             ide=this_ide_name),
                         headers=get_bearer_token_header()))
    if obj is None:
        raise SystemError('unable to find IDE: {}'.format(this_ide_name))
    else:
        print('{} has successfully been suspended'.format(this_ide_name))
