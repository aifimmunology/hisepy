import os
import requests
import json
import hisepy.common_utils as cu

metadata_server_root = "http://metadata.google.internal/computeMetadata/v1/instance"
instance_name_path = "name"
client_id_path = "attributes/iap-client-id"
account_guid_path = "attributes/currentAccountGuid"
identity_path = "service-accounts/default/identity"
server_id_path = "attributes/hise-server"
token_env = "TOKEN_GENERATOR"
sdk_debug = "HISE_SDK_DEBUG"

default_metadata = {
    instance_name_path: os.getenv("TEST_INSTANCE_NAME")
    or "local-testing-instance",
    client_id_path: os.getenv("AUTH_CLIENT_ID"),
}
permanent_store = "permanent"
project_store = "project"
valid_upload_stores = [permanent_store, project_store]
defaultLocalAccountGuid = "10f58583-1cdf-4f18-8de4-dc1ca94783e2"
DEFAULT_STORE_KEY = "default_store"
IDE_DEFAULT_TAG = "IDE_DEFAULT"


class HiseUser:

    def __init__(self):
        user_url = cu.hise_url("amds", "user_path")
        user_resp = cu.hise_get(user_url)
        for key, value in user_resp.items():
            setattr(self, key, value)


class IDEInstance:

    def __init__(self):
        self.__url = cu.hise_url("tracer", "ide_instance", ide_instance_guid())
        try:
            ide = cu.hise_get(self.__url)
            for key, value in ide.items():
                setattr(self, key, value)
        except:
            raise Exception(
                "Your current account (%s) does not match this IDE. You must change your current account in order to use it."
                % HiseUser().current_account_name)

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
        for p in cu.get_projects(False):
            if self.destinationProjectGuid == p["guid"]:
                return p["short_name"]
        return None

    def set_default_project(self, projectShortName: str):
        g = cu.project_shortname_to_guid(projectShortName)
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


def ide_instance_guid():
    iguid = os.getenv("IDE_INSTANCE_GUID")
    if iguid is None:
        raise Exception(
            "The IDE Instance guid is not set. This IDE is misconfigured. Please contact support"
        )
    return iguid


def instance_account_guid():
    iguid = os.getenv("INSTANCE_ACCOUNT_GUID")
    if iguid is None:
        raise Exception(
            "The Account GUID is not set. This IDE is misconfigured. Please contact support"
        )
    return iguid


def hise_server():
    return os.getenv("HISE_SERVER") or "dev.allenimmunology.org"


def get_from_metadata_server(path):
    try:
        resp = requests.request("GET",
                                "%s/%s" % (metadata_server_root, path),
                                headers={"Metadata-Flavor": "Google"})
        if resp.status_code != 200:
            raise SystemError("Request to %s failed with status %d. %s" %
                              (path, resp.status_code, resp.text))
        value = resp.text
    except:
        if path in default_metadata:
            value = default_metadata[path]
        else:
            raise SystemError(
                "No default value found for %s. Cannot continue" % path)
    return value


def get_bearer_token_header():
    audience = get_audience() or get_from_metadata_server(client_id_path)
    token_gen = os.getenv(token_env)
    if token_gen is not None:
        token = os.popen(token_gen).read().rstrip()
        headers = {
            "InstanceAccountGuid": defaultLocalAccountGuid,
            # Rather than look at whether we're running locally, just set both auth headers
            # for dev:
            "Authorization": "Bearer %s" % token,
            # for local instances:
            "hise_invoker_token": "%s" % token
        }
    else:
        token = get_from_metadata_server("%s?format=full&audience=%s" %
                                         (identity_path, audience))
        headers = {
            "Authorization": "Bearer %s" % token,
            "InstanceAccountGuid": "%s" % instance_account_guid()
        }
    return headers


def get_audience():
    afile = cu.get_from_config('stores', 'audience_file')
    if os.path.exists(afile):
        with open(afile, 'r') as f:
            return f.readline().strip()
    return None


# use the presence of the token gen env as a proxy for debug env
def debug():
    return os.getenv(sdk_debug) is not None
