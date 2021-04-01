import requests

metadata_server_root = "http://metadata.google.internal/computeMetadata/v1/instance"
instance_name_path = "name"
client_id_path = "attributes/iap-client-id"
identity_path = "service-accounts/default/identity"
server_id_path = "attributes/hise-server"

def get_from_metadata_server(path):
    resp = requests.request("GET",
                            "%s/%s" % (metadata_server_root, path),
                            headers = {"Metadata-Flavor": "Google"})
    if resp.status_code != 200:
        raise(SystemError("Request to %s failed with status %d. %s" %
                          (path,resp.status_code,resp.text)))
    return resp.text

def get_bearer_token_header():
    client_id = get_from_metadata_server(client_id_path)
    return {"Authorization": "Bearer %s" %
            (get_from_metadata_server("%s?format=full&audience=%s" %
                                      (identity_path, client_id)))}

