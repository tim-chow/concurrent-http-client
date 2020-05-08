from setuptools import setup, find_packages

setup(
    name="concurrent_http_client",
    version="0.0.3",
    packages=find_packages(),
    install_requires=[
        "pycurl",
        "futures"
    ]
)
