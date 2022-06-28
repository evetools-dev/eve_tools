import os
import json

from dataclasses import dataclass, asdict

from eve_tools.config import APP_PATH


@dataclass
class Application:
    """Hold info for an Application.

    clientId is the primary key for each Application.
    Application has a save() function, which is useful for storing single Application.
    If multiple Application(s) need to be stored, append to ESIApplications and use its save().

    Attributes:
        clientId: str
            A str acting as a unique key for an Application, created and retrieved from ESI developer site:
            https://developers.eveonline.com/

        scope: str
            A comma seperated str, usually copied from ESI developer site,
            in the format "esi...v1 esi...v1 esi...v1"
        callbackURL: str
            A str of URL that the authentication will redirect to.
            Default and recommend using: https://localhost/callback/

    Example usage:
        >>> # 1. Navigate and log in to https://developers.eveonline.com/.
        >>> # 2. Click "Manage Applications" in the center.
        >>> # 3. Click "Create a new Application" or "View Application".
        >>> # 4. After creating an application or viewing an application,
        >>> #   copy the "Client ID", "Callback URL", and click "Copy Scopes to Clipboard".
        >>> #   Do not reveal "Secret Key" field.
        >>> clientId = {"Client ID" field copied}
        >>> scope = {Pasted content after clicking "Copy Scopes to Clipboard"}
        >>> callbackURL = {"Callback URL" field copied}
        >>> app = Application(clientId, scope, callbackURL)
        >>> # Now you can save() or append to ESIApplications
        >>> app.save()  # save to local file immediately
    """

    clientId: str
    scope: str
    callbackURL: str = "https://localhost/callback/"

    def save(self) -> None:
        """Save current Application to local file.

        If local file already has an Application with the same clientId,
        scope and callbackURL fields will be updated.

        One read and one write per call. Recommend using ESIApplications.save()
        """
        if os.path.exists(APP_PATH) and os.stat(APP_PATH).st_size:
            with open(APP_PATH, "r") as all_apps_fp:
                all_apps = json.load(all_apps_fp)

            old_app = None
            for app_ in all_apps:
                if app_["clientId"] == self.clientId:
                    old_app = app_

            if old_app:
                old_app["callbackURL"] = self.callbackURL
                old_app["scope"] = self.scope
            else:
                all_apps.append(asdict(self))
        else:
            all_apps = [asdict(self)]

        with open(APP_PATH, "w") as all_apps_fp:
            json.dump(all_apps, all_apps_fp)


class ESIApplications(object):
    """Hold all Application(s) available.

    Load load application.json file and parse into a list of Application.
    New Application can be appended like list append.
    """

    def __init__(self) -> None:
        self.apps = []

        self._load_apps()

    def search_scope(self, scope: str) -> Application:
        """Find the first Application with scope.

        Args:
            scope: A str of a single scope. Multiple scope search will yield no Application.

        Returns:
            An Application with the given scope.

        Raises:
            ValueError: No application with scope found.
        """
        for app_ in self.apps:
            scopes = app_.scope.split(" ")
            if scope in scopes:
                return app_

        raise ValueError(
            f"No Application with {scope} found. Create one and save using Application class."
        )

    def append(self, app: Application) -> None:
        """Append an Application to the ESIApplications instance.

        Args:
            app: An Application. Fields are not checked when append.
        """
        self.apps.append(app)

    def save(self) -> None:
        """Save all Application(s) to a local file.

        Unpack all Application and store them to local application.json file.
        Old file is truncated because the ESIApplications instance is initiated with all Application in the file.
        """
        if not self.apps:
            return

        app_list = [asdict(app_) for app_ in self.apps]
        with open(APP_PATH, "w") as all_apps_fp:
            json.dump(app_list, all_apps_fp)

    def _load_apps(self) -> None:
        if not os.path.exists(APP_PATH) or not os.stat(APP_PATH).st_size:
            return

        with open(APP_PATH, "r") as all_apps_fp:
            all_apps = json.load(all_apps_fp)

        for app_ in all_apps:
            self.apps.append(Application(**app_))  # dict unpacking
