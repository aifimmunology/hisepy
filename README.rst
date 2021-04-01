HISEPY
===========

Python Interface to the Allen Institute For Immunology's Human Immune System Explorer (HISE)

```
from hisepy import hise_file, read_files, schedule_hsn_notebook
```

Working With Files
----------
```
# read and work with a single file
my_file = hise_file('9f6d7ab5-1c7b-4709-9455-3d8ff3fbb6c8') # initialize a file from HISE
my_file.status                                              # True/False: file is downloaded
my_file.load()                                              # download the file 
my_file.path                                                # where it wound up
my_file.descriptors                                         # the descriptors for the file 

# initialize and load a batch of hise_files at once:
my_files = read_files([
  "246528ce-593d-4106-80d6-735bdb8ee35d",
  "f7081d4a-8e9e-42a2-a899-335384e37d78",
  "c53e8d62-141c-413b-94e4-9e9b55510ce8",
  "314f07ea-9237-4ed7-bb19-da052e8d1ad0"])                   
```

Scheduling HSNE Jobs
--------------------
```
events = a_pandas_data_frame or a_numpy_ndarry             
result = schedule_hsne_notebook(
  data = events,
  num_scales = 5,
  graph_scale_index = 4,
  project = "cohorts")
```
