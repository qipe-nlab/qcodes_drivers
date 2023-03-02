from setuptools import setup, find_packages

setup(
    name="qcodes_drivers",
    packages=find_packages(),
    package_data={"qcodes_drivers": ['HVI_Delay/*']},
)
