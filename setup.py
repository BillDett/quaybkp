"""Setup script for quaybkp."""

from setuptools import setup, find_packages

with open("requirements.txt", "r") as f:
    requirements = f.read().splitlines()

setup(
    name="quaybkp",
    version="1.0.0",
    description="Quay Blob Backup and Restore Tool",
    long_description=open("Quay Blob Backup and Restore Tool.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=[
        "boto3>=1.26.0",
        "PyYAML>=6.0", 
        "psycopg2-binary>=2.9.0",
        "click>=8.0.0",
        "tqdm>=4.64.0"
    ],
    extras_require={
        'gcs': ['google-cloud-storage>=2.5.0'],
        'azure': ['azure-storage-blob>=12.0.0'],
        'all': ['google-cloud-storage>=2.5.0', 'azure-storage-blob>=12.0.0']
    },
    entry_points={
        "console_scripts": [
            "quaybkp=quaybkp.main:main",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)