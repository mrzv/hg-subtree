# Author: Dmitriy Morozov <dmitriy@mrzv.org>, 2017

"""Subtree repository management for Mercurial."""

from mercurial import hg, util, commands, cmdutil, error
from mercurial.i18n import _
from hgext     import strip

import os, ConfigParser
from fnmatch     import fnmatch
from collections import defaultdict

# configurable via subtree/hgsubtree in hgrc
default_hgsubtree        = '.hgsubtree'
default_bookmark_prefix  = 'subtree@'
default_move_comment     = 'subtree: move {name}'
default_merge_comment    = 'subtree: update {name}'
default_collapse_comment = 'subtree: {name}@{rev}'

cmdtable = {}
command = cmdutil.command(cmdtable)

@command('subpull|sp', [('e', 'edit',     False,  'invoke editor on commit messages'),
                        ('s', 'source',   '',     'use this source instead of the one specified in the config'),
                        ('r', 'rev',      '',     'use this revision instead of the one specified in the config'),
                        ('',  'no-strip', False,  "don't strip upstream repo after collapse")],
         _('hg subpull [OPTIONS]'))
def subpull(ui, repo, name = '', **opts):
    """Pull subtree(s)"""

    # change to root directory
    if repo.getcwd() != '':
        ui.warn("Working directory is not repository root. At best, this directory won't exist when subpull is done.\n")
        repo.dirstate._cwd = repo.root
        os.chdir(repo.root)

    # if there are uncommitted change, abort --- we will be modifying the working copy quite drammatically
    modified, added, removed, deleted, _unknown, _ignored, _clean = repo.status()
    if modified or added or removed or deleted:
        raise error.Abort("Uncommitted changes in the working copy. Subtree extension needs to modify the working copy, so it cannot proceed.")

    # parse .hgsubtree
    hgsubtree = ui.config('subtree', 'hgsubtree', default = default_hgsubtree)
    subtrees = _parse_hgsubtree(os.path.join(repo.root, hgsubtree))

    # if names not in .hgsubtree, abort
    # if names is empty, go through all repos in .hgsubtree
    if name:
        if name not in subtrees:
            raise error.Abort("Cannot find %s in %s." % (name, hgsubtree))
        names = [name]
    else:
        if opts['source']:
            raise error.Abort("Cannot use --source without specifying a repository")
        names = subtrees.keys()

    origin = str(repo[None])
    commit_opts = { 'edit': opts['edit'] }
    bookmark_prefix = ui.config('subtree', 'bookmark', default = default_bookmark_prefix)

    for name in names:
        subtree = subtrees[name]
        if 'destination' not in subtree:
            raise error.Abort('No destination found for %s' % name)

        collapse = 'collapse' in subtree and subtree['collapse']

        # pull and update -C
        pull_opts = {}
        if 'rev' in subtree:
            pull_opts['rev'] = [subtree['rev']]
        if opts['rev']:
            pull_opts['rev'] = opts['rev']
        tip = repo['tip']
        commands.pull(ui, repo, source = subtree['source'] if not opts['source'] else opts['source'],
                                force = True, **pull_opts)
        if tip == repo['tip']:
            ui.status("no changes: nothing for subtree to do\n")
            continue

        if collapse:
            # find a matching bookmark
            bookmark_name = bookmark_prefix + name
            if bookmark_name in repo._bookmarks:
                commands.update(ui, repo, bookmark_name, clean = True)
            else:
                commands.update(ui, repo, 'null', clean = True)

            # set up the correct file state and commit as a new changeset
            pulled_tip = repo['tip']
            commands.revert(ui, repo, rev = 'tip', all = True)
            hgsubrepo_meta = [os.path.join(repo.root, '.hgsubstate'),
                              os.path.join(repo.root, '.hgsub')]
            for fn in hgsubrepo_meta:
                if os.path.exists(fn):
                    ui.debug("removing %s\n" % fn)
                    commands.remove(ui, repo, fn, force = True)
                    os.remove(fn)
            changed = commands.commit(ui, repo,
                                      message=ui.config('subtree', 'collapse', default_collapse_comment).format(name=name, rev=str(pulled_tip)[:12]),
                                      **commit_opts)
            commands.bookmark(ui, repo, bookmark_name, inactive=True)

            if not opts['no_strip']:
                # delete bookmarks on the changesets that will be stripped; not
                # the most efficient procedure to find them, but will do for now
                remove_bookmarks = []
                for k in repo._bookmarks.keys():
                    ctx = repo[k]
                    if pulled_tip.ancestor(ctx) == ctx:
                        remove_bookmarks.append(k)

                for bookmark in remove_bookmarks:
                    commands.bookmark(ui, repo, bookmark, delete = True)

                strip.stripcmd(ui, repo, rev = ['ancestors(%s)' % str(pulled_tip)], bookmark = [])

            if changed == 1:    # nothing changed
                ui.status("no changes: nothing for subtree to do\n")
                commands.update(ui, repo, origin[:12])
                continue
        else:
            commands.update(ui, repo, 'tip', clean = True)

        # move or delete
        destinations = _destinations(subtree['destination'])

        # process destinations
        for dest in destinations:
            if dest[0] == 'mkdir':
                if not os.path.exists(dest[1]):
                    os.makedirs(dest[1])
            elif dest[0] == 'mv':
                commands.rename(ui, repo, *dest[1:], force = False)
            elif dest[0] == 'cp':
                commands.copy(ui, repo, *dest[1:], force = False)

        # remove all untouched files, unless instructed to keep them
        if 'keep' not in subtree or not subtree['keep']:
            _modified, _added, _removed, _deleted, _unknown, _ignored, clean = repo.status(clean = True)
            for fn in clean:
                commands.remove(ui, repo, fn)

        commands.commit(ui, repo,
                        message=ui.config('subtree', 'move', default_move_comment).format(name=name),
                        **commit_opts)
        merge_commit = str(repo[None])

        # update to original and merge with the new
        commands.update(ui, repo, origin[:12])
        commands.merge(ui, repo, merge_commit[:12])
        commands.commit(ui, repo,
                        message=ui.config('subtree', 'merge', default_merge_comment).format(name=name),
                        **commit_opts)
        origin = str(repo[None])

def _parse_hgsubtree(fn):
    config = ConfigParser.SafeConfigParser()
    config.read(fn)

    result = {}
    for s in config.sections():
        result[s] = dict(config.items(s))

    return result

def _destinations(s):
    res = []
    for x in s.split('\n'):
        x = x.strip()
        if len(x) == 0: continue
        res.append([y.strip() for y in x.split(' ')])
    return res
