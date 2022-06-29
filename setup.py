from setuptools import setup, find_packages

# 0.1.1: Packaging to PyPI
version = "0.1.1"
test_version = "0.1.1.1"

install_requirements = [
    "pandas",
    "numpy",
    "requests",
    "aiohttp",
    "python-jose",
    "pyperclip",
    "pyyaml",
]

with open("README.md", "r") as rm:
    README = rm.read()

setup(
    name="eve_tools",
    version=version,
    author="Hanbo",
    author_email="ghbhanbo@gmail.com",
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
