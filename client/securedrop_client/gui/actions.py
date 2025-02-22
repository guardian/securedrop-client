"""
The actions available to the journalist.

Over time, this module could become the interface between
the GUI and the controller.
"""

from collections.abc import Callable
from contextlib import ExitStack
from gettext import gettext as _
from pathlib import Path

from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QAction, QApplication, QDialog, QMenu

from securedrop_client import state
from securedrop_client.conversation import Transcript as ConversationTranscript
from securedrop_client.db import Source
from securedrop_client.export import Export, ExportDestination
from securedrop_client.gui.base import ModalDialog
from securedrop_client.gui.conversation import PrintDialog
from securedrop_client.gui.conversation.export import ExportWizard
from securedrop_client.gui.conversation.export.whistleflow_dialog import WhistleflowDialog
from securedrop_client.gui.shortcuts import Shortcuts
from securedrop_client.logic import Controller
from securedrop_client.utils import safe_mkdir

TRANSCRIPT_FILENAME = "transcript.txt"


class DownloadConversation(QAction):
    """Download all files and messages of the currently selected conversation."""

    def __init__(
        self, parent: QMenu, controller: Controller, app_state: state.State | None = None
    ) -> None:
        self._controller = controller
        self._state = app_state
        self._text = _("Download All")
        super().__init__(self._text, parent)
        self.setShortcut(Shortcuts.DOWNLOAD_CONVERSATION.value)
        self.triggered.connect(self.on_triggered)
        self.setShortcutVisibleInContextMenu(True)

        self._connect_enabled_to_conversation_changes()
        self._set_enabled_initial_value()

    @pyqtSlot()
    def on_triggered(self) -> None:
        if self._controller.api is None:
            self._controller.on_action_requiring_login()
        elif self._state is not None:
            id = self._state.selected_conversation
            if id is None:
                return
            self._controller.download_conversation(id)

    def _connect_enabled_to_conversation_changes(self) -> None:
        if self._state is not None:
            self._state.selected_conversation_files_changed.connect(
                self._on_selected_conversation_files_changed
            )

    @pyqtSlot()
    def _on_selected_conversation_files_changed(self) -> None:
        if self._state is None:
            return
        if self._state.selected_conversation_has_downloadable_files:
            self.setEnabled(True)
        else:
            self.setEnabled(False)

    def _set_enabled_initial_value(self) -> None:
        self._on_selected_conversation_files_changed()


class DeleteSourceAction(QAction):
    """Use this action to delete the source record."""

    def __init__(
        self,
        source: Source,
        parent: QMenu,
        controller: Controller,
        confirmation_dialog: Callable[[list[Source], int], QDialog],
    ) -> None:
        self.source = source
        self.controller = controller
        text = _("Delete Source Account")

        super().__init__(text, parent)

        # DeleteSource Dialog can accept more than one source (bulk delete),
        # but when triggered from this menu, only applies to one source
        self._confirmation_dialog = confirmation_dialog(
            [self.source],
            self.controller.get_source_count(),
        )
        self._confirmation_dialog.accepted.connect(
            lambda: self.controller.delete_sources([self.source])
        )
        self.triggered.connect(self.trigger)

    def trigger(self) -> None:
        if self.controller.api is None:
            self.controller.on_action_requiring_login()
        else:
            self._confirmation_dialog.exec()


class DeleteConversationAction(QAction):
    """Use this action to delete a source's submissions and replies."""

    def __init__(
        self,
        source: Source,
        parent: QMenu,
        controller: Controller,
        confirmation_dialog: Callable[[Source], QDialog],
        app_state: state.State | None = None,
    ) -> None:
        self.source = source
        self.controller = controller
        self._state = app_state
        text = _("Delete All Files and Messages")

        super().__init__(text, parent)

        # DeleteConversationDialog accepts only one source
        self._confirmation_dialog = confirmation_dialog(self.source)
        self._confirmation_dialog.accepted.connect(lambda: self._on_confirmation_dialog_accepted())
        self.triggered.connect(self.trigger)

    def trigger(self) -> None:
        if self.controller.api is None:
            self.controller.on_action_requiring_login()
        else:
            self._confirmation_dialog.exec()

    def _on_confirmation_dialog_accepted(self) -> None:
        if self._state is not None:
            id = self._state.selected_conversation
            if id is None:
                return
            self.controller.delete_conversation(self.source)
            self._state.remove_conversation_files(id)


class PrintConversationAction(QAction):  # pragma: nocover
    def __init__(
        self,
        parent: QMenu,
        controller: Controller,
        source: Source,
    ) -> None:
        """
        Allows printing of a conversation transcript.
        """
        text = _("Print Transcript")

        super().__init__(text, parent)

        self.controller = controller
        self._source = source

        self.triggered.connect(self._on_triggered)

    @pyqtSlot()
    def _on_triggered(self) -> None:
        """
        (Re-)generates the conversation transcript and opens a confirmation dialog to print it,
        in the manner of the existing PrintDialog.
        """
        file_path = (
            Path(self.controller.data_dir)
            .joinpath(self._source.journalist_filename)
            .joinpath(TRANSCRIPT_FILENAME)
        )

        transcript = ConversationTranscript(self._source)
        safe_mkdir(file_path.parent)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(str(transcript))
            # Let this context lapse to ensure the file contents
            # are written to disk.

        # Open the file to prevent it from being removed while
        # the archive is being created. Once the file object goes
        # out of scope, any pending file removal will be performed
        # by the operating system.
        with open(file_path) as f:
            export = Export()
            dialog = PrintDialog(export, TRANSCRIPT_FILENAME, [str(file_path)])
            dialog.exec()


class ExportConversationTranscriptAction(QAction):  # pragma: nocover
    def __init__(
        self,
        parent: QMenu,
        controller: Controller,
        source: Source,
        destination: ExportDestination | None = ExportDestination.USB,
    ) -> None:
        """
        Allows export of a conversation transcript.
        """
        text = (
            _("Export Transcript to USB")
            if destination == ExportDestination.USB
            else _("Export Transcript to Whistleflow View")
        )

        super().__init__(text, parent)

        self.controller = controller
        self._source = source
        self._destination = destination

        self.triggered.connect(self._on_triggered)

    @pyqtSlot()
    def _on_triggered(self) -> None:
        """
        (Re-)generates the conversation transcript and opens export wizard.
        """
        file_path = (
            Path(self.controller.data_dir)
            .joinpath(self._source.journalist_filename)
            .joinpath(TRANSCRIPT_FILENAME)
        )

        transcript = ConversationTranscript(self._source)
        safe_mkdir(file_path.parent)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(str(transcript))
            # Let this context lapse to ensure the file contents
            # are written to disk.

        # Open the file to prevent it from being removed while
        # the archive is being created. Once the file object goes
        # out of scope, any pending file removal will be performed
        # by the operating system.
        with open(file_path) as f:
            if self._destination == ExportDestination.USB:
                export_device = Export()
                wizard = ExportWizard(export_device, TRANSCRIPT_FILENAME, [str(file_path)])
                wizard.exec()
            else:
                whistleflow_dialog = WhistleflowDialog(
                    Export(),
                    "transcript.txt",
                    [str(file_path)],
                )
                whistleflow_dialog.exec()


class ExportConversationAction(QAction):  # pragma: nocover
    def __init__(
        self,
        parent: QMenu,
        controller: Controller,
        source: Source,
        app_state: state.State | None = None,
        destination: ExportDestination | None = ExportDestination.USB,
    ) -> None:
        """
        Allows export of a conversation transcript and all is files. Will download any file
        that wasn't already downloaded.
        """

        text = (
            _("Export All to USB")
            if destination == ExportDestination.USB
            else _("Export All to Whistleflow View")
        )

        super().__init__(text, parent)

        self.controller = controller
        self._source = source
        self._state = app_state
        self._destination = destination

        self.triggered.connect(self._on_triggered)

    @pyqtSlot()
    def _on_triggered(self) -> None:
        """
        (Re-)generates the conversation transcript and opens export wizard to export it
        alongside all the (attached) files that are downloaded.
        """
        if self._state is not None:
            id = self._state.selected_conversation
            if id is None:
                return
            if self._state.selected_conversation_has_downloadable_files:
                dialog = ModalDialog(show_header=False)
                message = _(
                    "<h2>Some files will not be exported</h2>"
                    "Some files from this source have not yet been downloaded, and will not be exported."  # noqa: E501
                    "<br /><br />"
                    'To export the currently downloaded files, click "Continue."'
                )
                dialog.body.setText(message)
                dialog.rejected.connect(self._on_confirmation_dialog_rejected)
                dialog.accepted.connect(self._on_confirmation_dialog_accepted)
                dialog.continue_button.setFocus()
                dialog.exec()
            else:
                self._prepare_to_export()

    def _prepare_to_export(self) -> None:
        """
        (Re-)generates the conversation transcript and opens a confirmation dialog to export it
        alongside all the (attached) files that are downloaded, in the manner
        of the existing ExportWizard.
        """
        transcript_location = (
            Path(self.controller.data_dir)
            .joinpath(self._source.journalist_filename)
            .joinpath(TRANSCRIPT_FILENAME)
        )

        transcript = ConversationTranscript(self._source)
        safe_mkdir(transcript_location.parent)

        with open(transcript_location, "w", encoding="utf-8") as f:
            f.write(str(transcript))
            # Let this context lapse to ensure the file contents
            # are written to disk.

        downloaded_file_locations = [
            file.location(self.controller.data_dir)
            for file in self._source.files
            if self.controller.downloaded_file_exists(file, silence_errors=True)
        ]

        file_locations = downloaded_file_locations + [transcript_location]

        # Open the files to prevent them from being removed while
        # the archive is being created. Once the file objects go
        # out of scope, any pending file removal will be performed
        # by the operating system.
        with ExitStack() as stack:
            export_device = Export()
            files = [stack.enter_context(open(file_location)) for file_location in file_locations]

            file_count = len(files)
            if file_count == 1:
                summary = TRANSCRIPT_FILENAME
            else:
                summary = _("all files and transcript")

            if self._destination == ExportDestination.WHISTLEFLOW:
                whistleflow_dialog = WhistleflowDialog(
                    export_device,
                    summary,
                    [str(file_location) for file_location in file_locations],
                )
                whistleflow_dialog.exec()
            else:
                wizard = ExportWizard(
                    export_device,
                    summary,
                    [str(file_location) for file_location in file_locations],
                    QApplication.activeWindow(),
                )
                wizard.exec()

    def _on_confirmation_dialog_accepted(self) -> None:
        self._prepare_to_export()

    def _on_confirmation_dialog_rejected(self) -> None:
        pass
