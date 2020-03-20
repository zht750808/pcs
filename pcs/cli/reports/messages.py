from typing import (
    Any,
    Dict,
    Mapping,
)

from pcs.common import file_type_codes
from pcs.common.str_tools import (
    format_list,
    format_optional,
    format_plural,
    transform,
)
from pcs.common.reports import (
    dto,
    item,
    messages,
)
from pcs.common.tools import get_all_subclasses


_file_role_to_option_translation: Mapping[file_type_codes.FileTypeCode, str] = {
    file_type_codes.BOOTH_CONFIG: "--booth-conf",
    file_type_codes.BOOTH_KEY: "--booth-key",
    file_type_codes.CIB: "-f",
    file_type_codes.COROSYNC_CONF: "--corosync_conf",
}


# TODO: prefix all internal functions with _
# TODO: file cleanup

class CliReportMessage:
    def __init__(self, dto_obj: dto.ReportItemMessageDto) -> None:
        self._dto_obj = dto_obj

    @property
    def code(self) -> str:
        return self._dto_obj.code

    @property
    def message(self) -> str:
        return self._dto_obj.message

    @property
    def payload(self) -> Mapping[str, Any]:
        return self._dto_obj.payload


class CliReportMessageCustom(CliReportMessage):
    # pylint: disable=no-member
    _obj: item.ReportItemMessage

    def __init__(self, dto_obj: dto.ReportItemMessageDto) -> None:
        super().__init__(dto_obj)
        self._obj = self.__class__.__annotations__.get("_obj")(  # type: ignore
            **dto_obj.payload
        )

    @property
    def message(self) -> str:
        raise NotImplementedError()


# class CorosyncLinkDoesNotExistCannotUpdate(CliReportMessageCustom):
#     _obj: messages.CorosyncLinkDoesNotExistCannotUpdate
#
#     @property
#     def message(self) -> str:
#         return f"{self._dto_obj.message}{self._obj.existing_link_list}"


class ResourceManagedNoMonitorEnabled(CliReportMessageCustom):
    _obj: messages.ResourceManagedNoMonitorEnabled

    @property
    def message(self) -> str:
        return (
            f"Resource '{self._obj.resource_id}' has no enabled monitor "
            "operations. Re-run with '--monitor' to enable them."
        )


class ResourceUnmoveUnbanPcmkExpiredNotSupported(CliReportMessageCustom):
    _obj: messages.ResourceUnmoveUnbanPcmkExpiredNotSupported

    @property
    def message(self) -> str:
        return "--expired not supported, please upgrade pacemaker"


class CannotUnmoveUnbanResourceMasterResourceNotPromotable(
    CliReportMessageCustom
):
    _obj: messages.CannotUnmoveUnbanResourceMasterResourceNotPromotable

    @property
    def message(self) -> str:
        return resource_move_ban_clear_master_resource_not_promotable(
            self._obj.promotable_id
        )


class InvalidCibContent(CliReportMessageCustom):
    _obj: messages.InvalidCibContent

    @property
    def message(self) -> str:
        return "invalid cib:\n{report}{more_verbose}".format(
            report=self._obj.report,
            more_verbose=format_optional(
                self._obj.can_be_more_verbose,
                "\n\nUse --full for more details.",
            ),
        )


class NodeCommunicationErrorNotAuthorized(CliReportMessageCustom):
    _obj: messages.NodeCommunicationErrorNotAuthorized

    @property
    def message(self) -> str:
        return (
            f"Unable to authenticate to {self._obj.node} ({self._obj.reason})"
            f", try running 'pcs host auth {self._obj.node}'"
        )


class NodeCommunicationErrorTimedOut(CliReportMessageCustom):
    _obj: messages.NodeCommunicationErrorTimedOut

    @property
    def message(self) -> str:
        return (
            f"{self._obj.node}: Connection timeout, try setting higher timeout "
            f"in --request-timeout option ({self._obj.reason})"
        )


class CannotBanResourceMasterResourceNotPromotable(CliReportMessageCustom):
    _obj: messages.CannotBanResourceMasterResourceNotPromotable

    @property
    def message(self) -> str:
        return resource_move_ban_clear_master_resource_not_promotable(
            self._obj.promotable_id
        )


class CannotMoveResourceMasterResourceNotPromotable(CliReportMessageCustom):
    _obj: messages.CannotMoveResourceMasterResourceNotPromotable

    @property
    def message(self) -> str:
        return resource_move_ban_clear_master_resource_not_promotable(
            self._obj.promotable_id
        )


class CannotMoveResourcePromotableNotMaster(CliReportMessageCustom):
    _obj: messages.CannotMoveResourcePromotableNotMaster

    @property
    def message(self) -> str:
        return (
            "to move promotable clone resources you must use --master and the "
            f"promotable clone id ({self._obj.promotable_id})"
        )


class SbdWatchdogTestMultipleDevices(CliReportMessageCustom):
    _obj: messages.SbdWatchdogTestMultipleDevices

    @property
    def message(self) -> str:
        return (
            "Multiple watchdog devices available, therefore, watchdog which "
            "should be tested has to be specified. To list available watchdog "
            "devices use command 'pcs stonith sbd watchdog list'"
        )


class NodeUsedAsTieBreaker(CliReportMessageCustom):
    _obj: messages.NodeUsedAsTieBreaker

    @property
    def message(self) -> str:
        return (
            f"Node '{self._obj.node}' with id '{self._obj.node_id}' is used as "
            "a tie breaker for a qdevice, run 'pcs quorum device update model "
            "tie_breaker=<node id>' to change it"
        )


class NodesToRemoveUnreachable(CliReportMessageCustom):
    _obj: messages.NodesToRemoveUnreachable

    @property
    def message(self) -> str:
        return (
            "Removed {node} {nodes} could not be reached and subsequently "
            "deconfigured. Run 'pcs cluster destroy' on the unreachable "
            "{node}."
        ).format(
            node=format_plural(self._obj.node_list, "node"),
            nodes=format_list(self._obj.node_list),
        )


class UnableToConnectToAllRemainingNode(CliReportMessageCustom):
    _obj: messages.UnableToConnectToAllRemainingNode

    @property
    def message(self) -> str:
        pluralize = lambda word: format_plural(self._obj.node_list, word)
        return (
            "Remaining cluster {node} {nodes} could not be reached, run "
            "'pcs cluster sync' on any currently online node once the "
            "unreachable {one} become available"
        ).format(
            node=pluralize("node"),
            nodes=format_list(self._obj.node_list),
            one=pluralize("one"),
        )


class CannotRemoveAllClusterNodes(CliReportMessageCustom):
    _obj: messages.CannotRemoveAllClusterNodes

    @property
    def message(self) -> str:
        return (
            "No nodes would be left in the cluster, if you intend to destroy "
            "the whole cluster, run 'pcs cluster destroy --all' instead"
        )


class WaitForNodeStartupWithoutStart(CliReportMessageCustom):
    _obj: messages.WaitForNodeStartupWithoutStart

    @property
    def message(self) -> str:
        return "Cannot specify '--wait' without specifying '--start'"


class HostNotFound(CliReportMessageCustom):
    _obj: messages.HostNotFound

    @property
    def message(self) -> str:
        pluralize = lambda word: format_plural(self._obj.host_list, word)
        return (
            (
                "{host} {hosts_comma} {_is} not known to pcs, try to "
                "authenticate the {host} using 'pcs host auth {hosts_space}' "
                "command"
            )
            .format(
                host=pluralize("host"),
                hosts_comma=format_list(self._obj.host_list),
                _is=pluralize("is"),
                hosts_space=" ".join(sorted(self._obj.host_list)),
            )
            .capitalize()
        )


class UseCommandNodeRemoveGuest(CliReportMessageCustom):
    _obj: messages.UseCommandNodeRemoveGuest

    @property
    def message(self) -> str:
        return (
            "this command is not sufficient for removing a guest node, use"
            " 'pcs cluster node remove-guest'"
        )


class UseCommandNodeAddGuest(CliReportMessageCustom):
    _obj: messages.UseCommandNodeAddGuest

    @property
    def message(self) -> str:
        return (
            "this command is not sufficient for creating a guest node, use"
            " 'pcs cluster node add-guest'"
        )


class UseCommandNodeAddRemote(CliReportMessageCustom):
    _obj: messages.UseCommandNodeAddRemote

    @property
    def message(self) -> str:
        return (
            "this command is not sufficient for creating a remote connection,"
            " use 'pcs cluster node add-remote'"
        )


class CorosyncNodeConflictCheckSkipped(CliReportMessageCustom):
    _obj: messages.CorosyncNodeConflictCheckSkipped

    @property
    def message(self) -> str:
        return (
            "Unable to check if there is a conflict with nodes set in corosync "
            "because {reason}"
        ).format(reason=skip_reason_to_string(self._obj.reason_type))


class LiveEnvironmentNotConsistent(CliReportMessageCustom):
    _obj: messages.LiveEnvironmentNotConsistent

    @property
    def message(self) -> str:
        return (
            "When {given} {_is} specified, {missing} must be specified as well"
        ).format(
            given=format_list(
                transform(
                    self._obj.mocked_files, _file_role_to_option_translation
                )
            ),
            _is=format_plural(self._obj.mocked_files, "is"),
            missing=format_list(
                transform(
                    self._obj.required_files, _file_role_to_option_translation
                )
            ),
        )


class LiveEnvironmentRequired(CliReportMessageCustom):
    _obj: messages.LiveEnvironmentRequired

    @property
    def message(self) -> str:
        return "This command does not support {forbidden_options}".format(
            forbidden_options=format_list(
                transform(
                    self._obj.forbidden_options,
                    _file_role_to_option_translation,
                )
            ),
        )


class LiveEnvironmentRequiredForLocalNode(CliReportMessageCustom):
    _obj: messages.LiveEnvironmentRequiredForLocalNode

    @property
    def message(self) -> str:
        return "Node(s) must be specified if -f is used"


class ServiceCommandsOnNodesSkipped(CliReportMessageCustom):
    _obj: messages.ServiceCommandsOnNodesSkipped

    @property
    def message(self) -> str:
        return (
            "Running action(s) {actions} on {nodes} was skipped because "
            "{reason}. Please, run the action(s) manually."
        ).format(
            actions=format_list(self._obj.action_list),
            nodes=format_list(self._obj.node_list),
            reason=skip_reason_to_string(self._obj.reason_type),
        )


class FilesRemoveFromNodesSkipped(CliReportMessageCustom):
    _obj: messages.FilesRemoveFromNodesSkipped

    @property
    def message(self) -> str:
        return (
            "Removing {files} from {nodes} was skipped because {reason}. "
            "Please, remove the file(s) manually."
        ).format(
            files=format_list(self._obj.file_list),
            nodes=format_list(self._obj.node_list),
            reason=skip_reason_to_string(self._obj.reason_type),
        )


class FilesDistributionSkipped(CliReportMessageCustom):
    _obj: messages.FilesDistributionSkipped

    @property
    def message(self) -> str:
        return (
            "Distribution of {files} to {nodes} was skipped because "
            "{reason}. Please, distribute the file(s) manually."
        ).format(
            files=format_list(self._obj.file_list),
            nodes=format_list(self._obj.node_list),
            reason=skip_reason_to_string(self._obj.reason_type),
        )


class WaitForIdleNotLiveCluster(CliReportMessageCustom):
    _obj: messages.WaitForIdleNotLiveCluster

    @property
    def message(self) -> str:
        return "Cannot use '-f' together with '--wait'"


def _create_report_msg_map() -> Dict[str, type]:
    result: Dict[str, type] = {}
    for report_msg_cls in get_all_subclasses(CliReportMessageCustom):
        # pylint: disable=protected-access
        code = report_msg_cls.__annotations__.get(
            "_obj", item.ReportItemMessage
        )._code
        if code:
            if code in result:
                raise AssertionError()
            result[code] = report_msg_cls
    return result


REPORT_MSG_MAP = _create_report_msg_map()


def report_item_msg_from_dto(obj: dto.ReportItemMessageDto) -> CliReportMessage:
    return REPORT_MSG_MAP.get(obj.code, CliReportMessage)(obj)


def resource_move_ban_clear_master_resource_not_promotable(
    promotable_id: str,
) -> str:
    return (
        "when specifying --master you must use the promotable clone id{_id}"
    ).format(_id=format_optional(promotable_id, " ({})"),)


def skip_reason_to_string(reason: messages.ReasonType) -> str:
    return {
        messages.NOT_LIVE_CIB: (
            "the command does not run on a live cluster (e.g. -f " "was used)"
        ),
        messages.UNREACHABLE: "pcs is unable to connect to the node(s)",
    }.get(reason, reason)
