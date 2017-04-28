# Author: Dmitriy Morozov <dmitriy@mrzv.org>, 2017

"""Subtree repository management for Mercurial."""

from mercurial import hg, util, commands, cmdutil, error
from mercurial.i18n import _

import os, ConfigParser

# configurable via subtree/hgsubtree in hgrc
default_hgsubtree       = '.hgsubtree'
default_move_comment    = 'subtree: move {name} to {destination}'
default_merge_comment   = 'subtree: update {name}'

cmdtable = {}
command = cmdutil.command(cmdtable)

@command('subpull|sp', [('e', 'edit', False, 'invoke editor on commit messages'),
                        ('r', 'rev',  '',    'use this revision instead of the one specified in the config')],
         _('hg subpull [OPTIONS]'))
def subpull(ui, repo, name = '', **opts):
    """Pull subtree(s)"""

    # if there are uncommitted change, abort --- we will be modifying the working copy quite drammatically
    # TODO: need to make sure repo.status() runs in the root directory, not in the current working dir
    modified, added, removed, deleted, _unknown, _ignored, _clean = repo.status()
    if modified or added or removed or deleted:
        raise error.Abort("Uncommitted changes in the working copy. Subtree extension needs to modify the working copy, so it cannot proceed.")

    # parse .hgsubtree
    hgsubtree = ui.config('subtree', 'hgsubtree', default = default_hgsubtree)
    subtrees = _parse_hgsubtree(os.path.join(repo.root, hgsubtree))
    print(subtrees)

    # if names not in .hgsubtree, abort
    # if names is empty, go through all repos in .hgsubtree
    if name:
        if name not in subtrees:
            raise error.Abort("Cannot find %s in %s." % (name, hgsubtree))
        names = [name]
    else:
        names = subtrees.keys()

    origin = str(repo[None])
    commit_opts = { 'edit': opts['edit'] }

    for name in names:
        subtree = subtrees[name]
        if 'destination' not in subtree:
            raise error.Abort('No destination found for %s' % name)

        # pull and update -C
        pull_opts = {}
        if 'rev' in subtree:
            pull_opts['rev'] = [subtree['rev']]
        if opts['rev']:
            pull_opts['rev'] = opts['rev']
        tip = repo['tip']
        commands.pull(ui, repo, source = subtree['source'], force = True, **pull_opts)
        if tip == repo['tip']:
            ui.status("No changes, nothing for subtree to do")
            continue
        commands.update(ui, repo, 'tip', clean = True)

        # mkdir + rename
        destination = subtree['destination']
        if not os.path.exists(destination):
            os.makedirs(destination)
        manifest = [x for x in repo[None].manifest()]
        manifest.append(destination)
        commands.rename(ui, repo, *manifest, force = False)
        commands.commit(ui, repo,
                        message=ui.config('subtree', 'move', default_move_comment).format(name=name, destination=destination),
                        **commit_opts)
        merge_commit = str(repo[None])

        # update to original and merge with the new
        commands.update(ui, repo, origin[:12])
        commands.merge(ui, repo, merge_commit[:12])
        commands.commit(ui, repo,
                        message=ui.config('subtree', 'merge', default_merge_comment).format(name=name),
                        **commit_opts)
        origin = repo[None]

def _parse_hgsubtree(fn):
    config = ConfigParser.SafeConfigParser()
    config.read(fn)

    result = {}
    for s in config.sections():
        result[s] = dict(config.items(s))

    return result
