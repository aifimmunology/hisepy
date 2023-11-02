import os

import requests

metadata_server_root = "http://metadata.google.internal/computeMetadata/v1/instance"
instance_name_path = "name"
client_id_path = "attributes/iap-client-id"
account_guid_path = "attributes/currentAccountGuid"
identity_path = "service-accounts/default/identity"
server_id_path = "attributes/hise-server"
token_env = "TOKEN_GENERATOR"

default_metadata = {
    instance_name_path: os.getenv("TEST_INSTANCE_NAME")
    or "local-testing-instance",
    client_id_path: os.getenv("AUTH_CLIENT_ID"),
    server_id_path: "dev.allenimmunology.org"
}

# dev primecollective
defaultLocalAccountGuid = "10f58583-1cdf-4f18-8de4-dc1ca94783e2"


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
            print("Returning default value for %s" % path)
            value = default_metadata[path]
        else:
            raise SystemError(
                "No default value found for %s. Cannot continue" % path)
    return value


def get_bearer_token_header():
    client_id = get_from_metadata_server(client_id_path)
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
                                         (identity_path, client_id))
        account_guid = get_from_metadata_server(account_guid_path)
        headers = {
            "Authorization": "Bearer %s" % token,
            "InstanceAccountGuid": "%s" % account_guid
        }
    return headers


# use the presence of the token gen env as a proxy for debug env
def debug():
    return os.getenv(token_env) is not None
