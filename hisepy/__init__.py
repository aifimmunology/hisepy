from .formatter import (hise_file_to_df, subject_to_df, sample_to_df,
                        _dict_to_df)
from .lookup import (lookup_queryable_fields, lookup_unique_entries)
from .project_folder import (list_project_folders,
                             list_files_in_project_folder,
                             download_from_project_folder,
                             archive_file_in_project_folder,
                             undo_archive_in_project_folder)
from .reader import (hise_file, read_files, read_subjects, read_samples,
                     query_files, get_file_descriptors, cache_filesets,
                     list_filesets)
from .scRNA_utils import (read_obs, read_mat, read_genes, create_AnnData)
from .scheduler import (notebook_job, schedule_notebook, get_notebook_job,
                        clear_notebook_job)
from .upload import (upload_files, save_static_image, save_visualization,
                     load_visualization, get_trace, get_study_spaces,
                     get_files_for_query, save_dash_app)
from .instances import (stop_ide, suspend_ide)
from .version import __version__

# if somebody does "from somepackage import *", this is what they will
# be able to access:
__all__ = [
    'hise_file',
    'read_files',
    'read_subjects',
    'read_samples',
    'schedule_notebook',
    'get_notebook_job',
    'clear_notebook_job',
    'notebook_job',
    'hise_file_to_df',
    'subject_to_df',
    'sample_to_df',
    'lookup_queryable_fields',
    'lookup_unique_entries',
    'list_project_folders',
    'list_files_in_project_folder',
    'download_from_project_folder',
    'archive_file_in_project_folder',
    'undo_archive_in_project_folder',
    'upload_files',
    'save_static_image',
    'save_visualization',
    'load_visualization',
    'get_study_spaces',
    'get_trace',
    'get_files_for_query',
    'save_dash_app',
    'list_filesets',
    'cache_filesets',
]
