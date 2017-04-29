# hg-subtree Extension

Author: [Dmitriy Morozov](http://mrzv.org)

Repository: https://bitbucket.org/mrzv/hg-subtree


## Overview

A typical software project has many dependencies. Because these are often
shared with other projects, they are version-controlled as their own standalone
repositories. But then how can we include these dependencies
into the main codebase? Some languages offer central package repositories
(e.g., Python's [PyPI](https://pypi.python.org/pypi)), which help with
dependency management, but in general (e.g., in C++), the problem is acute.

Mercurial provides one solution in its [Subrepository feature](https://www.mercurial-scm.org/wiki/Subrepository).
As the linked page suggests, it is considered a "feature of last resort."
In practice, it's tricky to use correctly, let alone effortlessly. The
hg-subtree extension offers an alternative solution. The contents of the
external project are pulled and merged directly into the main repository (with
possibly re-organized directory structure). Developers who pull the repository
don't need to know anything about this extension. Its main purpose is to
simplify updating the dependency by streamlining the pulling, moving, and
merging (and, optionally, collapsing).

Although the name is an homage to [git's subtree feature](https://www.atlassian.com/blog/git/alternatives-to-git-submodule-git-subtree),
it is a bit of a misnomer, since this extension does not require that
subrepository's contents live in a subtree of the main repository. The files
can be reorganized to go anywhere.

The hg-subtree extension provides the `subpull` command.

## Configuration

Enable the extension in your `.hgrc`. Additional options can be specified in
section `[subtree]`, with defaults shown below.

### .hgrc configuration

```
[extensions]
subtree = .../hg-subtree/hgsubtree

[subtree]
hgsubtree = .hgsubtree
bookmark = subtree@
move     = subtree: move {name}
merge    = subtree: update {name}
collapse = subtree: {name}@{rev}
```

## Setup

The hg-subtree extension reads configuration of subrepositories from
`.hgsubtree` file (the name is configurable in `.hgrc`). Each subrepository is
its own section. The two main options to set are `source` and `destination`:

 * `source` is any valid repository path; updates are pulled from there using
   `hg pull -f`.
 * `destination` specifies a sequence of commands to transform the
   contents of the subrepo into a form mergeable into the main repository. In
   the following example, everything is simply moved into `ext/sub` subdirectory.
   Currently, the following commands are supported: `mkdir`, `mv`, `cp`.
   Any file not touched by the directions in `destination` gets removed.

```
[sub]
source = ssh://.../path/to/sub
destination:
    mkdir ext/sub
    mv glob:** ext/sub
```

Optionally:
```
collapse = True
rev = master
keep = True
```

`collapse` is explained below. `rev` specifies which revision to pull.
`keep` specifies whether to keep (as opposed to the default remove)
the files untouched by the moves/copies during the repository re-organization
prescribed in `destination`.

## Usage

The extension provides only one command: `subpull`. By default, this command
goes through every subrepo specified in `.hgsubtree`. It pulls the subrepo's
contents, applies transformations prescribed by `destination`, commits those
transformations, and then merges the resulting commit with the parent of the
working directory.

For example, suppose we have unrelated repositories `main` and `sub`.

```
$ hg log -R main
@  1 Add .hgsubtree
|
o  0 Initial commit

$ hg log -R sub
@  0 Add a.txt

$ ls sub
a.txt
```

If `main` contains `.hgsubtree` as above, we can `subpull` from `main`:

```
$ cd main
$ hg subpull
...
$ hg log
@    4 subtree: update sub
|\
| o  3 subtree: move sub
| |
| o  2 Add a.txt
|
o  1 Add .hgsubtree
|
o  0 Initial commit

$ ls . ext/sub
.:
ext      main.txt

ext/sub:
a.txt
```

Now if we add another commit to `sub` (adding file `b.txt`):
```
$ hg log -R sub
@  1 Add b.txt
|
o  0 Add a.txt
```

And `subpull` from `main`:
```
$ hg subpull
...
$ hg log
@    7 subtree: update sub
|\
| o  6 subtree: move sub
|  \
|   o  5 Add b.txt
|   |
o   |  4 subtree: update sub
|\  |
| o |  3 subtree: move sub
|  \|
|   o  2 Add a.txt
|
o  1 Add .hgsubtree
|
o  0 Initial commit

$ ls . ext/sub
.:
ext      main.txt

ext/sub:
a.txt b.txt
```
We get the expected update.

It's possible to pass arguments to `subpull` to specify pulling from only one
of the subrepos in `.hgsubtree`, or to pull a specific revision (`-r`), or to
override `source` (`-s`), or to invoke editor on every commit to modify the
messages (`-e`).


### Collapse

An obvious downside of the above approach is that it could import a lot of history.
If the subrepository is your own project, and you plan to push changes back,
keeping the full history is a good idea. But if the project is an external
dependency, its history would mostly pollute your main repository. To address
this problem, it's possible to add `collapse = True` to any subrepository's
section in `.hgsubtree`. Doing so would collapse all the imported changesets
into one. In the previous example, we would get the same contents, but the
following history, after the first `subpull`:
```
@    4 subtree: update sub
|\
| o  3 subtree: move sub
| |
| o  2 subtree: sub@aded622672dd [subtree@sub]
|
o  1 Add .hgsubtree
|
o  0 Initial commit
```

And after the second `subpull`:
```
@    7 subtree: update sub
|\
| o  6 subtree: move sub
|  \
|   o  5 subtree: sub@85f971e8c898 [subtree@sub]
|   |
o   |  4 subtree: update sub
|\  |
| o |  3 subtree: move sub
|  \|
|   o  2 subtree: sub@aded622672dd
|
o  1 Add .hgsubtree
|
o  0 Initial commit
```

Notice that `subtree@sub` bookmark is used to keep track of which revision
corresponds to the subrepo. The bookmark prefix is configurable in `.hgrc`.
