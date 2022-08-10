import os
from setuptools import setup, find_packages

# 0.1.2: Bug fix
version = "0.1.2"
test_version = "0.1.2.0"

install_requirements = []
if os.path.isfile("requirements.txt"):
    with open("requirements.txt", "r") as f:
        install_requirements = f.read().splitlines()


with open("README.md", "r") as rm:
    README = rm.read()

setup(
    name="eve_tools",
    version=version,
    author="Hanbo",
    author_email="hb.evetools@gmail.com",
    description="Tools collection for EVE game plays.",
    long_description=README,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,
    install_requires=install_requirements,
    license="BSD 3-Clause License",
    keywords=["python", "esi", "eveonline"],
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        # 3.6 fails because of new version of aiohttp. Module typing lacks some submodules in 3.6.
        "Programming Language :: Python :: 3.7",  # tested with testcases
        "Programming Language :: Python :: 3.8",  # tested with testcases
        "Programming Language :: Python :: 3.9",  # tested with testcases
        "Programming Language :: Python :: 3.10",  # tested with testcases
        "Intended Audience :: Developers",
    ],
)
