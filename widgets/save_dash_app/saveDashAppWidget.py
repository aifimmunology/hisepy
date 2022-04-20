import ipywidgets as widgets
import os
import hisepy as hp
from ipyfilechooser import FileChooser


# save_dash_app(app_filepath : str,
#                           filenames : list, 
#                           plotly_objects : list, 
#                           create_requirements : bool, 
#                           study_space_id,
#                           input_file_ids : list,
#                           custom_style_sheets : str,
#                           input_sample_ids : list = []):

# app_filepath = '/home/jupyter/dash_deploy/app.py'
filenames = ['merged.pkl','Readme.md']
plotly_objects = ['default_thumbnail.png']
# create_requirements = True
# study_space_id = '3f9e4093-49a6-445e-a3df-c12264f6ad10'
input_file_ids = ['0fb06e51-74c4-46be-b92d-5e045232b2d9', '93ea6cb8-a45f-4370-bbfe-d57ba6420882']
# dash_title = 'bidden-eth'
# dash_description = 'I have done as thou hast bidden-eth'

class SaveDashAppWidget:
    min_title_length = 10
    create_requirements = True
    study_space_dropdown_place_holder = 'Choose a Study space'
    study_space_dropdown_description = 'Study space:'
    
#     app_path_placeholder = 'app.py'
#     app_path_description = 'app.py'
    
#     file_names_placeholder = "'merged.pkl','Readme.md'"
#     file_names_description = "'merged.pkl','Readme.md'"
    
#     plotly_obj_text_placeholder = 'default_thumbnail.png'
#     plotly_obj_text_description = 'default_thumbnail.png'
    
#     thumbnail_names_placeholder = '"data.pkl","data.json","data.csv"'
#     thumbnail_names_description = 'app dependency files'
    
#     thumbnail_names_description = 'Create Requirements.txt file'

    title_text_placeholder = 'Type a title for the app'
    title_text_description = 'Title:'
    
    description_text_placeholder = 'Type a description for the app'
    description_text_description = 'Description:'
    
    file_list_description = 'Select App.py:'
    
#     custom_stylesheet_placeholder = 'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css'
#     custom_stylesheet_description = 'external style sheets'


    save_button_tooltip = 'Save Dash App'
    save_button_description = 'Save'
    
    def __init__(self):
        self.sp_options = [('Choose a study space', None)]
        study_spaces = hp.get_study_spaces()
        for sp in study_spaces:
            tpl = (sp['name'], sp['id'])
            self.sp_options.append(tpl)
    
        self.study_space_dropdown = widgets.Dropdown(
            placeholder=self.study_space_dropdown_place_holder,
            options=self.sp_options,
            description=self.study_space_dropdown_description,
        )

#         cwd = os.getcwd()
#         file_list = os.listdir(cwd)
#         file_list_tpl = res = tuple(file_list)
#         # abs_path = os.path.abspath(cwd + 'labResults.pkl')
        
#         self.app_file = widgets.Dropdown(
#             options=file_list_tpl,
#             description=self.file_list_description,
#             disabled=False
#         )
        
        # app path
        starting_directory = '/home/jupyter'
        select_desc = 'App.py:'
        change_desc = 'Select App.py:'
        self.app_file = FileChooser(starting_directory, select_desc, change_desc)
        self.app_file.filter_pattern = '*.py'
        # Customize dir icon
        self.app_file.dir_icon = '/'
        self.app_file.dir_icon_append = True

        # plotly objects -- list of strings, this is user selected
        # it could be in sub directories to like assets dir

        # file ids -- list of strings, this is pasted in from advanced search
        self.input_file_ids = widgets.Text(
            placeholder='"file1.pkl", "file2.json", "file3.csv"',
            description='File IDs:',
            disabled=False
        )

        self.title_text = widgets.Text(
            value='',
            placeholder=self.title_text_placeholder,
            description=self.title_text_description,
            disabled=False
        )

        self.description_text = widgets.Text(
            value='',
            placeholder=self.description_text_placeholder,
            description=self.description_text_description,
            disabled=False
        )

        # input sample ids -- list of sample ids
        self.input_sample_ids = widgets.Text(
            placeholder='"sample_id_1, "sample_id_2", "sample_id_3"',
            description='Sample IDs:',
            disabled=False
        )

        self.save_button = widgets.Button(
            description=self.save_button_description,
            disabled=False,
            button_style='success',
            tooltip=self.save_button_tooltip
        )
        
        def on_save_button_click(evt):
            if self.study_space_dropdown.value is not None and len(self.title_text.value) >= self.min_title_length:
                print("saving...")
                # self.save_result = hp.save_dash_app(app_filepath=self.app_file.value, 
                # filenames=filenames, 
                # plotly_objects=, 
                # create_requirements=self.create_requirements, 
                # study_space_id=self.study_space_dropdown.value, 
                # input_file_ids=self.input_file_ids.value.split(','), 
                # dash_title=self.title_text.value,
                # dash_description=self.description_text.value,
                # custom_style_sheets="",
                # input_sample_ids=self.input_sample_ids.value.split(','))

        def getSaveDashAppResult():
            return self.save_dash_app_result
        
        self.save_button.on_click(on_save_button_click)

        self.output = widgets.Output()

        display(self.study_space_dropdown, self.title_text, self.description_text, self.app_file, self.input_file_ids, self.input_sample_ids, self.save_button, self.output)
    
    
    
