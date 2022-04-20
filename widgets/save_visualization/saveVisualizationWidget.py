import ipywidgets as widgets
import os
import hisepy as hp
from ipyfilechooser import FileChooser


# def save_visualization(pl_obj,
#                        study_space_id = None,
#                        title = None,
#                        input_file_ids = [],
#                        input_sample_ids = []):


fig_options = [('Choose a figure', None), 
               ('scatter', fig_scatter),
               ('bar', fig_bar),
               ('bubble', fig_bubble),
               ('heatmap', fig_heatmap),
               ('box', fig_box),
               ('histogram', fig_histogram),
               ('violin', fig_violin),
               ('distplot', fig_distplot),
               ('contour', fig_contour),
               ('mesh', fig_mesh)]

input_files = ["0fb06e51-74c4-46be-b92d-5e045232b2d9", "93ea6cb8-a45f-4370-bbfe-d57ba6420882", "9f9dbd27-2861-4600-9920-729dbcbd61da", "166a161c-b615-4476-b648-86701ae7230b", "07104c6c-80c2-415e-a906-8ba78e5c1936"]



class SaveVisualizationWidget:
    min_title_length = 10
    create_requirements = True
    study_space_dropdown_place_holder = 'Choose a Study space'
    study_space_dropdown_description = 'Study space:'

    plotly_obj_place_holder = 'plotly_figure_object'
    plotly_obj_description = 'Plotly fligure:'
    
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
    
    def __init__(self, pl_obj):
        self.pl_obj = pl_obj

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

        # try this - pass in the name of the actual object
        # get a list of the plotly objects in the current notebook
        self.pl_obj_text = widgets.Text(
            value='',
            placeholder=self.plotly_obj_place_holder,
            description=self.plotly_obj_place_description,
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
        
        # app path
        starting_directory = '/home/jupyter'
        select_desc = 'App.py:'
        change_desc = 'Select App.py:'
        self.app_file = FileChooser(starting_directory, select_desc, change_desc)
        self.app_file.filter_pattern = '*.py'
        # Customize dir icon
        self.app_file.dir_icon = '/'
        self.app_file.dir_icon_append = True

        # file ids -- list of strings, this is pasted in from advanced search
        self.input_files = widgets.Text(
            placeholder='"file1.pkl", "file2.json", "file3.csv"',
            description='File IDs:',
            disabled=False
        )

        self.save_button = widgets.Button(
            description=self.save_button_description,
            disabled=False,
            button_style='success',
            tooltip=self.save_button_tooltip
        )
        
        def on_save_button_click(evt):
            if self.study_space_dropdown.value is not None and len(self.title_text.value) >= min_title_length:
                print("saving...")
                # self.save_vis_result = hp.save_visualization(plotly_obj_dropdown.value, 
                # study_space_id=self.study_space_dropdown.value, 
                # title=title_text.value, 
                # input_files=self.input_files.value.split(','))

        def getSaveDashAppResult():
            return self.save_dash_app_result
        
        self.save_button.on_click(on_save_button_click)

        self.output = widgets.Output()

        display(self.study_space_dropdown, self.title_text, self.description_text, self.app_file, self.input_files, self.save_button, self.output)
    
    