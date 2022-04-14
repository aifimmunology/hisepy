import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid

import plotly.graph_objects as go
import requests

import hisepy.common_utils as cu
from hisepy.auth import get_from_metadata_server, get_bearer_token_header, instance_name_path
from hisepy.reader import parse_hise_response, hise_url
from hisepy.scheduler import current_notebook

dataframe_file_type = "Visualization-dataframe"
freezer_ignore_endpoints = {"shutdown": None}


def get_study_spaces():
    return parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "study_space_path"),
                         headers=get_bearer_token_header()))


def get_files_for_query(query_id):
    resp = parse_hise_response(
        requests.post(hise_url("hydration", "query_search_path", query_id),
                      headers=get_bearer_token_header()))
    return list(map(lambda x: x['file']['id'], resp))


def get_trace(trace_id):
    trace = parse_hise_response(
        requests.request("GET",
                         hise_url("tracer", "trace_path", trace_id),
                         headers=get_bearer_token_header()))
    if len(trace) == 0:
        raise Exception("Trace id %s is invalid" % trace_id)
    return trace[0]


def default_study_space_id(must=True):
    return default_study_space(must)["id"]


def default_study_space(must=True):
    sspaces = get_study_spaces()
    if len(sspaces) == 0:
        if not must:
            return None
        raise ValueError(
            "User belongs to no study spaces! Cannot upload to HISE!")
    if len(sspaces) > 1:
        if not must:
            return None
        for s in sspaces:
            print("%s: %s" % (s["id"], s["name"]))
        raise ValueError(
            "User belongs to multiple study spaces. Please specify with the study_space_id parameter"
        )
    return sspaces[0]


def upload_files(files: list,
                 study_space_id: str = None,
                 title: str = None,
                 input_file_ids=None,
                 input_sample_ids=None,
                 file_types=None,
                 do_prompt: bool = True):

    if input_file_ids is None:
        input_file_ids = []
    if input_sample_ids is None:
        input_sample_ids = []
    if file_types is None:
        file_types = []

    def _user_prompt_upload(prompt_files: list):
        print(
            'you are trying to upload file_ids... {}. Do you truly want to proceed?'
            .format(prompt_files))
        user_input = input('(y/n)')
        while user_input.lower() not in ['y', 'n']:
            print('please enter either "n" for no, or "y" for yes.')
            user_input = input('(y/n)')
        if user_input.lower() == 'y':
            return True
        elif user_input.lower() == 'n':
            return False

    if type(files) is not list or len(files) == 0:
        raise ValueError("No files specified for upload")

    trace_id = None
    study_space_id = validate_upload_data(study_space_id, title,
                                          input_file_ids)
    uploaded = []
    for i, f in enumerate(files):
        if not os.path.exists(f):
            raise ValueError("%s is not a valid file." % f)

        file_dict = {
            'file': (f, open(f, 'rb'), 'application/json', {
                'Expires': '0'
            })
        }
        file_type = cu.get_filetype(f)
        if type(file_types) is list and len(file_types) > i:
            file_type = file_types[i]
        if trace_id is not None:
            qargs = {"traceId": trace_id, "fileType": file_type}
        else:
            qargs = {
                "studySpaceId": study_space_id,
                "title": title,
                "fileType": file_type,
                "saveIDE": True,
                "instanceId": get_from_metadata_server(instance_name_path),
                "inputFileIds": input_file_ids,
                "sampleIds": input_sample_ids,
                "notebook": current_notebook()
            }

        url = hise_url("toolchain", "upload_file_path", args=qargs)
        headers = get_bearer_token_header()
        if not do_prompt or _user_prompt_upload(prompt_files=files):
            df_data = parse_hise_response(
                requests.post(url, headers=headers, files=file_dict))
            if "TraceId" not in df_data:
                raise SystemError("No trace found in file upload response.")
            trace_id = df_data["TraceId"]
            # don't verify with the user more than once
            do_prompt = False
            uploaded.append(df_data["FileId"])
        else:
            print('Uploading canceled.')
            break
    return {"trace_id": trace_id, "files": uploaded}


def save_visualization(pl_obj,
                       study_space_id=None,
                       title=None,
                       input_file_ids=None,
                       input_sample_ids=None):

    if input_file_ids is None:
        input_file_ids = []
    if input_sample_ids is None:
        input_sample_ids = []
    tmp_data_file = "/tmp/plotly_data.json"
    tmp_plotly_file = "/tmp/plotly.json"
    tmp_img_file = "/tmp/plotly.png"

    pl_obj.write_image(tmp_img_file)
    img_data = save_static_image(image=tmp_img_file,
                                 title=title,
                                 study_space_id=study_space_id)
    os.remove(tmp_img_file)

    exp_obj = json.loads(pl_obj.to_json())

    f = open(tmp_data_file, "w")
    f.write(json.dumps(exp_obj["data"]))
    f.close()

    up_res = upload_files(files=[tmp_data_file],
                          study_space_id=study_space_id,
                          title=title,
                          input_file_ids=input_file_ids,
                          input_sample_ids=input_sample_ids,
                          file_types=[dataframe_file_type],
                          do_prompt=False)

    args = {"traceId": up_res["trace_id"], "images": img_data["id"]}

    # now null out the data and save the plotly without it
    exp_obj["data"] = []
    f = open(tmp_plotly_file, "w")
    f.write(json.dumps(exp_obj))
    f.close()

    vis_dict = {
        'file': (tmp_plotly_file, open(tmp_plotly_file,
                                       'rb'), 'application/json', {
                                           'Expires': '0'
                                       })
    }

    url = hise_url("toolchain", "visualization_path", "json", args=args)
    parse_hise_response(
        requests.post(url, headers=get_bearer_token_header(), files=vis_dict))
    os.remove(tmp_data_file)
    os.remove(tmp_plotly_file)
    return up_res


class DashAppImg:
    """ Class representing a Dash App Object """
    dash_app_name = 'app.py'

    def __init__(self,
                 app_fpath: str,
                 list_fnames: list,
                 plty_objs: list,
                 my_study_id: str,
                 my_file_ids: list,
                 style_sheet: str,
                 work_dir: str,
                 title: str = None,
                 description: str = None,
                 my_sample_ids=None):

        if my_sample_ids is None:
            my_sample_ids = []
        if self.verify_app_path(app_fpath):
            self.app_filepath = app_fpath
        if self.verify_filenames(list_fnames):
            self.filenames = list_fnames
        self.plotly_objects = plty_objs
        self.study_space_id = my_study_id
        self.input_file_ids = my_file_ids
        self.input_sample_ids = my_sample_ids
        self.title = title
        self.description = description
        self.style_sheet = style_sheet
        self.work_dir = work_dir

    def get_app_dir(self):
        """ Sets working directory of dash app """
        return os.path.dirname(self.app_filepath)

    @staticmethod
    def verify_app_path(path):
        """ Verifies that user-submitted path is appropriate and actually exists """
        assert path.split(
            '/'
        )[-1] == 'app.py', 'filename of your dash app must be app.py. Please rename your file and try again.'
        if not os.path.exists(path):
            raise ValueError("%s is not a valid file" % path)
        return True

    def verify_filenames(self, filenames):
        """ Verifies that submitted input files are of appropriate type, and exists within the working directory

        TODO: force just a single filetype per submission
        """
        filepaths = cu.find_files(self.get_app_dir(), filenames)
        assert len(filepaths) == len(filenames
        ), 'not all files listed under filenames were found. Please make sure the files listed exist in the same' \
           ' directory as your app.py file'

        return True

    def create_req_txt(self):
        subprocess.run(
            "pip3 freeze > {wd}/requirements.txt".format(wd=self.work_dir),
            shell=True)

    def export_plotly_objs(self):
        plot_type = type(self.plotly_objects[0])
        if plot_type == str:  # NOTE: might not want this
            plotly_list = cu.find_files(self.get_app_dir(),
                                        self.plotly_objects)
            for this_plot in plotly_list:
                assert (type(this_plot) == str) and (
                    cu.get_filetype(this_plot) == 'png'
                ), "image must be a PNG if you're trying to submit snapshots of visualizations"

                # move all to tmp dir
                shutil.copy(this_plot, self.work_dir)
        else:
            # assume plotly objects are being passed through
            for plo in self.plotly_objects:
                save_visualization(plo,
                                   study_space_id=self.study_space_id,
                                   input_file_ids=self.input_file_ids,
                                   input_sample_ids=self.input_sample_ids)

    def create_dash_image(self):
        """Creates image by bundling all required objects"""
        source_dir = '{wd}'.format(wd=self.work_dir)
        with tarfile.open('{wd}/dash_app.tar.gz'.format(wd=self.work_dir),
                          "w:gz") as tar:
            tar.add(source_dir, arcname="")
        return True

    @staticmethod
    def archive_style_sheet():
        """ Requests submitted style sheet, and saves """
        # TODO: does user submit this style sheet? what if user doesn't submit one?
        resp = requests.request(
            "GET",
            "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css"
        )
        return resp.text

    def export_dash_image(self):
        """ Uploads, saves and deploys Dash app """
        upload_resp = upload_files(
            files=['{wd}/dash_app.tar.gz'.format(wd=self.work_dir)],
            study_space_id=self.study_space_id,
            title=self.title,
            input_file_ids=self.input_file_ids,
            input_sample_ids=self.input_sample_ids,
            do_prompt=False)
        upload_trace_id = upload_resp['trace_id']

        save_args = {
            "studySpaceId": self.study_space_id,
            "title": self.title,
            "instanceId": get_from_metadata_server(instance_name_path),
            "inputFileIds": self.input_file_ids,
            "sampleIds": self.input_sample_ids,
            "notebook": current_notebook(),
            "traceId": upload_trace_id
        }
        save_url = hise_url("toolchain", "save_dash_app_path", args=save_args)
        headers = get_bearer_token_header()
        # We don't technically need the save response because it's the same Trace ID,
        # but we'll go through it to help with debugging if save returns something crazy
        save_resp = parse_hise_response(
            requests.post(save_url, headers=headers))
        deploy_url = hise_url("toolchain",
                              "deploy_dash_app_path",
                              resource=save_resp['TraceId'])
        deploy_resp = parse_hise_response(
            requests.post(deploy_url, headers=headers))
        return deploy_resp


def save_dash_app(app_filepath: str,
                  filenames: list,
                  plotly_objects: list,
                  study_space_id,
                  input_file_ids: list,
                  custom_style_sheet: str,
                  title: str = None,
                  description: str = None,
                  input_sample_ids=None):
    """ Given a filepath to app.py, validate input files for the app exist, require that requirements.txt also
     exist, create static images of plotly objects, tar/zip everything together and upload the file via uploadFiles()

    Parameters:
        app_filepath : str
            filepath to app.py file
        filenames : list
            list of filenames that are used as inputs to users' dash app
        plotly_objects: list
            a list of plotly objects or filepaths to .png images users want included in their study space
        study_space_id : str
            unique identifier for study space
        input_file_ids : list
            list of unique HISE files used to generate results
        input_sample_ids : list
            list of unique samples used to generate results

    Returns:
        True if upload was successful, False if submission failed

    Examples:
        hp.save_dash_app('/Users/james.harvey/workplace/dash_test/app.py',
                                ['inputdash1.csv', 'inputdash2.csv'],
                                ['pic1.png'],
                                'f2f03ecb-5a1d-4995-8db9-56bd18a36aba',
                                ['9f6d7ab5-1c7b-4709-9455-3d8ff3fbb6c8'],
                                'custom.css',
                                'my app title',
                                'this is a description',
                                []
        )
    """
    if input_sample_ids is None:
        input_sample_ids = []
    with tempfile.TemporaryDirectory() as tmpdirname:
        # create static dash image
        dobj = DashAppImg(app_fpath=app_filepath,
                          list_fnames=filenames,
                          plty_objs=plotly_objects,
                          my_study_id=study_space_id,
                          my_file_ids=input_file_ids,
                          style_sheet=custom_style_sheet,
                          work_dir=tmpdirname,
                          title=title,
                          description=description,
                          my_sample_ids=input_sample_ids)

        # Insert UI widget code here:
        # pull out all filenames
        # determine what are input datasets vs. hero images

        # now walk down this app_dir and find those files
        fpaths_list = cu.find_files(dobj.get_app_dir(),
                                    dobj.filenames + ['app.py'])

        # move everything to a temporary dir
        for this_file in fpaths_list:
            shutil.copy(this_file, tmpdirname)

        # create .txt files that contains users' imported libraries
        dobj.create_req_txt()

        # handle images users want to show up in their study space.
        dobj.export_plotly_objs()

        # tar it up; upload; and clean up
        dobj.create_dash_image()
        resp = dobj.export_dash_image()

        # now upload the images
        print('dash image was successfully uploaded!')
        return resp


def save_static_image(image, title, study_space_id=None):
    if not os.path.exists(image):
        raise ValueError("%s is not a valid file." % image)

    img_dict = {
        'bytes': (image, open(image,
                              'rb'), "image/%s" % (cu.get_filetype(image)))
    }
    study_space_id = validate_upload_data(study_space_id, title,
                                          ["not a file"])
    args = {"studySpaceId": study_space_id, "title": title}
    return parse_hise_response(
        requests.post(hise_url("hydration", "upload_path", args=args),
                      headers=get_bearer_token_header(),
                      files=img_dict))


def validate_upload_data(study_space_id, title, input_file_ids):
    if study_space_id is None:
        study_space_id = default_study_space_id()
    if title is None:
        raise ValueError("Title cannot be empty")
    elif len(title) < 10:
        raise ValueError("Title must be at least 10 characters")
    if len(input_file_ids) == 0:
        raise ValueError("You must specify at least one input file UUID")
    return study_space_id


def load_visualization(trace_id):
    data = None
    trace = get_trace(trace_id)
    if "steps" in trace and "dataReference" in trace["steps"]:
        ref = trace["steps"]["dataReference"]
        try:
            datauuid = uuid.UUID(ref)
            if datauuid != uuid.UUID(int=0):
                data = parse_hise_response(
                    requests.request("GET",
                                     hise_url("hydration", "download_path",
                                              format(datauuid)),
                                     headers=get_bearer_token_header()))
            else:
                # dataReference was empty UUID. Ignore
                pass
        except Exception as e:
            print("Failed to load data reference %s: %s" % (ref, format(e)))

    obj = parse_hise_response(
        requests.request("GET",
                         hise_url("toolchain", "visualization_path", trace_id),
                         headers=get_bearer_token_header()))
    if data is not None:
        obj["data"] = data
    return go.Figure(obj, skip_invalid=True)
