import distutils.core
distutils.core.setup(
    name = 'pyjdb',
    version = '0.1',
    author = "Christopher Suter",
    author_email = "cgs@alltheburritos.com",
    url = "github.com/cgs1019/pyjdb",
    download_url = "",
    package_dir = {
        'pyjdb': 'src/pyjdb',
    },
    packages = [ \
        'pyjdb',
        'pyjdb.internal'
    ],
)
