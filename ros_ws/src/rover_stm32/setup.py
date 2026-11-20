from glob import glob

from setuptools import find_packages, setup

package_name = 'rover_stm32'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/systemd', glob('systemd/*.service')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    extras_require={'test': ['pytest']},
    maintainer='cbm',
    maintainer_email='cbm@todo.todo',
    description='Serial link to the Rover STM32: firmware version/boot state, update, app messages',
    license='TODO: License declaration',
    entry_points={
        'console_scripts': [
            'stm32_link = rover_stm32.stm32_node:main',
        ],
    },
)
