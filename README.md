## HISEPY IDE LocalHostTesting
Start running toolchain-service locally then on the terminal set these environment variables, build the repo, and run hisepy.

```
export TEST_TOOLCHAIN_SERVER=localhost:2082
export GOOGLE_APPLICATION_CREDENTIALS=/Users/madeline.ambrose/Documents/Keys/personal/dev-pipeline-internal-34e47d8f7d57.json
(Make sure this GOOGLE_APPLICATION_CREDENTIALS is also set for hisecli when getting the auth token from there)
export AUTH_CLIENT_ID="example.apps.googleusercontent.com"
python3 setup.py build
python
```

This opens the python environment

Example call from there:
import hisepy as hp
hp.read_files(["33b7f255-382a-4ffd-a754-162bb480cd30"])
