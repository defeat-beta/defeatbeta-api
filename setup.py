from setuptools import setup, find_packages

version = {}
with open("defeatbeta_api/__version__.py") as f:
    exec(f.read(), version)

setup(
    name="defeatbeta_api",
    version=version["__version__"],
    packages=find_packages(),
    install_requires=[],
    python_requires=">=3.8",
)

