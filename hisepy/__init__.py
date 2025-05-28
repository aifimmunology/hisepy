from .formatter import (hise_file_to_df, subject_to_df, sample_to_df,
                        _dict_to_df)
from .lookup import (lookup_queryable_fields, lookup_unique_entries)
from .project_store import (list_project_stores, list_files_in_project_store,
                            download_from_project_store,
                            promote_file_in_project_store,
                            undo_promote_in_project_store,
                            delete_file_in_project_store,
                            undo_delete_in_project_store)
from .project_folder import (list_project_folders,
                             list_files_in_project_folder,
                             download_from_project_folder)
from .reader import (hise_file, MongoQuery, read_files, read_subjects,
                     read_samples, query_files, get_file_descriptors,
                     cache_fileset, list_filesets, cache_files)
from .scheduler import (notebook_job, schedule_notebook, get_notebook_job,
                        clear_notebook_job)
from .upload import (save_static_image, save_visualization, load_visualization,
                     get_trace, get_study_spaces, get_files_for_query,
                     save_dash_app, set_default_store, set_default_project,
                     get_default_store, get_default_project, upload_files,
                     retry_ide_commit)
from .utils import (set_memory_limit, get_memory_usage, conda_env_builds)
from .abstraction import (save_abstraction, result_filetype_to_guid,
                          get_result_files)
from .private_folders import (
    list_files_in_all_private_folders, list_files_in_private_folder,
    move_file_in_private_folder, delete_file_in_private_folder,
    download_from_private_folder, rename_file_in_private_folder,
    upload_file_to_private_folder, delete_private_folder,
    find_private_folder_of_file)
from .instances import (stop_ide)
from .training_job import (start_training_run) #list_all_training_jobs, get_training_job, get_training_job_status, start_training_run) 
from .version import __version__

# if somebody does "from somepackage import *", this is what they will
# be able to access:
__all__ = [
    'hise_file', 'read_files', 'read_subjects', 'read_samples',
    'schedule_notebook', 'get_notebook_job', 'clear_notebook_job',
    'notebook_job', 'hise_file_to_df', 'subject_to_df', 'sample_to_df',
    'lookup_queryable_fields', 'lookup_unique_entries', 'list_project_stores',
    'list_files_in_project_store', 'download_from_project_store',
    'promote_file_in_project_store', 'undo_promote_in_project_store',
    'delete_file_in_project_store', 'undo_delete_in_project_store',
    'list_project_folders', 'list_files_in_project_folder',
    'download_from_project_folder', 'upload_files', 'retry_ide_commit',
    'save_static_image', 'save_visualization', 'load_visualization',
    'get_result_files', 'get_study_spaces', 'get_trace', 'get_files_for_query',
    'save_dash_app', 'list_filesets', 'cache_filesets', 'save_abstraction',
    'set_default_store', 'set_default_project', 'get_default_store',
    'get_default_project', 'set_memory_limit', 'get_memory_usage'
]
