HISEPY
===========

Python Interface to the Allen Institute For Immunology's Human Immune System Explorer (HISE)

``import hisepy``

Working With Files
----------

::

  # read and work with a single file
  my_file = hisepy.hise_file('9f6d7ab5-1c7b-4709-9455-3d8ff3fbb6c8')
  my_file.status                                              # True/False: file is downloaded
  my_file.load()                                              # download the file 
  my_file.path                                                # where it wound up
  my_file.descriptors                                         # the descriptors for the file 

  # initialize and load a batch of hise_files at once:
  my_files = hisepy.read_files([
    "246528ce-593d-4106-80d6-735bdb8ee35d",
    "f7081d4a-8e9e-42a2-a899-335384e37d78",
    "c53e8d62-141c-413b-94e4-9e9b55510ce8",
    "314f07ea-9237-4ed7-bb19-da052e8d1ad0"])                   

Scheduling HSNE Jobs
--------------------

::

  events = a_pandas_data_frame or a_numpy_ndarry             
  result = hisepy.schedule_hsne_notebook(
    data = events,
    num_scales = 5,
    graph_scale_index = 4,
    project = "cohorts")

Scheduling General Notebook Jobs
--------------------

::

   def a_func_to_run_on_a_larger_instance(args):
     #some heavy-weight function
     #that takes in an args dictionary 
     #and outputs foo.csv and bar.txt
     #...
     
   job = hisepy.schedule_notebook(["foo.csv","bar.txt"],
                                  function = a_func_to_run_on_a_larger_instance,
                                  function_args = {"something": "that i want to pass to my function"})
   #is the job done?
   job.is_completed()
   #what's the status?
   job.status
   #when it is completed...
   file_refs = job.download_output()

Building the HISEPY Package
---------------------------

::

  # add channels to the build environment
  conda config --env --add channels conda-forge

  # install grayskull -- the skeleton generator
  conda install -c conda-forge grayskull

  # build the package, create the meta.yaml file
  conda skeleton pypi --extra-specs cython sep
  

  # note that Pinning is important for SEP for packages
  # that use C API through Cython should use the same package 
  # version at runtime that was used at build time.

  # 1. set up custom discovery (`find` directive with `include` or `exclude`)
  # 2. use a `src-layout`
  # 3. explicitly set `py_modules` or `packages` with a list of names

  # To find more information, look for "package discovery" on setuptools docs.


"""