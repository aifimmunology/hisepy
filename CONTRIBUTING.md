### To-do once after cloning:
* Set up and activate a virtual python environment (you're doing this in a virtual env, right?)
* Install development requirements: `pip install --requirement requirements-dev.txt`
* Install pre-commit hooks: `pre-commit install`.  
  This installs scripts that run prior to every commit to do things like autoformatting.  If you need to disable them 
  for any reason, use `git commit --no-verify`

Running locally
----
A few environment variables must be set to make HISE API calls:
```shell
export TOKEN_GENERATOR="/path/to/hisecli/hisecli auth"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-credentials-sa-dev-pipeline-internal-231c2bfbebfd.json"
```

For call that need the current notebook, you'll also want
```shell
export TEST_SCHEDULER_NOTEBOOK=FakeNotebookName.ipynb
```

The instance name can be set via `TEST_INSTANCE_NAME` or defaults to `local-testing-instance`.

You can point the SDK at your locally running services via
```shell
export TEST_TOOLCHAIN_SERVER=localhost:2082
export TEST_HYDRATION_SERVER=localhost:6080
export TEST_TRACER_SERVER=localhost:8081
# etc
```
