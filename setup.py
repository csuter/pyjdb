import distutils.core
distutils.core.setup(
    name = 'pyjdwp',
    version = '0.1',
    author = "Christopher Suter",
    author_email = "cgs@alltheburritos.com",
    url = "github.com/cgs1019/pyjdb",
    download_url = "",
    package_dir = {
        'pyjdwp': 'pyjdwp',
    },
    package_data = {
        'pyjdwp': ['specs/jdwp.spec*'],
    },
    packages = [
        'pyjdwp',
    ],
)
