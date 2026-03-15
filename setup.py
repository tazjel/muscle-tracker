from setuptools import setup, find_packages

setup(
    name="muscle_tracker",
    version="2.0.0",
    description="Clinical-grade muscle growth analysis suite with CV metrology",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "opencv-python>=4.8.0",
        "opencv-contrib-python>=4.8.0",
        "numpy>=1.24.0",
    ],
    extras_require={
        "web": ["py4web>=1.20231001"],
    },
    entry_points={
        "console_scripts": [
            "muscle-tracker=muscle_tracker:main",
        ],
    },
)
