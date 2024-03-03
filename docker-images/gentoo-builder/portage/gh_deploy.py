#!/bin/env python3
import os
import socket
import re
import xml.etree.ElementTree as xml
from pathlib import Path
from github import Github, GithubException, UnknownObjectException, InputGitAuthor
import portage

class Block:
    def __init__(self, lines):
        self.lines = lines

    def get(self, key):
        entries = [x for x in self.lines if x.startswith(key + ":")]
        if len(entries) == 0:
            return None
        return entries[0].split(":", 2)[1].strip()

    def set(self, key, value):
        line = key + ": " + value
        entries = [i for i,x in enumerate(self.lines) if x.startswith(key + ":")]
        if len(entries) == 0:
            self.lines.append(line)
        else:
            for i in entries:
                self.lines[i] = line



class Manifest:
    def __init__(self, contents):
        lines = contents.split("\n")

        splits = [i for i,x in enumerate(lines) if x.strip() == ""]

        ci = 0
        self.blocks = []

        for i in splits:
            if i > ci:
                self.blocks.append(Block(lines[ci:i]))
            ci = i + 1

        if ci < len(lines):
            self.blocks.append(Block(lines[ci:len(lines)]))

    def update(self, manifest, package):
        self.blocks[0] = manifest.blocks[0]

        for block in manifest.blocks[1:]:
            if block.get("PATH") == package:
                for i, b in enumerate(self.blocks):
                    if b.get("PATH") == package:
                        self.blocks[i] = block
                        return
                self.blocks.append(block)
                return

    def build(self):
        self.blocks[0].set("PACKAGES", str(len(self.blocks) - 1))

        result = ""
        for block in self.blocks:
            if len(result) > 0:
                result = result + "\n"

            for line in block.lines:
                result = result + line + "\n"

        return result


class PkgConfig:
    def __init__(self):
        self.full_name = os.environ['PF']
        self.name = os.environ['PN']
        self.version = os.environ['PV']
        self.category = os.environ['CATEGORY']
        self.features = os.environ['PORTAGE_FEATURES']
        self.multi_instance = self.features.__contains__('binpkg-multi-instance')
        self.ebuild = os.environ['EBUILD']

        self.dbapi = portage.db[portage.root]["porttree"].dbapi

        pkgdir = os.environ['PKGDIR']

        self.manifest = 'Packages'
        self.manifest_path = pkgdir + '/' + self.manifest

        if self.multi_instance:
            self.file_ext = 'xpak'
            xpack_dir = self.category + '/' + self.name
            
            instances = [name for name in os.listdir(pkgdir + "/" + xpack_dir) if os.path.isfile(os.path.join(pkgdir + "/" + xpack_dir, name)) and name.startswith(self.full_name + '-')]
            build_ids = [int(name[len(self.full_name) + 1:len(name) - len(self.file_ext) - 1]) for name in instances]
            build_id = max(build_ids)
            self.file_name = self.full_name + '-' + str(build_id) + '.' + self.file_ext
            self.pkg_path = xpack_dir + '/' + self.file_name
        else:
            self.file_ext = 'tbz2'
            self.file_name = self.full_name + '.' + self.file_ext
            self.pkg_path = self.category + '/' + self.file_name

        self.file_path = pkgdir + '/' + self.pkg_path
    
    def category_description(self):
        category_metadata_path = Path(self.ebuild).parents[1] / 'metadata.xml'
        if not os.path.isfile(category_metadata_path):
            return 'custom category'
        
        root = xml.parse(category_metadata_path)
        long_description = root.findall('./longdescription[@lang="en"]')

        if len(long_description) > 0:
            long_description = long_description[0].text.strip()
            long_description = re.sub('^\\s*', '', long_description, flags=re.M)
            long_description = re.sub('\n', ' ', long_description, flags=re.M)
        return long_description


    def package_description(self):
        return self.dbapi.aux_get(self.category + "/" + self.full_name, ["DESCRIPTION"])[0]

    

class GitHubConfig:
    def __init__(self, cfg):
        self.repo_name = os.environ['GITHUB_REPO']
        self.token = os.environ['GITHUB_TOKEN']
        self.branch_prefix = 'binhost-'
        self.branch_name = self.branch_prefix + cfg.chost

        self.header_uri = "https://github.com/{}/release/download/{}".format(self.repo_name, self.branch_name)

        self.client = Github(self.token, timeout=280)
        self.repo = self.client.get_repo(self.repo_name)

        self.author = InputGitAuthor("binhost", "binhost" + '@' + socket.getfqdn())

    def ensure_barnch(self):
        try:
            try:
                return self.repo.get_branch(self.branch_name)
            except Exception:
                master_branch = self.repo.get_branch("master")
                return self.repo.create_git_ref(ref='refs/heads/' + self.branch_name, sha=master_branch.commit.sha)
        except Exception:
            print("Unable to ensure '%s' branch!" % gh_branch)
            exit(1)

    def ensure_release(self, pkg, branch):
        release_name = self.branch_name + "/" + pkg.category
        if pkg.multi_instance:
            release_name = release_name + "/" + pkg.name

        try:
            return self.repo.get_release(release_name)
        except Exception:
            description = pkg.package_description() if pkg.multi_instance else pkg.category_description()
            return self.repo.create_git_release(release_name, release_name, description, target_commitish=branch.commit.sha)

    def publish(self, pkg):
        branch = self.ensure_barnch()
        release = self.ensure_release(pkg, branch)

        updated = False

        for asset in release.get_assets():
            if asset.name == pkg.file_name:
                if pkg.multi_instance:
                    print("Package already published")
                    return
                updated = True
                asset.delete_asset()

        release.upload_asset(path=pkg.file_path, content_type='application/x-tar', name=pkg.file_name)
        print('Uploaded ' + pkg.file_name)

        try:
            commitMsg = pkg.category + "-" + pkg.version + (" updated" if updated else " added")
            manifest = ""
            with open(pkg.manifest_path, 'r') as file:
                manifest = file.read()

            def insert_uri(match):
                return match.group(1) + "URI: {}\n".format(self.header_uri) + match.group(2)

            manifest = re.sub(r'(PROFILE:.*\n)(TIMESTAMP:.*\n)', insert_uri, manifest)

            # receive git file/blob reference via git tree
            ref = self.repo.get_git_ref(f'heads/{self.branch_name}')
            tree = self.repo.get_git_tree(ref.object.sha).tree
            sha = [x.sha for x in tree if x.path == pkg.manifest]  # get file sha

            if not sha:
                self.repo.create_file(pkg.manifest, commitMsg, manifest, branch=self.branch_name, committer=self.author)
            else:
                old_manifest = Manifest(self.repo.get_contents(pkg.manifest, ref=self.branch_name).decoded_content.decode())
                new_manifest = Manifest(manifest)

                old_manifest.update(new_manifest, pkg.pkg_path)

                self.repo.update_file(pkg.manifest, commitMsg, old_manifest.build(), sha[0], branch=self.branch_name, committer=self.author)
        except Exception as e:
            #print('error handling Manifest under: ' + pkg.manifest_path + ' Error: ' + str(e))
            raise e
            #exit(1)
        print('Package index updated')

class Config:
    def __init__(self):
        self.chost = os.environ['CHOST']
        self.github = GitHubConfig(self)



cfg = Config()
pkg = PkgConfig()

cfg.github.publish(pkg)

exit(0)




gh_repo = os.environ['GITHUB_REPO']
gh_token = os.environ['GITHUB_TOKEN']
gh_branch = 'binhost-' + os.environ['CHOST'] # use chost as git branch name
gh_relName = gh_branch + '/' + os.environ['CATEGORY'] # create new github release for every category
gh_author = InputGitAuthor(os.environ['PORTAGE_BUILD_USER'], os.environ['PORTAGE_BUILD_USER'] + '@' + socket.getfqdn())
g_header_uri = "https://github.com/{}/releases/download/{}".format(gh_repo, gh_branch)

g_pkgName = os.environ['PF'] # create a new github asset for every package
g_pkgVersion = os.environ['PV']
g_cat = os.environ['CATEGORY']

# detect pkgdir layout
# https://wiki.gentoo.org/wiki/Binary_package_guide
g_pkgdirLayoutVersion = 2 if os.environ['PORTAGE_FEATURES'].__contains__('binpkg-multi-instance') else 1

g_xpakExt = 'tbz2' # XPAK extension (chanding compression scheme $BINPKG_COMPRESS does not change the extenstion)
g_xpak = os.environ['PF'] + '.' + g_xpakExt
g_xpakPath = os.environ['PKGDIR'] + '/' + g_cat + '/' + g_xpak
g_xpakStatus = ' added.'
g_manifest = 'Packages'
g_manifestPath = os.environ['PKGDIR'] + '/' + g_manifest

if g_pkgdirLayoutVersion == 2:
    g_xpakExt = 'xpak'
    g_xpakDir = os.environ['PKGDIR'] + '/' + g_cat + '/' + os.environ['PN']
    #g_buildID = str(len([name for name in os.listdir(g_xpakDir) if os.path.isfile(os.path.join(g_xpakDir,name)) and name.startswith(os.environ['PF'] + '-')]))
    f_name = os.environ['PF'] + "-"
    f_ext = ".xpak"
    g_buildID = str(max([0] + [int(name[len(f_name):len(name)-len(f_ext)]) for name in os.listdir(g_xpakDir) if os.path.isfile(os.path.join(g_xpakDir,name)) and name.startswith(f_name)]))
    g_xpak = os.environ['PF'] + '-' + g_buildID  + '.' + g_xpakExt
    g_xpakPath = os.environ['PKGDIR'] + '/' + g_cat + '/' + os.environ['PN'] + '/' + g_xpak
    # create new github release for every category
    g_cat = os.environ['CATEGORY']  + '/' + os.environ['PN']
    gh_relName = gh_branch + '/' + g_cat # create new github release for every category

# FIXME figure out how to dod this right, will fail on custom repos
def getXpakDesc():
    try:
        # this has to be relative to the ebuild in case of different repos
        # custom repos have no metadata.xml for base categories like sys-apps
        # if packages from these there merged before github release create we don't get the description
        g_catMetadataFile = Path(os.environ['EBUILD']).parents[1] / 'metadata.xml'
        root = xml.parse(g_catMetadataFile)
        g_catDesc = root.findall('./longdescription[@lang="en"]')

        if len(g_catDesc) > 0:
            g_catDesc = g_catDesc[0].text.strip()
            g_catDesc = re.sub('^\s*', '', g_catDesc, flags=re.M)  # strip leading spaces>
            g_catDesc = re.sub('\\n', ' ', g_catDesc, flags=re.M)  # convert to single lin>
    except:
        g_catDesc = 'custom category'

    return g_catDesc

def getEbuildDesc():
    """Get DESCRIPTION from ebuild"""
    try:
        g_catDesc = ''
        # read description fron ebuild
        ebuildPath = os.environ['EBUILD']
        with open(ebuildPath, 'r', encoding='utf-8') as ebuildFile:
            for line in ebuildFile:
                line = line.strip()
                try:
                    key, value = line.split('=', 1)
                except ValueError:
                    continue
                if key == 'DESCRIPTION':
                    g_catDesc = value
        # remove quotes at start and end
        g_catDesc = g_catDesc.strip('\"')
    except:
        g_catDesc = ''

    return g_catDesc

g = Github(gh_token, timeout = 280)
repo = g.get_repo(gh_repo)

# make sure we are working on an existent branch
try:
    branch = repo.get_branch(gh_branch)
except GithubException:
    print("branch not found!\nCreate git branch: '%s' first!" % gh_branch)
    exit(1)

# get release
try:
    rel = repo.get_release(gh_relName)
# create new release (gentoo category), read category description from gentoo metadata
except UnknownObjectException:
    if g_pkgdirLayoutVersion == 2:
        g_catDesc = getEbuildDesc()
    else:
        g_catDesc = getXpakDesc()

    rel = repo.create_git_release(gh_relName, g_cat, g_catDesc, target_commitish=gh_branch)

# upload packages as an gitlab asset
assets = rel.get_assets()
for asset in rel.get_assets():
    if asset.name == g_xpak:
        g_xpakStatus = ' updated.'
        asset.delete_asset()

asset = rel.upload_asset(path=g_xpakPath, content_type='application/x-tar', name=g_xpak)
print('GIT ' + g_xpak + ' upload')

# create/update Packages file
try:
    commitMsg = g_cat + "-" + g_pkgVersion + g_xpakStatus
    with open(g_manifestPath, 'r') as file:
        g_manifestFile = file.read()

    # check if we need to insert PORTAGE_BINHOST_HEADER_URI in Packages
    # the URI: entry will always between PROFILE: and TIMESTAMP:
    def insertURI(match):
       return match.group(1) + "URI: {}\n".format(g_header_uri) + match.group(2)
    g_manifestFile = re.sub(r'(PROFILE:.*\n)(TIMESTAMP:.*\n)', insertURI, g_manifestFile)

    # receive git file/blob reference via git tree
    ref = repo.get_git_ref(f'heads/{gh_branch}') # get branch ref
    tree = repo.get_git_tree(ref.object.sha).tree # get git tree
    sha = [x.sha for x in tree if x.path == g_manifest] # get file sha

    if not sha:
        # create new file (Packages)
        repo.create_file(g_manifest, commitMsg, g_manifestFile, branch=gh_branch, committer=gh_author)
    else:
        repo.update_file(g_manifest, commitMsg, g_manifestFile, sha[0], branch=gh_branch, committer=gh_author)
except Exception as e:
    print('error handling Manifest under: ' + g_manifestPath + ' Error: ' + str(e))
    exit(1)
print('GIT ' + g_manifest + ' commit')
