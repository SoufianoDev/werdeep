from Cython.Build import cythonize
from setuptools import Extension, setup

extensions = [
    Extension(
        "werdeep.engine.parser",
        ["src/werdeep/engine/parser.pyx"],
    ),
    Extension(
        "werdeep.engine.formatter",
        ["src/werdeep/engine/formatter.pyx"],
    ),
    Extension(
        "werdeep.external.html_to_markdown._html_to_markdown",
        ["src/werdeep/external/html_to_markdown/_html_to_markdown.pyx"],
    ),
    Extension(
        "werdeep.external.html_to_markdown.api",
        ["src/werdeep/external/html_to_markdown/api.pyx"],
    ),
    Extension(
        "werdeep.external.html_to_markdown.options",
        ["src/werdeep/external/html_to_markdown/options.pyx"],
    ),
    Extension(
        "werdeep.external.html_to_markdown.exceptions",
        ["src/werdeep/external/html_to_markdown/exceptions.pyx"],
    ),
]

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "embedsignature": True,
        },
    ),
)
