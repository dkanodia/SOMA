from setuptools import setup, find_packages

setup(
    name="soma",
    version="0.1.0-prototype",
    description=(
        "Signaling-Optimal Memory Architecture: "
        "autonomous cyber defense via RL and signaling game theory. "
        "Research prototype — not operationally validated."
    ),
    author="TODO",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "torch>=2.0.0",
        "stable-baselines3>=2.0.0",
        "scikit-learn>=1.3.0",
        "scipy>=1.11.0",
        "numpy>=1.24.0",
        "gymnasium>=0.29.0",
        "matplotlib>=3.7.0",
        "fastapi>=0.100.0",
        "websockets>=11.0",
        "uvicorn>=0.23.0",
        "tqdm>=4.65.0",
        "pyyaml>=6.0",
    ],
    extras_require={
        "dev": ["pytest>=7.4.0", "pytest-cov>=4.1.0", "jupyter>=1.0.0"],
    },
)
