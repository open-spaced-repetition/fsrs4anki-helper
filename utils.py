import re


def get_version(custom_scheduler):
    return list(map(int, re.findall(f'v(\d+).(\d+).(\d+)', custom_scheduler)[0]))