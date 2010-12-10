
# want a versioned file layout that exposes multiple versions of files with the
# same logical filename in the code. each url then has 'infinite' expiration.
#
# so this url referenced in code:
#   /css/base.css
# resolves to this file:
#   /htdocs/css/base-vfl2048.css
# mapped to this url:
#   http://www.blah.com/css/base-vfl2048.css
#
# you can then prune based on the number of revisions you want to keep

# release process:
#  * checkout release version
#  * create versioned file tree
#  * create versioned index (python pickle? cdb?)
#  * prune versions to max revisions
#  * push versioned file tree (rsync w/ --delete)
#  * move versioned index to web code
#  * restart web processes to pick up new resource version index

# this was working all fine until i realized that things like css and
# javascript - classically static things - can themselves include resources
# that i want to version.
#
# i have a 2 problems. i want this to be simple for designers to use
# in the average case. i also want to have close to 100% coverage. this means
# that i need to generate a dependency tree from web resources and then dump
# out a copy with the correct versions substituted. this also means i don't
# get a fancy syntax (since i want backward compatibility) - so i need to rely
# on the kindness of strangers and their ability to follow simple conventions.
#
# the convention is that site-relative urls in css and javascript will be
# automatically versioned - so things starting with a / and ending with what
# looks like a file extension - we'll see how it goes.
#
# this results in a 2-stage 'compile' process.
#  * generate version index (see above)
#  * for each css and javascript file, parse it and look for subresources
#    * if it has subresources
#      * substitute all urls with versioned urls
#      * re-version the parent to the max revision of any resource/subresource

__author__ = 'Mike Solomon'
__author_email__ = '<mas63 @t cornell d0t edu>'
__version__ = '0.7.3'
__license__ = 'BSD License'

import errno
import logging
import os
import os.path
import re
import shutil
import urlparse

import cPickle as pickle


log = logging.getLogger('vfl')

class VersionedFileLayoutException(Exception):
    pass

default_filename_format = '%(name)s-vfl%(rev)s%(ext)s'
default_filename_pattern = '(?P<name>.+)-vfl(?P<rev>\d+)(?P<ext>\..+)'

class VersionedFileLayout(object):
    def __init__(self, versioned_filename_format=default_filename_format,
                 versioned_filename_pattern=default_filename_pattern,
                 http_root=None, new_index_format=True,
                 version_by_mtime=False, fallback_to_mtime=False):
        self.versioned_filename_format = versioned_filename_format
        self.versioned_filename_pattern = versioned_filename_pattern
        self.http_root = http_root
        if self.http_root and self.http_root.endswith('/'):
            self.http_root = self.http_root[:-1]
        self.new_index_format = new_index_format
        self.version_by_mtime = version_by_mtime
        self.index_loaded = False
        self.version_url_map = {}
        self.last_mtime_indexed = None
        self.fallback_to_mtime = fallback_to_mtime
        
    def load_index(self, index_path):
        f = open(index_path, 'r')
        index = pickle.load(f)
        if 'vfl_map' in index:
            self.version_url_map = index['vfl_map']
            self.last_mtime_indexed = index['last_mtime_indexed']
        else:
            self.version_url_map = index
            self.last_mtime_indexed = index.get('last_mtime_indexed')
        f.close()
        self.index_loaded = True

    # try to return an absolute path to the versioned resource
    # if the lookup fails, fall through to the local resource so any cache
    # pulling through doesn't get confused
    def get_url(self, site_relative_path):
        try:
            url_path = self.version_url_map[site_relative_path]
            return '%s%s' % (self.http_root, url_path)
        except KeyError:
            return site_relative_path
    
    def build_versioned_tree(self, release_base_path, versioned_base_path,
                             index_path, max_revisions, exclude_list=None,
                             url_prefix=''):
        version_url_map, max_mtime, codependents = copy_versioned_tree(
            release_base_path, versioned_base_path,
            self.versioned_filename_format, exclude_list,
            self.last_mtime_indexed,
            extract_revision_map(self.version_url_map,
                                 self.versioned_filename_pattern),
            version_by_mtime=self.version_by_mtime,
            fallback_to_mtime=self.fallback_to_mtime)

        # log.debug('codependents: %s', codependents)
        version_url_map = self.compile_versioned_resources(
            release_base_path, versioned_base_path,
            codependents, version_url_map, url_prefix)

        if index_path:
            self.write_vfl_map(version_url_map, max_mtime, index_path)

        if max_revisions:
            prune_versioned_tree(versioned_base_path, max_revisions,
                                 self.versioned_filename_pattern)


    def compile_versioned_resources(self, release_base_path,
                                    versioned_base_path, codependents,
                                    version_url_map, url_prefix):
        version_url_map = version_url_map.copy()
        for relative_path, revision, ext in codependents:
            if ext == '.css':
                preprocessor = CSSPreprocessor(relative_path,
                                               release_base_path,
                                               version_url_map,
                                               url_prefix)
            elif ext == '.js':
                preprocessor = JSPreprocessor(relative_path,
                                              release_base_path,
                                              version_url_map,
                                              url_prefix)
            else:
                preprocessor = NullPreprocessor(relative_path,
                                                release_base_path,
                                                version_url_map,
                                                url_prefix)
                
            (data, new_revision) = preprocessor.run()
            if not data:
                continue

            relative_versioned_path = get_relative_versioned_path(
                relative_path, new_revision, self.versioned_filename_format)
            version_url_map[relative_path] = (relative_versioned_path,
                                              new_revision)
            versioned_path = get_absolute_path(versioned_base_path,
                                               relative_versioned_path)
            f = open(versioned_path, 'w')
            f.write(data)
            f.close()

        return version_url_map


    def write_vfl_map(self, version_url_map, max_mtime, map_path):
        vfl_map = {}
        for key, value in version_url_map.iteritems():
            try:
                (path, revision) = value
            except TypeError:
                continue
            vfl_map[key] = path
        f = open(map_path, 'w')
        if self.new_index_format:
            index = {
                'vfl_map': vfl_map,
                'last_mtime_indexed': max_mtime,
                }
        else:
            index = vfl_map
            index['last_mtime_indexed'] = max_mtime
        pickle.dump(index, f, pickle.HIGHEST_PROTOCOL)
        f.close()


class Preprocessor(object):
    explicit_dependency_pattern = re.compile('/\*\s*#include\s+(\S+)\s*\*/')

    def __init__(self, relative_path, release_base_path, version_url_map,
                 url_prefix=''):
        self.relative_path = relative_path
        if url_prefix and url_prefix.endswith('/'):
            url_prefix = url_prefix[:-1]
            
        self.url_prefix = url_prefix
        self.release_path = os.path.join(release_base_path, relative_path[1:])
        f = open(self.release_path)
        self.file_contents = f.read()
        f.close()
        self.version_url_map = version_url_map


    # get the max revision of the resource or any its subresources
    def get_revision(self, dependencies):
        parent_revision = self.version_url_map[self.relative_path][-1]
        try:
            revision = max([self.version_url_map[relative_path][-1]
                            for relative_path in dependencies])
            revision = max(revision, parent_revision)
        except ValueError:
            revision = parent_revision
            
        return revision

    def replace_urls(self):
        return self.dependency_pattern.sub(self.url_match_replacement,
                                           self.file_contents)

    def run(self):
        dependencies = self.get_dependencies()
        dependencies.extend(self.get_explicit_dependencies())
        # print 'dependencies:', self.relative_path, dependencies
        if dependencies:
            dependent_revision = self.get_revision(dependencies)
            #print "dependent_revision", self.release_path, dependent_revision
            preprocessed_content = self.replace_urls()
            return preprocessed_content, dependent_revision
        return (None, None)

    def get_explicit_dependencies(self):
        deps_path = get_dependency_path(self.release_path)
        try:
            f = open(deps_path)
        except IOError, e:
            if e[0] == errno.ENOENT:
                return []
            else:
                raise
        
        data = f.read()
        f.close()
        return [path
                for path in
                self.explicit_dependency_pattern.findall(data)
                if path in self.version_url_map]
        


class CSSPreprocessor(Preprocessor):
    dependency_pattern = re.compile('url\((\S+)\)')
        
    # compute a dependency 'tree' for a css file
    def get_dependencies(self):
        # TODO: handle css import statement
        return [path
                for path in
                self.dependency_pattern.findall(self.file_contents)
                if path in self.version_url_map]

    def url_match_replacement(self, match_obj):
        url = match_obj.group(1)
        try:
            versioned_url = 'url(%s%s)' % (self.url_prefix,
                                           self.version_url_map[url][0])
        except KeyError:
            versioned_url = match_obj.group(0)
        return versioned_url


class JSPreprocessor(Preprocessor):
    # a little more ambiguous than the css version as the syntax isn't
    # as well specified
    dependency_pattern = re.compile("([\'\"])(/\S+?\.\w{2,4})([\'\"])")

    # compute a dependency 'tree' for a css file
    def get_dependencies(self):
        return [path
                for start, path, end in
                self.dependency_pattern.findall(self.file_contents)
                if start == end and path in self.version_url_map]

    def url_match_replacement(self, match_obj):
        start_token, url, end_token = match_obj.groups()
        if start_token != end_token:
            return match_obj.group(0)
        try:
            versioned_url = '%s%s%s%s' % (start_token,
                                          self.url_prefix,
                                          self.version_url_map[url][0],
                                          end_token)
        except KeyError:
            versioned_url = match_obj.group(0)
        return versioned_url


class NullPreprocessor(Preprocessor):
	def get_dependencies(self):
		return []

	def replace_urls(self):
		return self.file_contents


def get_absolute_path(base_path, site_relative_path):
    # strip off the leading /
    # FIXME: not portable
    if site_relative_path.startswith('/'):
        site_relative_path = site_relative_path[1:]
    return os.path.join(base_path, site_relative_path)

def get_dependency_path(path):
    directory, filename = os.path.split(path)
    deps_file = '.%s.vfl' % filename
    return os.path.join(directory, deps_file)

def get_site_relative_path(site_root, path):
    return path.replace(os.path.abspath(site_root), '')

def format_dependency_comment(path):
    return '/* #include %s */' % path

def get_relative_versioned_path(relative_path, revision,
                            versioned_filename_format):
    dirname, filename = os.path.split(relative_path)
    name, ext = os.path.splitext(filename)
    sub_vars = {
        'name': name,
        'rev': revision,
        'ext': ext,
        }
    return os.path.join(dirname, versioned_filename_format % sub_vars)

def extract_revision_map(version_url_map, versioned_filename_pattern):
    version_url_map = version_url_map.copy()
    version_pattern = re.compile(versioned_filename_pattern)
    for path, versioned_path in version_url_map.items():
        try:
            versioned_filename = os.path.basename(versioned_path)
        except AttributeError, e:
            continue
        
        match = version_pattern.match(versioned_filename)
        if not match:
            continue
        version_url_map[path] = (versioned_path,
                                 int(match.group('rev')))

    return version_url_map

def prune_versioned_tree(versioned_base_path, max_revisions,
                         versioned_filename_pattern):
    if max_revisions < 1:
        raise VersionedFileLayoutException('max_revisions < 1')
    
    version_pattern = re.compile(versioned_filename_pattern)
    for (path, dir_list, file_list) in os.walk(versioned_base_path):
        versioned_file_map = {}
        for filename in file_list:
            match = version_pattern.match(filename)
            if not match:
                continue
            name = match.group('name')
            rev = int(match.group('rev'))
            ext = match.group('ext')

            normal_filename = '%s%s' % (name, ext)
            try:
                versioned_file_map[normal_filename].append((rev, filename))
            except KeyError:
                versioned_file_map[normal_filename] = [(rev, filename),]

        for filename, version_list in versioned_file_map.iteritems():
            version_list.sort(reverse=True)
            for version, version_file in version_list[max_revisions:]:
                remove_path = os.path.join(path, version_file)
                try:
                    os.unlink(remove_path)
                except OSError, e:
                    log.error('unable to unlink %s %s', remove_path, e)
                log.debug('rm %s %s', remove_path, version_list)

svn_client = None
# this is a very slow operation
def get_svn_revision(path):
    global svn_client
    import pysvn
    if svn_client is None:
        svn_client = pysvn.Client()
    try:
        svn_entry = svn_client.info(path)
    except pysvn.ClientError, e:
        log.error('error %s getting svn revision for %s', e, path)
        return None
    if svn_entry is None:
        return None
    else:
        return svn_entry.commit_revision.number

# create versioned mirror of release_base_path in versioned_base_path
# return dict mapping of path -> versions
def copy_versioned_tree(release_base_path, versioned_base_path,
                        versioned_filename_format, exclude_list=None,
                        last_mtime_indexed=None, last_vfl_map=None,
                        version_by_mtime=False, fallback_to_mtime=False):
    # note: i rationalize putting this here because this is a 'compile-time'
    # operation - the rest of the site should not need this package just to
    # read a url out of a dictionary
    if exclude_list is None:
        exclude_list = ['.svn',]

    # a list of (relative_path, version) tuples for files that might depend
    # on other versioned resources - this is just determined by file extension
    # right now. slightly ghetto.
    codependents = []
    codependent_file_extensions = ['.css', '.js']
    version_url_map = {}
    release_base_path = os.path.abspath(release_base_path)
    versioned_base_path = os.path.abspath(versioned_base_path)
    max_mtime = 0
    for (path, dir_list, file_list) in os.walk(release_base_path):
        for dirname in exclude_list:
            if dirname in dir_list:
                dir_list.remove(dirname)
        relative_dir = path[len(release_base_path):]
        if not relative_dir:
            relative_dir = '/'
            # print 'no relative_dir', path, filename
        versioned_dir = os.path.join(versioned_base_path, relative_dir[1:])
        if not os.path.isdir(versioned_dir):
            os.makedirs(versioned_dir)

        for filename in file_list:
            release_path = os.path.join(path, filename)
            relative_path = os.path.join(relative_dir, filename)
            name, ext = os.path.splitext(filename)
            if ext == '.vfl':
                # skip dependency files
                continue
            dependency_path = get_dependency_path(release_path)
            has_dependencies = os.path.exists(dependency_path)
            mtime = os.path.getmtime(release_path)
            max_mtime = max(max_mtime, mtime)
            if mtime <= last_mtime_indexed:
                needs_copying = False
                try:
                    revision = last_vfl_map[relative_path][-1]
                except (KeyError, IndexError), e:
                    log.warning("skipping %s: no cached entry", relative_path)
                    continue
            else:
                needs_copying = True
                if not version_by_mtime:
                    revision = get_svn_revision(release_path)
                else:
                    revision = int(mtime)
            if revision is None:
                if not has_dependencies and ext not in codependent_file_extensions:
                    if fallback_to_mtime:
                        revision = int(mtime)
                    else:
                        log.warning("skipping %s: no svn entry", release_path)
                        continue
                # if the file is dependent on something else, maybe we can
                # create an implied version number
                if not has_dependencies:
                    if fallback_to_mtime:
                        revision = int(mtime)
                    else:
                        log.warning("skipping %s: no dependency file %s",
                                    release_path, dependency_path)
                        continue
                    
            sub_vars = {
                'name': name,
                'rev': revision,
                'ext': ext,
                }
            versioned_name = versioned_filename_format % sub_vars

            # copy through the unversioned resource in case something doesn't
            # use the VFL naming scheme
            unversioned_path = os.path.join(versioned_dir, filename)
            versioned_path = os.path.join(versioned_dir, versioned_name)

            if needs_copying:
                log.debug('cp %s -> %s', release_path, unversioned_path)
                shutil.copy2(release_path, unversioned_path)
                # if we have explicit dependencies, we have to copy this on
                # the second pass - most of the other data that's incorrect
                # will be overwritten later
                if revision:
                    log.debug('cp %s -> %s', release_path, versioned_path)
                    shutil.copy2(release_path, versioned_path)

            relative_versioned_path = os.path.join(relative_dir,
                                                   versioned_name)
            version_url_map[relative_path] = (relative_versioned_path,
                                              revision)
            
            if has_dependencies or ext in codependent_file_extensions:
                codependents.append((relative_path, revision, ext))
    return version_url_map, max_mtime, codependents

