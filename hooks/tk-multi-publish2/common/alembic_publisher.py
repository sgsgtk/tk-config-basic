# Copyright (c) 2017 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.
import sgtk
import os

HookBaseClass = sgtk.get_hook_baseclass()

from sgtk.util.filesystem import ensure_folder_exists, copy_file


class AlembicCachePublishPlugin(HookBaseClass):
    """
    Plugin for creating publishes for alembic files that exist on disk
    """

    @property
    def icon(self):
        """
        Path to an png icon on disk
        """
        return self.parent.get_icon_path("shotgun")

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Publish Alembic"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """
        return (
            "Publishes an alembic cache. This will create a versioned snapshot "
            "of the file in a <tt>publish</tt> folder in the same "
            "folder as the file. The associated version number will come from "
            "the parent item's publish version."
        )

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to recieve
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """
        return {
            "Publish Type": {
                "type": "shotgun_publish_type",
                "default": "Alembic Cache",
                "description": "SG publish type to associate publishes with."
            },
        }

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["cache.alembic"]

    def accept(self, log, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                        all.
            - required: If set to True, the publish task is required and cannot
                        be disabled.
            - enabled:  If True, the publish task will be enabled in the UI by
                        default.

        :param log: Logger to output feedback to.
        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        if "path" not in item.properties:
            log.error("Unknown file path for alembic cache.")
            return {"accepted": False}

        return {"accepted": True, "required": False, "enabled": True}

    def validate(self, log, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity. Use the logger to output further details
        around why validation has failed.

        :param log: Logger to output feedback to.
        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: True if item is valid, False otherwise.
        """

        return True

    def publish(self, log, settings, item):
        """
        Executes the publish logic for the given item and settings. Use the
        logger to give the user status updates.

        :param log: Logger to output feedback to.
        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        publisher = self.parent
        path = item.properties["path"]

        # extract the components of the alembic cache path
        file_info = publisher.util.get_file_path_components(path)

        # if the parent item has a publish folder, we'll copy the cache there
        # prior to publishing
        publish_folder = item.parent.properties.get("publish_folder")
        if publish_folder:

            # build a folder structure in the publish path that matches the
            # project root structure
            alembic_publish_folder = os.path.join(
                publish_folder,
                "cache",
                "alembic",
            )
            ensure_folder_exists(alembic_publish_folder)

            # full path to where we'll copy alembic cache to and publish from
            publish_path = os.path.join(
                alembic_publish_folder,
                file_info["filename"]
            )

            # copy the source to the publish folder
            log.info(
                "Copying to publish folder: %s" % (alembic_publish_folder,))
            copy_file(path, publish_path)

            # update the file info for the new publish path
            file_info = publisher.util.get_file_path_components(publish_path)
        else:
            # no parent. publish in place
            publish_path = path

        # this plugin may be running after a parent has already been published.
        # use the same publish version to build a simple association to the
        # parent on disk. if no publish version available, fall back to any
        # version discovered in the file name itself. otherwise, the version
        # number will not be set.
        publish_version = item.parent.properties.get("publish_version")
        if not publish_version:
            publish_version = file_info["version"]

        # get the publish id from the parent publish if possible
        parent_publish_id = \
            item.parent.properties.get("sg_publish_data", {}).get("id")

        # Create the TankPublishedFile entity in Shotgun
        args = {
            "tk": self.parent.sgtk,
            "context": item.context,
            "comment": item.description,
            "path": publish_path,
            "name": "%s.%s" % (file_info["prefix"], file_info["extension"]),
            "version_number": publish_version,
            "thumbnail_path": item.get_thumbnail_as_path(),
            "published_file_type": settings["Publish Type"].value,
            "dependency_ids": [parent_publish_id]
        }
        log.debug("Publishing: %s" % (args,))

        # create the publish and update this item's data
        item.properties["sg_publish_data"] = sgtk.util.register_publish(**args)

        # add publish version and publish version folder to the item properties.
        # child items can choose to also write to the same location and use the
        # same version to keep a tight association of files published together.
        item.properties["publish_version"] = publish_version
        item.properties["publish_folder"] = file_info["folder"]

    def finalize(self, log, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param log: Logger to output feedback to.
        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # remove the source path so that we don't publish it again next time.
        path = item.properties["path"]
        log.info("Deleting %s" % item.properties["path"])
        sgtk.util.filesystem.safe_delete_file(path)
