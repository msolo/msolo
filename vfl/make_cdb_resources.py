#!/usr/bin/env python

# want to pack a number of files into one - for primarily read access
 
import logging
import os
import os.path
import re
import shutil

import cdb

log = logging.getLogger('cdbfs')

class CDBFSException(Exception):
    pass

def pack_tree(cdb_file, base_path):
    exclude_list = ['.svn',]
    version_map = {}
    cdb_maker = cdb.cdbmake(cdb_file, cdb_file + '.tmp')
    
    base_path = os.path.abspath(base_path)
    for (path, dir_list, file_list) in os.walk(base_path):
        for dirname in exclude_list:
            if dirname in dir_list:
                dir_list.remove(dirname)

        for filename in file_list:
            relative_dir = path[len(base_path):]
            if not relative_dir:
                relative_dir = '/'
                # print 'no relative_dir', path, filename
            absolute_path = os.path.join(path, filename)
            relative_path = os.path.join(relative_dir, filename)
            f = open(absolute_path)
            data = f.read()
            f.close()
            cdb_maker.add(relative_path, data)

    cdb_maker.finish()

if __name__ == '__main__':
    from optparse import OptionParser
    import sys

    def validate_file(option, opt_str, value, parser):
        value = os.path.expanduser(value)
        setattr(parser.values, option.dest, value)

    option_parser = OptionParser()
    option_parser.add_option('-v', dest='verbose', default=False, action='store_true')
    option_parser.add_option('--cdb-file',
                             action='callback', callback=validate_file,
                             type='str', nargs=1,
                             help="cdb file to write to")
    option_parser.add_option('--base-dir',
                             action='callback', callback=validate_file,
                             type='str', nargs=1,
                             help="directory to recurse and add files from")
    
    (options, args) = option_parser.parse_args()
    if not (options.cdb_file and options.base_dir):
        print >> sys.stderr, 'must specify --cdb-file and --base-dir'
        sys.exit(1)

    pack_tree(options.cdb_file, options.base_dir)
    

