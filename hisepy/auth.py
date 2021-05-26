import requests
import os

metadata_server_root = "http://metadata.google.internal/computeMetadata/v1/instance"
instance_name_path = "name"
client_id_path = "attributes/iap-client-id"
account_guid_path = "attributes/currentAccountGuid"
identity_path = "service-accounts/default/identity"
server_id_path = "attributes/hise-server"
token_env = "TOKEN_GENERATOR"

default_metadata = {
    instance_name_path: "local-testing-instance",
    client_id_path: "938455265122-t3ovcfjsbdlrv628abnt0qpl36m23k6j.apps.googleusercontent.com",
    server_id_path: "dev.allenimmunology.org",
}

# dev primecollective
defaultLocalAccountGuid = "10f58583-1cdf-4f18-8de4-dc1ca94783e2"

def get_from_metadata_server(path):
    value = None
    try:
        resp = requests.request("GET",
                                "%s/%s" % (metadata_server_root, path),
                                headers = {"Metadata-Flavor": "Google"})
        if resp.status_code != 200:
            raise(SystemError("Request to %s failed with status %d. %s" %
                              (path,resp.status_code,resp.text)))
        value = resp.text
    except:
        if path in default_metadata:
            print("Returning default value for %s" % (path))
            value = default_metadata[path]
        else:
            raise(SystemError("No default value found for %s. Cannot continue" % path))
    return value

def get_bearer_token_header():
    client_id = get_from_metadata_server(client_id_path)
    token_gen = os.getenv(token_env)
    if token_gen is not None:
        headers = {"Authorization": "Bearer %s" % os.popen(token_gen).read().rstrip(), "InstanceAccountGuid": defaultLocalAccountGuid}
    else:
        headers = {"Authorization": "Bearer %s" % (get_from_metadata_server("%s?format=full&audience=%s" % (identity_path, client_id))),
            "InstanceAccountGuid": "%s" % (get_from_metadata_server("%s" % (account_guid_path)))}
    print("HEADERS ARE:")
    print(headers)
    return headers

