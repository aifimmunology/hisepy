import ipywidgets as widgets
from pathlib import Path
import hisepy as hp

class SaveDashAppWidget:
    min_title_length = 10
    study_space_dropdown_place_holder = 'Choose a Study space'
    study_space_dropdown_description = 'Study space:'

    title_text_placeholder = 'Type a title for the app'
    title_text_description = 'Title:'
    
    description_text_placeholder = 'Type a description for the app'
    description_text_description = 'Description:'
    
    file_list_description = 'Select App.py:'
    app_filepath_label = 'App file:'
    
    image_filepath_description = 'PNG File:'
    
    input_file_ids_placeholder = '"DEF-456","ABC-123"'
    input_file_ids_description = 'File IDs:'
    
    input_sample_ids_placeholder = '"DEF-456","ABC-123"'
    input_sample_ids_description = 'Sample IDs:'
    
    additional_files_description = 'Additional Files:'

    save_button_tooltip = 'Save Dash App'
    save_button_description = 'Save'
    save_button_label = 'Save to study space:'
    
    heading_text = 'Save Dash App to Study Space'
    
    def __init__(self):
        self.save_dash_app_result = None
        
        self.heading_text = widgets.HTML(
            value="<h1>" + SaveDashAppWidget.heading_text + "</h1>",
        )
        
        self.app_filepath = widgets.Select(
            options=self.build_file_list(Path.cwd()),
            disabled=False
        )
        
        self.additional_files = widgets.SelectMultiple(
            options=self.build_file_list(Path.cwd()),
            rows=10,
            disabled=False
        )
        
        self.sp_options = [('Choose a study space', None)]
        study_spaces = hp.get_study_spaces()
        for sp in study_spaces:
            tpl = (sp['name'], sp['id'])
            self.sp_options.append(tpl)
    
        self.study_space_dropdown = widgets.Dropdown(
            placeholder=SaveDashAppWidget.study_space_dropdown_place_holder,
            options=self.sp_options,
            # description=SaveDashAppWidget.study_space_dropdown_description,
        )

        self.title_text = widgets.Text(
            value='',
            placeholder=SaveDashAppWidget.title_text_placeholder,
            disabled=False
        )

        self.description_text = widgets.Text(
            value='',
            placeholder=SaveDashAppWidget.description_text_placeholder,
            disabled=False
        )
        
        self.image_filepath = widgets.Select(
            options=self.build_file_list(Path.cwd()),
            # rows=10,
            disabled=False
        )
        
        self.input_file_ids = widgets.Text(
                            placeholder=SaveDashAppWidget.input_file_ids_placeholder,
                            disabled=False
                        )
        
        self.input_sample_ids = widgets.Text(
                            placeholder=SaveDashAppWidget.input_sample_ids_placeholder,
                            disabled=False
                        )
        
        self.save_button = widgets.Button(
            description=SaveDashAppWidget.save_button_description,
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
                    
        self.additional_files.observe(on_additional_files_change, names='value')
        
        def on_save_button_click(evt):
            if self.study_space_dropdown.value is not None and len(self.title_text.value) >= SaveDashAppWidget.min_title_length:
                print(str(self.app_filepath.value))
                print(self.get_selected_files(self.additional_files.value))
                print(self.resolve_ids(self.input_file_ids.value))
                print(self.resolve_ids(self.input_sample_ids.value))
                print(self.study_space_dropdown.value)
                print(self.title_text.value)
                print(self.description_text.value)
                print(Path(self.image_filepath.value).name) # or str(Path(self.image_filepath.value).resolve()) - for full path
                self.save_dash_app_result = hp.save_dash_app(app_filepath=str(self.app_filepath.value),
                                                    additional_files=self.get_selected_files(self.additional_files.value), 
                                                    input_file_ids=self.resolve_ids(self.input_file_ids.value),
                                                    input_sample_ids=self.resolve_ids(self.input_sample_ids.value),
                                                    study_space_id=self.study_space_dropdown.value, 
                                                    title=self.title_text.value,
                                                    description=self.description_text.value, 
                                                    image=Path(self.image_filepath.value).name)

        self.save_button.on_click(on_save_button_click)

        self.output = widgets.Output()
        
        # rows and columns
        self.grid = widgets.GridspecLayout(5, 6);
        
        # heading text
        self.grid[0, 1:4] = self.heading_text
        
        # app specific info
        self.grid[1, 0] = widgets.Label(SaveDashAppWidget.study_space_dropdown_description)
        self.grid[1, 1] = self.study_space_dropdown
        self.grid[1, 2] = widgets.Label(SaveDashAppWidget.title_text_description)
        self.grid[1, 3] = self.title_text
        self.grid[1, 4] = widgets.Label(SaveDashAppWidget.description_text_description)
        self.grid[1, 5] = self.description_text
        # app files
        self.grid[2, 0] = widgets.Label(SaveDashAppWidget.app_filepath_label)
        self.grid[2, 1] = self.app_filepath
        self.grid[2, 2] = widgets.Label(SaveDashAppWidget.additional_files_description)
        self.grid[2, 3] = self.additional_files
        self.grid[2, 4] = widgets.Label(SaveDashAppWidget.image_filepath_description)
        self.grid[2, 5] = self.image_filepath
        # file or sample ids
        self.grid[3, 0] = widgets.Label(SaveDashAppWidget.input_file_ids_description)
        self.grid[3, 1] = self.input_file_ids
        self.grid[3, 2] = widgets.Label(SaveDashAppWidget.input_sample_ids_description)
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
    
    def getSaveDashAppResult(self):
            return self.save_dash_app_result
    
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
        if ids_str:
            ids_list = list(map(lambda id: str.strip(id), ids_str.replace('"', "").split(',')))
            return ids_list
        else:
            return []