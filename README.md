## Running HISEPY Locally
1. Start running toolchain-service locally. 
2. On the terminal do the commands below to set the required environment variables, build the repo, and open a python environment.

```
export TEST_TOOLCHAIN_SERVER=localhost:2082
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials/example.json
export AUTH_CLIENT_ID="example.apps.googleusercontent.com"
python3 setup.py build
python
```

The 'python' command opens the python environment and from there you can use hisepy. An example call is:

```
import hisepy as hp
hp.read_files(["33b7f255-382a-4ffd-a754-162bb480cd30"])
```
