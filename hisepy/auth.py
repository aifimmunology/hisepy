import os
import requests
import json
import urllib
import pandas as pd
import hisepy.common_utils as cu
from hisepy.common_utils import valid_upload_stores, project_store, token_env

metadata_server_root = "http://metadata.google.internal/computeMetadata/v1/instance"
instance_name_path = "name"
client_id_path = "attributes/iap-client-id"
account_guid_path = "attributes/currentAccountGuid"
identity_path = "service-accounts/default/identity"
server_id_path = "attributes/hise-server"

default_metadata = {
    instance_name_path: os.getenv("TEST_INSTANCE_NAME")
    or "local-testing-instance",
    client_id_path: os.getenv("AUTH_CLIENT_ID"),
}

defaultLocalAccountGuid = "10f58583-1cdf-4f18-8de4-dc1ca94783e2"
DEFAULT_STORE_KEY = "default_store"
IDE_DEFAULT_TAG = "IDE_DEFAULT"

# directory of hisepy package
_here = os.path.abspath(os.path.dirname(__file__))
CONFIG = cu.read_yaml('{}/config.yaml'.format(_here))


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


def hise_get(url: str):
    return cu.parse_hise_response(
        requests.get(url, headers=get_bearer_token_header()))


def hise_server():
    return os.getenv("HISE_SERVER") or "dev.allenimmunology.org"


def hise_url(service: str,
             config_path: str,
             resource: str = None,
             args: dict = None):
    if service.upper() not in CONFIG:
        raise ValueError("%s is not a known HISE service" % service)
    if config_path.upper() not in CONFIG[service.upper()]:
        raise ValueError("%s is not a known path in %s service" %
                         (config_path, service))

    server = get_server(service)
    protocol = "http" if "localhost" in server else "https"
    url = "%s://%s/%s" % (protocol, server,
                          CONFIG[service.upper()][config_path.upper()])
    if resource is not None:
        if type(resource) is not str:
            raise ValueError("resource argument was a %s, not a string" %
                             (type(resource)))
        url += "/%s" % resource

    if args is not None:
        if type(args) is not dict:
            raise ValueError("query string argument was a %s, not a dict" %
                             (type(args)))
        url += "?%s" % (urllib.parse.urlencode(args, doseq=True))
    return url


def get_server(service):
    test_hydration_server = os.getenv("TEST_HYDRATION_SERVER")
    test_toolchain_server = os.getenv("TEST_TOOLCHAIN_SERVER")
    test_tracer_server = os.getenv("TEST_TRACER_SERVER")
    test_ledger_server = os.getenv("TEST_LEDGER_SERVER")
    if service == "hydration" and test_hydration_server is not None:
        return test_hydration_server
    elif service == "toolchain" and test_toolchain_server is not None:
        return test_toolchain_server
    elif service == "tracer" and test_tracer_server is not None:
        return test_tracer_server
    elif service == "ledger" and test_ledger_server is not None:
        return test_ledger_server
    else:
        return hise_server()


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


def project_guid_to_shortname(proj_guid):
    """
    Takes a string, looks up if there's a Project guid with the passed in value. If there is, return the corresponding short name.
    Otherwise, let the user know the Project doesn't exist.

    Parameters: 
        proj_guid (str) : the guid of a HISE Project
    """
    proj_df = get_projects()

    # chosen project must be in there, right?
    if proj_guid not in proj_df['guid'].values:
        raise ValueError("%s is not a valid project guid." % proj_guid)
    else:
        this_proj = proj_df.loc[proj_df['guid'].eq(proj_guid), ].reset_index(
            drop=True)

    return this_proj.loc[0, 'short_name']


def project_shortname_to_guid(proj_name):
    """
    Takes a string, looks up if there's a Project shortname with the passed in value. If there is, return the corresponding 
    guid. Otherwise, let the user know the Project doesn't exist.

    Parameters: 
        proj_name (str) : the short-name of a HISE Project
    """
    proj_df = get_projects()

    # chosen project must be in there, right?
    if proj_name not in proj_df['short_name'].values:
        raise ValueError(
            "%s is not a valid project name. The following is a list of valid projects: %s"
            % (proj_name, proj_df['short_name'].values))
    else:
        this_proj = proj_df.loc[
            proj_df['short_name'].eq(proj_name), ].reset_index(drop=True)

    # error if collisions exist
    if len(this_proj) > 1:
        raise SystemError(
            "Looks like there multiple Projects named %s. Please contact the software team."
            % (proj_name))
    else:
        proj_guid = this_proj.loc[0, 'guid']
        return proj_guid


def get_projects(to_df: bool = True):
    """
    Returns information on all projects in the current account

    Parameters: 
        to_df (bool): reshape to tabular, if True
    """
    keep_cols = ['guid', 'short_name', 'name']
    resp = cu.parse_hise_response(
        requests.get(hise_url("amds", "project_path"),
                     headers=get_bearer_token_header()))

    # reshape to tabular format and concatenate each entry
    if to_df:
        proj_df = pd.DataFrame()
        for p in resp:
            proj_df = pd.concat([proj_df, pd.json_normalize(p)[keep_cols]])
        return proj_df

    return resp
