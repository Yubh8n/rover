import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'rover_bringup'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'),
            glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='cbm',
    maintainer_email='chrisbmikkelsen@gmail.com',
    description='Bringup launch files for the rover',
    license='MIT',
    entry_points={
        'console_scripts': [],
    },
)