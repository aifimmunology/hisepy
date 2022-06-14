import ipywidgets as widgets
from pathlib import Path
import hisepy as hp

class SaveVisualizationWidget:
        
    min_title_length = 10
    study_space_dropdown_place_holder = 'Choose a Study space'
    study_space_dropdown_description = 'Study space:'

    title_text_placeholder = 'Type a title for the visualization'
    title_text_description = 'Title:'
    
    description_text_placeholder = 'Type a description for the visualization'
    description_text_description = 'Description:'
    
    file_list_description = 'Select App.py:'
    app_filepath_label = 'App.py:'
    
    input_file_ids_placeholder = '"DEF-456","ABC-123"'
    input_file_ids_description = 'File IDs:'
    
    input_sample_ids_placeholder = '"DEF-456","ABC-123"'
    input_sample_ids_description = 'Sample IDs:' 

    save_button_tooltip = 'Save Visualization'
    save_button_description = 'Save'
    save_button_label = 'Save to study space:'
    
    heading_text = 'Save Visualization to Study Space'
    
    def __init__(self, plotly_obj):
        self.heading_text = widgets.HTML(
            value="<h1>" + SaveVisualizationWidget.heading_text + "</h1>",
        )
        
        self.plotly_obj = plotly_obj
        
        self.sp_options = [('Choose a study space', None)]
        study_spaces = hp.get_study_spaces()
        for sp in study_spaces:
            tpl = (sp['name'], sp['id'])
            self.sp_options.append(tpl)
    
        self.study_space_dropdown = widgets.Dropdown(
            placeholder=SaveVisualizationWidget.study_space_dropdown_place_holder,
            options=self.sp_options
        )

        self.title_text = widgets.Text(
            value='',
            placeholder=SaveVisualizationWidget.title_text_placeholder,
            disabled=False
        )

        self.description_text = widgets.Text(
            value='',
            placeholder=SaveVisualizationWidget.description_text_placeholder,
            disabled=False
        )
        
        self.input_file_ids = widgets.Text(
                            placeholder=SaveVisualizationWidget.input_file_ids_placeholder,
                            disabled=False
                        )
        
        self.input_sample_ids = widgets.Text(
                            placeholder=SaveVisualizationWidget.input_sample_ids_placeholder,
                            disabled=False
                        )
        
        self.save_button = widgets.Button(
            description=SaveVisualizationWidget.save_button_description,
            disabled=False,
            tooltip=self.save_button_tooltip,
            layout=widgets.Layout(width='auto', height='3rem', border='1px solid #33B0C8', border_radius='.25rem', margin='1rem 0 0 0'),
        )
        
        self.save_button.style.button_color='#76CFE0'
        self.save_button.style.color='white'

        def on_additional_files_change(change):
            selected_item = change['new']
            if selected_item:
                if selected_item[0].is_dir():
                    cwd = Path(selected_item[0])
                    self.additional_files.options=self.build_file_list(cwd)
                            
        def on_save_button_click(evt):
            if self.study_space_dropdown.value is not None and len(self.title_text.value) >= SaveVisualizationWidget.min_title_length:
                self.save_result = hp.save_visualization(pl_obj=self.plotly_obj, 
                                                         study_space_id=self.study_space_dropdown.value, 
                                                         title=self.title_text.value, 
                                                         input_file_ids=self.resolve_ids(self.input_file_ids.value), 
                                                         input_sample_ids=self.resolve_ids(self.input_sample_ids.value))

        self.save_button.on_click(on_save_button_click)

        self.output = widgets.Output()
        
        # rows and columns
        self.grid = widgets.GridspecLayout(5, 6);
        
        # heading text
        self.grid[0, 1:4] = self.heading_text
        
        # app specific info
        self.grid[1, 0] = widgets.Label(SaveVisualizationWidget.study_space_dropdown_description)
        self.grid[1, 1] = self.study_space_dropdown
        self.grid[1, 2] = widgets.Label(SaveVisualizationWidget.title_text_description)
        self.grid[1, 3] = self.title_text

        # file or sample ids
        self.grid[3, 0] = widgets.Label(SaveVisualizationWidget.input_file_ids_description)
        self.grid[3, 1] = self.input_file_ids
        self.grid[3, 2] = widgets.Label(SaveVisualizationWidget.input_sample_ids_description)
        self.grid[3, 3] = self.input_sample_ids
        # save to study space
        self.grid[4, 1:2] = self.save_button
        
        self.grid.layout.background_color='#f5f5f5'
        self.grid.layout.border='1px solid #33B0C8'
        self.grid.layout.border_radius='.25rem'
        self.grid.layout.padding='.5rem'
        self.grid.layout.grid_template_columns='1.5fr 1'
        self.grid.layout.grid_template_rows='min-content'
        self.grid.layout.grid_gap='1rem'
        # self.grid.layout.justify_items='flex-end'

        display(self.grid, 
                self.output)
    
    def getSaveVizResult(self):
            return self.save_result
    
    def build_file_list(self, current_path):
        file_list_tpl = []
        for child in current_path.iterdir():
            if child.is_dir():
                tpl = ("./" + child.name, child)
                file_list_tpl.append(tpl)
            else:
                tpl = (child.name, child)
                file_list_tpl.append(tpl)

        parent_dir = ("../", current_path.parent)
        file_list_tpl.insert(0, parent_dir)

        return file_list_tpl
        
    def get_selected_files(self, file_tpls):
        fl_list = []
        if len(file_tpls) > 0:
            for fl_path in file_tpls:
                if fl_path.is_file():
                    fl_list.append(fl_path.name) # the full file path as a string. str(your_path.resolve())
                
        return fl_list
    
    def resolve_ids(self, ids_str):
        ids_list = []
        if ids_str:
            ids_list = ids_str.replace('"', "").split(',')
            
        return ids_list
