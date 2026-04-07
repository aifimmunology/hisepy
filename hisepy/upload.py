def upload_file_map(file_list):
    # This function accepts a list of dicts, each dict containing info for file upload
    for file_info in file_list:
        # Extract relevant information from each file_info dict
        file = file_info['file']
        file_type = file_info['file_type']
        input_sample_ids = file_info['input_sample_ids']
        input_sample_kit_guids = file_info['input_sample_kit_guids']
        # Implement file upload logic here
        pass


def upload_files(files, input_sample_ids=None, file_types=None, input_sample_kit_guids=None):
    # Transform the inputs into a list of dicts
    file_list = []
    for i in range(len(files)):
        file_list.append({
            'file': files[i],
            'file_type': file_types[i] if file_types else None,
            'input_sample_ids': input_sample_ids[i] if input_sample_ids else None,
            'input_sample_kit_guids': input_sample_kit_guids[i] if input_sample_kit_guids else None
        })
    # Call the shared internal implementation
    return upload_file_map(file_list)
