# setup.py

from setuptools import setup, find_packages

setup(
    name="motion_lang",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "lark>=1.1.9",
        "moviepy>=1.0.3",
        "duckduckgo_search>=4.0.0",
        "rembg>=2.0.50",
        "onnxruntime>=1.16.0",       # CPU ONNX runtime engine for rembg
        "opencv-python>=4.8.0",       # OpenCV for preview window & video handling
        "Pillow>=10.0.0",
        "requests>=2.31.0",
        "numpy",
    ],
    extras_require={
        # Optional: Run `pip install -e .[gpu]` if you want CUDA hardware acceleration
        "gpu": [
            "onnxruntime-gpu>=1.16.0",
        ],
        # Optional: Run `pip install -e .[pygame]` for Pygame preview window support
        "pygame": [
            "pygame>=2.5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "motion=motion_lang.cli:main",
        ],
    },
)