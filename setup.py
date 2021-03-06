from setuptools import setup, find_packages

version = '@BUILD-LABEL@'

setup(
    name='ckanext-qgov',
    version=version,
    description='Customises CKAN behavior for Queensland Government portals',
    long_description='',
    classifiers=[],
    keywords='',
    author='Queensland Online',
    author_email='qol.development@smartservice.qld.gov.au',
    url='',
    license='',
    packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
    namespace_packages=['ckanext'],
    include_package_data=True,
    zip_safe=False,
    install_requires=[],
    entry_points="""
    [ckan.plugins]
    qgovext=ckanext.qgov.common.plugin:QGOVPlugin
    """,
)
