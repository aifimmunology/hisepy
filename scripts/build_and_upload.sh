# create .tar.gz file
python -m build --sdist 

# build recipe 
grayskull pypi dist/hisepy-*tar.gz

# move meta.yaml to recipe dir
mv hisepy/meta.yaml recipe/

# edit meta.yaml --> ray --> ray[default]

# build based off recipe/meta.yaml 
#conda build recipe \         
#  --output-folder conda_dist \
#  --override-channels \
#  -c conda-forge


# upload to conda-channel/conda-forge 
# anaconda upload ./conda_dist/noarch/hisepy-1.15.19.dev4+gcd2b2ba9c.d20260818-py_0.conda