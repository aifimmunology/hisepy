import pandas as pd
import re
import requests
import tarfile
import tempfile
from IPython.display import HTML, display
from enum import Enum
from operator import xor
from os import chmod, path, walk
from os.path import abspath, dirname, isdir, isfile
from typing import Any, Tuple

import hisepy.upload_utils as hpu
from hisepy.auth import get_bearer_token_header
from hisepy.common_utils import hise_url
from hisepy.logging import logger


def create_visualization_tarball(CONFIG: Any,
                                 all_files: list[str],
                                 is_abstraction: bool = False) -> str:
    tmpdirname = tempfile.mkdtemp(dir=CONFIG['STORES']['TEMP_STORE'])
    chmod(tmpdirname, 0o777)
    logger.info("Created temporary directory for %s App build: %s",
                'Abstraction' if is_abstraction else 'Visualization',
                tmpdirname)

    hpu.create_temp_directory_files(all_files, tmpdirname)

    tarfile_basename = ('abstraction'
                        if is_abstraction else 'viz') + '_app.tar.gz'
    tarfile_path = path.join(tmpdirname, tarfile_basename)
    logger.debug('Creating tarball: %s', tarfile_path)
    with tarfile.open(tarfile_path, 'w:gz') as tar:
        tar.add(tmpdirname,
                arcname='',
                filter=lambda ti: None if ti.name == tarfile_basename else ti)
    return tarfile_path


def enumerate_all_files(files: list[str], dirs: list[str]) -> set[str]:
    all_files = set([abspath(f) for f in files])
    for dir in [abspath(d) for d in dirs]:
        for (dirpath, _, filenames) in walk(dir):
            all_files.update(
                [path.join(dirpath, filename) for filename in filenames])
    return all_files


def get_build_template(build_template_name: str,
                       build_template_major_version: int,
                       build_template_minor_version: int) -> dict[str, Any]:
    templates = get_build_templates(build_template_name,
                                    build_template_major_version,
                                    build_template_minor_version)
    if len(templates) == 1:
        return templates[0]
    elif len(templates) == 0:
        raise RuntimeError(
            'No visualization templates found with name %s version %s.%s' % (
                build_template_name,
                '*' if build_template_major_version < 0 else
                build_template_major_version,
                '*' if build_template_minor_version < 0 else
                build_template_minor_version,
            ))

    template_df = pd.DataFrame({
        'Template Framework': [vbt['name'] for vbt in templates],
        'Version': [vbt['githubLink'] for vbt in templates],
        'Description': [vbt['description'] for vbt in templates]
    })

    # Define the function to create a clickable HTML link in a DataFrame
    def make_clickable(val):
        # target="_blank" ensures the link opens in a new window/tab
        # The last element of the Github URL is the version of the Visualization Build Template
        return '<a target="_blank" href="%s">%s</a>' % (val,
                                                        val.split('/')[-1])

    styled_df = template_df.style.format(formatter={'Version': make_clickable})
    print('The following Visualization Build Templates are available:')
    display(HTML(styled_df.to_html()))

    prompt = 'Enter the index of your desired template. Possible values range from 0 to %d' % (
        len(templates) - 1)
    user_choice = -1
    while not 0 <= user_choice < len(templates):
        try:
            user_choice = int(input(prompt))
        except ValueError:
            user_choice = -1
    return templates[user_choice]


def get_build_template_and_params(
    build_template_name: str, build_template_major_version: int,
    build_template_minor_version: int, all_files: set[str],
    build_template_parameters: dict[str,
                                    str], infer_build_template_arguments: bool
) -> Tuple[dict[str, Any], dict[str, str]]:
    vbt = get_build_template(build_template_name, build_template_major_version,
                             build_template_minor_version)
    return vbt, get_build_template_params(vbt, all_files,
                                          build_template_parameters,
                                          infer_build_template_arguments)


def get_build_templates(
        build_template_name: str, build_template_major_version: int,
        build_template_minor_version: int) -> list[dict[str, Any]]:
    query_filter = {}
    query_filter["deprecated"] = "false"
    if build_template_name != "":
        query_filter["name"] = build_template_name
        if build_template_major_version >= 0:
            query_filter["version.major"] = build_template_major_version
            if build_template_minor_version >= 0:
                query_filter["version.minor"] = build_template_minor_version
                del query_filter[
                    "deprecated"]  # they specified the exact template; include deprecated ones

    resp = requests.post(url=hise_url("tracer", "visualization_build_template",
                                      "filter"),
                         headers=get_bearer_token_header(),
                         json={"Filter": query_filter})
    return resp.json()


def get_build_template_params(
        vbt: dict[str, Any], all_files: set[str],
        build_template_parameters: dict[str, str],
        infer_build_template_arguments: bool) -> dict[str, str]:
    template_params = {}
    all_dirs = set([dirname(f) for f in all_files])
    for template_var in vbt['buildVariables']:
        varName = template_var['varName']
        var_value = None
        if varName in build_template_parameters and re.search(
                template_var['matchRegex'],
                build_template_parameters[varName]):
            var_value = build_template_parameters[varName]
        template_params[varName] = get_template_variable(
            template_var, all_files, all_dirs, infer_build_template_arguments,
            var_value)
    return template_params


class BuildTemplateVariableType(Enum):
    FILE = 1
    DIRECTORY = 2
    OTHER = 3


def get_template_variable(template_var: dict[str,
                                             Any], application_files: set[str],
                          application_dirs: set[str],
                          infer_build_template_arguments: bool,
                          provided_value: str | None) -> str:
    if provided_value == '' and not template_var['required']:
        return provided_value

    var_type = BuildTemplateVariableType.OTHER
    if template_var['isPath']:
        ds = template_var['directoryStructure']
        var_type = BuildTemplateVariableType.DIRECTORY if isinstance(
            ds, dict) and len(ds) > 0 else BuildTemplateVariableType.FILE

    def get_user_input() -> str:
        return input(f'Please enter {template_var["friendlyName"]}:')

    match var_type:
        case BuildTemplateVariableType.FILE:
            if infer_build_template_arguments and provided_value is None:
                found_file = ''
                for candidate in application_files:
                    if re.search(template_var['matchRegex'], candidate):
                        if found_file == '':
                            found_file = candidate
                        else:
                            found_file = ''
                            break

                if found_file != '':
                    return found_file

            user_input = provided_value or get_user_input()
            while True:
                if user_input == '' and not template_var['required']:
                    return ''
                elif re.search(template_var['matchRegex'],
                               user_input) and isfile(user_input):
                    user_input_abspath = abspath(user_input)
                    application_files.add(user_input_abspath)
                    return user_input_abspath

                user_input = get_user_input()
        case BuildTemplateVariableType.DIRECTORY:
            dir_structure = template_var['directoryStructure']
            if infer_build_template_arguments and provided_value is None:
                found_dir = ''
                for candidate in application_dirs:
                    if user_included_directory_structure(
                            candidate, dir_structure, application_files,
                            application_dirs):
                        if found_dir == '':
                            found_dir = candidate
                        else:
                            found_dir = ''
                            break

                if found_dir != '':
                    return found_dir

            user_input = provided_value or get_user_input()
            while True:
                if user_input == '' and not template_var['required']:
                    return ''
                elif re.search(template_var['matchRegex'],
                               user_input) and isdir(user_input):
                    user_input_abspath = abspath(user_input)
                    if user_included_directory_structure(
                            user_input_abspath, dir_structure):
                        # Include files in all subdirectories of the directory that the user gave us in our list of
                        # files that we will upload for this visualization app
                        for (dirpath, dirnames,
                             filenames) in walk(user_input_abspath):
                            application_dirs.update([
                                path.join(dirpath, dirname)
                                for dirname in dirnames
                            ])
                            application_files.update([
                                path.join(dirpath, filename)
                                for filename in filenames
                            ])
                        return user_input_abspath

                user_input = get_user_input()
        case BuildTemplateVariableType.OTHER:
            user_input = provided_value or get_user_input()
            while True:
                if user_input == '' and not template_var['required']:
                    return ''
                elif re.search(template_var['matchRegex'], user_input):
                    return user_input
                user_input = get_user_input()
    raise RuntimeError(f'impossible BuildTemplateVariableType {var_type}')


def user_included_directory_structure(
        user_dir: str,
        dir_structure: dict,
        included_files: set[str] | None = None,
        included_dirs: set[str] | None = None) -> bool:
    # We run this function in two modes:
    #   1. Check that the passed-in files and directories contain the provided directory structure rooted at user_dir
    #   2. Check that the filesystem itself contains the provided directory structure rooted at user_dir
    if xor(included_files is None, included_dirs is None):
        raise RuntimeError(
            'either both files and dirs must be included or neither files nor dirs can be included'
        )

    og_dirs = included_dirs
    og_files = included_files
    # We're checking the filesystem itself. Grab all the files and directories rooted at user_dir
    if included_dirs is None or included_files is None:
        included_dirs = set([])
        included_files = set([])
        for (dirpath, dirnames, filenames) in walk(user_dir):
            included_dirs = set(
                [path.join(dirpath, dirname) for dirname in dirnames])
            included_files = set(
                [path.join(dirpath, filename) for filename in filenames])
            break

    for name, val in dir_structure.items():
        if isinstance(val, dict):
            dirname = path.join(user_dir, name)
            if not dirname in included_dirs or not user_included_directory_structure(
                    dirname, val, og_files, og_dirs):
                return False
        elif isinstance(val, str):
            # Do we have a file with this exact name?
            if val == '':
                return path.join(user_dir, name) in included_files

            # Do we have a file that matches this regex?
            if not any(re.search(val, file) for file in included_files):
                return False
    return True
