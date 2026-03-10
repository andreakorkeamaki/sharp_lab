from setuptools import find_packages, setup


setup(
    name="sharp_lab",
    version="0.1.0",
    description="Local tools for experimenting with iPhone photos and preparing assets for Apple SHARP workflows.",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    package_data={
        "sharp_lab.ui": ["static/*.html", "static/*.css", "static/*.js"],
    },
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "sharp-lab=sharp_lab.cli:main",
        ]
    },
    extras_require={
        "dev": [
            "pytest>=8.0",
        ],
        "release": [
            "build>=1.2",
            "pyinstaller>=6.0",
        ],
    },
)
