from __future__ import print_function
import __main__
import datetime
import itertools
import os
import time

SCRIPT_NAME = os.path.basename(__main__.__file__)

def log(message, level='INFO'):
    print('{} [{}] ({}) {}'.format(datetime.datetime.now().strftime('%y-%m-%d %H:%M:%S'), level, SCRIPT_NAME, message))

def one(iterables):
    heads = list(itertools.islice(iterables, 2))
    if len(heads) == 0:
        raise Exception('Try to get one element from an empty iterable')
    if len(heads) > 1:
        raise Exception('More than 1 elements in {}'.format(iterables))
    return heads[0]

def flatten(listoflists):
    return [item for l in listoflists for item in l]

def paginate(l, page_size):
    return [l[i:i+page_size] for i in xrange(0, len(l), page_size)]

def attempt(what, how, max_try=30, interval=5):
    for i in xrange(max_try):
        if i > 0:
            log('Attempting {} of {} to {}...'.format(i+1, max_try, what))

        success = how()
        if success:
            return True

        if i < max_try - 1:
            time.sleep(interval)

    return False
