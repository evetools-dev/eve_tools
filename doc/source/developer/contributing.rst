Contributing to eve_tools
=========================

Where to start?
---------------

All contributions are welcome. This project needs your help to become more useful for EVE players. 
It's not just bug reports and bug fixes that matter. You are welcome to bring your ideas to discussions or even comment on my coding style.

If you simply want to help with this project, that's great! `GitHub "issues" tab <https://github.com/evetools-dev/eve_tools/issues>`_ might have something interesting for you.
If you have some brilliant ideas for this project, also mention it on `"issues" page <https://github.com/evetools-dev/eve_tools/issues>`_.

When you start working on an issue, remember to assign the issue to yourself. You can simply leave a comment letting others know you are working on the issue.
If you find any exciting issues, you can return to this guide to set up the development environment. 

Feel free to ask me questions via `email <hb.evetools@gmail.com>`_, or contact me in-game with character ``Hanbie Serine``.


Working with the code
---------------------

The code is hosted on `github <https://github.com/evetools-dev/eve_tools/tree/master>`_. We use `Git <https://git-scm.com/>`_ for version control to allow more people contributing together to the project.

Some great resources for starting with git:

* the `GitHub help pages <https://docs.github.com/en>`_
* the `Pandas documentation <https://pandas.pydata.org/docs/development/contributing.html>`_
* the `NumPy documentation <https://numpy.org/doc/stable/dev/index.html>`_

The rest of this document helps you get onboard with Git, basically you would have a working Python environment to start your contributions.

.. note::
    All contributions should be made to :red:`develop` branch only. ``master`` branch is only used for release.

Forking
^^^^^^^

You will need to work on your copy of codebase, and not directly editing eve_tools repo. 
Go to `eve_tools repo <https://github.com/evetools-dev/eve_tools/tree/develop>`_ and hit ``Fork`` button on the top-right.

.. note::
    Please check that you are forking from :red:`DEVELOP` branch instead of master branch.
    
Give your fork a good name!


Clone
^^^^^

Once you have a copy of eve_tools code, you would need to get this copy to your local machine, called clone::

    git clone https://github.com/your-user-name/eve_tools.git eve_tools-yourname
    cd eve_tools-yourname
    git remote add upstream https://github.com/evetools-dev/eve_tools.git

You can obtain the link after ``git clone`` from your repo, by clicking the green ``Code`` button and under option ``HTTPS``. 

``upstream`` is a remote branch that reflects current progress on eve_tools project. 


Creating a branch
^^^^^^^^^^^^^^^^^
.. note::
    Fork and clone are only needed ones. For each new feature, such as fixing bugs or adding new features, you need to do the following.

You might have multiple ideas in mind, each having distinct changes to the project. A feature branch is where you make changes to the codebase, which better defines your changes and keeps your master or develop branch clean.

Before creating a feature branch, pull the latest changes from upstream::
    git checkout develop
    git pull upstream develop

Then create the feature branch, with a useful name as it will be seen by all developers::
    git checkout -b fix-api-search

This changes your current working directory to ``fix-api-search`` branch. Keep all changes specific for this branch. If you have some new ideas, create a new branch for it.
You can use ``git checkout`` to switch between branches.

.. note::
    From here, you can start writing code!


Commit your code
^^^^^^^^^^^^^^^^

Once you have made some changes to the codebase, commit your changes to your local repository with an INFORMATIVE message. Here are some common prefixes for commit message:

* Add: new features, improved functionalities
* Fix: bug fixes
* Doc: additions/updates to documentation
* Clean: code clean up

The following format is preferred:

* A subject line with ``< 80`` characters
* One blank line
* Optionally, a commit message body

Commit message ``body`` is the place to write lines of explanation on your changes. Here is an example::

    Add search id api.

    Add search for structure_id, character_id, etc., converting from a name
    in game to an id that could be used for other API calls. E.g. convert
    character name "ABC BCD" to its character_id "123456". Finding these ids
    could be intimidating for first-time ESI users, so this functionality is
    provided. This commit also acts as an example of how to use ESIClient to
    generate useful EVE data.

    - Add character_id search
    - Add structure_id search with authenticated endpoint
    - (use "-" to list your changes in a clear manner)

(omit these colors on the text)

You should find it straightforward to write a useful commit message, for example "Add post requests to esi request family". 
If you find yourself writing too much for commit message, such as "Add post requests to esi and fix api search", you probably need to split changes to seperate commits.

To commit, first track changes in your code. In VS Code, this is simply clicking the ``+`` button on the ``Source Control`` menu. Alternatively, you can manually ask Git to track changes::

    git add path/to/file-to-be-added.py

You can also find some useful info with ``git status``::

    git status
    # On branch fix-api-search
    #
    #       modified:   /relative/path/to/file-you-added.py
    #   

After adding/tracking all changes you want for a commit, go to a command line and::

    git commit

This will prompt an editor (by default Vim), where you can use it to format your commit message and body. Some operations for Vim:

* Insert (start writing): ``i`` key
* Finish writing: first press ``ESC``, then write ``:wq``, then hit ``enter``
* Quit without saving: first press ``ESC``, then write ``:q!``, press ``enter``

You could use another editor for git commit (I use Vim and it's great)::
    git config --global core.editor "nano"


Push your code
^^^^^^^^^^^^^^

When you have accumulated lots of commits, or you simply want to view commits on GitHub, push your feature branch::

    git push origin fix-api-search (whatever your branch name)

Now your code is on GitHub, and you can view them and show off to friends. But it's not yet a part of eve_tools project. A ``Pull Request`` needs to be submitted on GitHub to us.


Finally, Pull Request!
^^^^^^^^^^^^^^^^^^^^^^

A pull request (PR) is how code from your fork becomes available and merged to the main eve_tools codebase. To submit a PR:

1. Navigate to your repository
2. Choose the branch you want to be merged
3. Click on the ``Contribute`` drop-down button, then ``Open pull request``
4. You can then click on ``Commits`` and ``Files Changed`` to check if everything is what you expected
5. Write an informative title for this PR
6. Check the checklist ([x] to check), or leave it empty
7. Click ``Create pull request``

This request then goes to us, and we will review the code.

.. note::
    From here, you can sit back and relax. If spot some errors, or want to add more to this PR, follow the next steps


Update your PR
^^^^^^^^^^^^^^

Based on the review, you might need to make some changes to the code. In this case, you can make changes on your local branch (same branch in PR), push to GitHub, and the PR will be automatically updated.

If there is a merge conflict, you need to resolve them locally::

    git checkout (your local branch)
    git fetch upstream
    git merge upstream/develop

See how to resolve merge conflict at `GitHub doc <https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/addressing-merge-conflicts/resolving-a-merge-conflict-using-the-command-line>`_.
Once the conflicts are resolved and merged, you can use ``git commit`` to save these changes, and push to GitHub (and PR automatically)::

    git push origin (your branch name)


From here, you can really sit back and relax. If your contribution is merged, don't hesitate to ask for some isk via `email <hb.evetools@gmail.com>`_.