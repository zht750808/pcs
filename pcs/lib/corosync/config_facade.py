from __future__ import (
    absolute_import,
    division,
    print_function,
    unicode_literals,
)

from pcs.common import report_codes
from pcs.lib.errors import ReportItem, LibraryError
from pcs.lib.corosync import config_parser
from pcs.lib.node import NodeAddresses, NodeAddressesList

class ConfigFacade(object):
    """
    Provides high level access to a corosync config file
    """

    QUORUM_OPTIONS = (
        "auto_tie_breaker",
        "last_man_standing",
        "last_man_standing_window",
        "wait_for_all",
    )

    @classmethod
    def from_string(cls, config_string):
        """
        Parse corosync config and create a facade around it
        config_string corosync config text
        """
        try:
            return cls(config_parser.parse_string(config_string))
        except config_parser.MissingClosingBraceException:
            raise LibraryError(ReportItem.error(
                report_codes.PARSE_ERROR_COROSYNC_CONF_MISSING_CLOSING_BRACE,
                "Unable to parse corosync config: missing closing brace"
            ))
        except config_parser.UnexpectedClosingBraceException:
            raise LibraryError(ReportItem.error(
                report_codes.PARSE_ERROR_COROSYNC_CONF_UNEXPECTED_CLOSING_BRACE,
                "Unable to parse corosync config: unexpected closing brace"
            ))
        except config_parser.CorosyncConfParserException:
            raise LibraryError(ReportItem.error(
                report_codes.PARSE_ERROR_COROSYNC_CONF,
                "Unable to parse corosync config"
            ))

    def __init__(self, parsed_config):
        """
        Create a facade around a parsed corosync config file
        parsed_config parsed corosync config
        """
        self._config = parsed_config

    @property
    def config(self):
        return self._config

    def get_nodes(self):
        """
        Get all defined nodes
        """
        result = NodeAddressesList()
        for nodelist in self.config.get_sections("nodelist"):
            for node in nodelist.get_sections("node"):
                node_data = {
                    "ring0_addr": None,
                    "ring1_addr": None,
                    "name": None,
                    "nodeid": None,
                }
                for attr_name, attr_value in node.get_attributes():
                    if attr_name in node_data:
                        node_data[attr_name] = attr_value
                result.append(NodeAddresses(
                    node_data["ring0_addr"],
                    node_data["ring1_addr"],
                    node_data["name"],
                    node_data["nodeid"]
                ))
        return result

    def set_quorum_options(self, report_processor, options):
        """
        Set options in quorum section
        options quorum options dict
        """
        report_processor.process_list(
            self.__validate_quorum_options(options)
        )
        quorum_section_list = self.__ensure_section(self.config, "quorum")
        self.__set_section_options(quorum_section_list, options)
        self.__update_two_node()
        self.__remove_empty_sections(self.config)

    def get_quorum_options(self):
        """
        Get configurable options from quorum section
        """
        options = {}
        for section in self.config.get_sections("quorum"):
            for name, value in section.get_attributes():
                if name in self.__class__.QUORUM_OPTIONS:
                    options[name] = value
        return options

    def __validate_quorum_options(self, options):
        report = []
        for name, value in sorted(options.items()):

            allowed_names = self.__class__.QUORUM_OPTIONS
            if name not in allowed_names:
                report.append(ReportItem.error(
                    report_codes.INVALID_OPTION,
                    "invalid {type} option '{option}'"
                        + ", allowed options are: {allowed}"
                    ,
                    info={
                        "option": name,
                        "type": "quorum",
                        "allowed_raw": allowed_names,
                        "allowed": " or ".join(allowed_names),
                    },
                ))
                continue

            if value == "":
                continue

            if name == "last_man_standing_window":
                if not value.isdigit():
                    report.append(ReportItem.error(
                        report_codes.INVALID_OPTION_VALUE,
                        "'{option_value}' is not a valid value for "
                            + "{option_name}, use {allowed_values}"
                        ,
                        info={
                            "option_name": name,
                            "option_value": value,
                            "allowed_values_raw": ("integer", ),
                            "allowed_values": "integer",
                        },
                    ))

            else:
                allowed_values = ("0", "1")
                if value not in allowed_values:
                    report.append(ReportItem.error(
                        report_codes.INVALID_OPTION_VALUE,
                        "'{option_value}' is not a valid value for "
                            + "{option_name}, use {allowed_values}"
                        ,
                        info={
                            "option_name": name,
                            "option_value": value,
                            "allowed_values_raw": allowed_values,
                            "allowed_values": " or ".join(allowed_values),
                        },
                    ))

        return report

    def has_quorum_device(self):
        """
        Check if quorum device is present in the config
        """
        for quorum in self.config.get_sections("quorum"):
            for device in quorum.get_sections("device"):
                if device.get_attributes("model"):
                    return True
        return False

    def get_quorum_device_settings(self):
        """
        Get configurable options from quorum.device section
        """
        model = None
        model_options = {}
        generic_options = {}
        for quorum in self.config.get_sections("quorum"):
            for device in quorum.get_sections("device"):
                for name, value in device.get_attributes():
                    if name == "model":
                        model = value
                    else:
                        generic_options[name] = value
                for subsection in device.get_sections():
                    if subsection.name not in model_options:
                        model_options[subsection.name] = {}
                    model_options[subsection.name].update(
                        subsection.get_attributes()
                    )
        return model, model_options.get(model, {}), generic_options

    def add_quorum_device(
        self, report_processor, model, model_options, generic_options
    ):
        """
        Add quorum device configuration
        model quorum device model
        model_options model specific options dict
        generic_options generic quorum device options dict
        """
        # validation
        if self.has_quorum_device():
            raise LibraryError(ReportItem.error(
                report_codes.QDEVICE_ALREADY_DEFINED,
                "quorum device is already defined"
            ))
        report_processor.process_list(
            self.__validate_quorum_device_model(model)
            +
            self.__validate_quorum_device_model_options(
                model,
                model_options,
                need_required=True
            )
            +
            self.__validate_quorum_device_generic_options(generic_options)
        )
        # configuration cleanup
        quorum_section_list = self.__ensure_section(self.config, "quorum")
        self.__set_section_options(
            quorum_section_list,
            {
                "allow_downscale": "",
                "auto_tie_breaker": "",
                "last_man_standing": "",
                "last_man_standing_window": "",
                "two_node": "",
            }
        )
        for quorum in quorum_section_list:
            for device in quorum.get_sections("device"):
                quorum.del_section(device)
        # add new configuration
        quorum = quorum_section_list[-1]
        new_device = config_parser.Section("device")
        quorum.add_section(new_device)
        self.__set_section_options([new_device], generic_options)
        new_device.set_attribute("model", model)
        new_model = config_parser.Section(model)
        self.__set_section_options([new_model], model_options)
        new_device.add_section(new_model)
        self.__update_two_node()
        self.__remove_empty_sections(self.config)

    def update_quorum_device(
        self, report_processor, model_options, generic_options
    ):
        """
        Update existing quorum device configuration
        model_options model specific options dict
        generic_options generic quorum device options dict
        """
        # validation
        if not self.has_quorum_device():
            raise LibraryError(ReportItem.error(
                report_codes.QDEVICE_NOT_DEFINED,
                "no quorum device is defined in this cluster"
            ))
        model = None
        for quorum in self.config.get_sections("quorum"):
            for device in quorum.get_sections("device"):
                for dummy_name, value in device.get_attributes("model"):
                    model = value
        report_processor.process_list(
            self.__validate_quorum_device_model_options(
                model,
                model_options,
                need_required=False
            )
            +
            self.__validate_quorum_device_generic_options(generic_options)
        )
        # set new configuration
        device_sections = []
        model_sections = []
        for quorum in self.config.get_sections("quorum"):
            device_sections.extend(quorum.get_sections("device"))
            for device in quorum.get_sections("device"):
                model_sections.extend(device.get_sections(model))
        self.__set_section_options(device_sections, generic_options)
        self.__set_section_options(model_sections, model_options)
        self.__update_two_node()
        self.__remove_empty_sections(self.config)

    def remove_quorum_device(self):
        """
        Remove all quorum device configuration
        """
        if not self.has_quorum_device():
            raise LibraryError(ReportItem.error(
                report_codes.QDEVICE_NOT_DEFINED,
                "no quorum device is defined in this cluster"
            ))
        for quorum in self.config.get_sections("quorum"):
            for device in quorum.get_sections("device"):
                quorum.del_section(device)
        self.__update_two_node()
        self.__remove_empty_sections(self.config)

    def __validate_quorum_device_model(self, model):
        report = []

        allowed_values = (
            "net",
        )
        if model not in allowed_values:
            report.append(ReportItem.error(
                report_codes.INVALID_OPTION_VALUE,
                "'{option_value}' is not a valid value for "
                    + "{option_name}, use {allowed_values}"
                ,
                info={
                    "option_name": "model",
                    "option_value": model,
                    "allowed_values_raw": allowed_values,
                    "allowed_values": " or ".join(allowed_values),
                },
                forceable=True
            ))

        return report

    def __validate_quorum_device_model_options(
        self, model, model_options, need_required
    ):
        if model == "net":
            return self.__validate_quorum_device_model_net_options(
                model_options,
                need_required
            )
        return []

    def __validate_quorum_device_model_net_options(
        self, model_options, need_required
    ):
        required_options = frozenset(["host"])
        optional_options = frozenset([
            "algorithm",
            "connect_timeout",
            "force_ip_version",
            "port",
            "tie_breaker",
        ])
        allowed_options = required_options | optional_options
        model_options_names = frozenset(model_options.keys())
        report = []

        if need_required:
            for missing in sorted(required_options - model_options_names):
                report.append(ReportItem.error(
                    report_codes.REQUIRED_OPTION_IS_MISSING,
                    "required option '{name}' is missing",
                    info={
                        "name": missing,
                    },
                ))

        for name, value in sorted(model_options.items()):
            if name not in allowed_options:
                report.append(ReportItem.error(
                    report_codes.INVALID_OPTION,
                    "invalid {type} option '{option}'"
                        + ", allowed options are: {allowed}"
                    ,
                    info={
                        "option": name,
                        "type": "quorum device model",
                        "allowed_raw": sorted(allowed_options),
                        "allowed": " or ".join(sorted(allowed_options)),
                    },
                    forceable=True
                ))
                continue

            if value == "":
                # do not allow to remove required options
                if name in required_options:
                    report.append(ReportItem.error(
                        report_codes.REQUIRED_OPTION_IS_MISSING,
                        "required option '{name}' is missing",
                        info={
                            "name": name,
                        },
                    ))
                else:
                    continue

            if name == "algorithm":
                allowed_algorithms = ("2nodelms", "ffsplit", "lms")
                if value not in allowed_algorithms:
                    report.append(ReportItem.error(
                        report_codes.INVALID_OPTION_VALUE,
                        "'{option_value}' is not a valid value for "
                            + "{option_name}, use {allowed_values}"
                        ,
                        info={
                            "option_name": "algorithm",
                            "option_value": value,
                            "allowed_values_raw": allowed_algorithms,
                            "allowed_values": " or ".join(allowed_algorithms),
                        },
                        forceable=True
                    ))

            if name == "connect_timeout":
                minimum, maximum = 1000, 2*60*1000
                if not (value.isdigit() and minimum <= int(value) <= maximum):
                    min_max = "{min}-{max}".format(min=minimum, max=maximum)
                    report.append(ReportItem.error(
                        report_codes.INVALID_OPTION_VALUE,
                        "'{option_value}' is not a valid value for "
                            + "{option_name}, use {allowed_values}"
                        ,
                        info={
                            "option_name": "connect_timeout",
                            "option_value": value,
                            "allowed_values_raw": (min_max, ),
                            "allowed_values": min_max,
                        },
                        forceable=True
                    ))

            if name == "force_ip_version":
                allowed_ip_version = ("0", "4", "6")
                if value not in allowed_ip_version:
                    report.append(ReportItem.error(
                        report_codes.INVALID_OPTION_VALUE,
                        "'{option_value}' is not a valid value for "
                            + "{option_name}, use {allowed_values}"
                        ,
                        info={
                            "option_name": "force_ip_version",
                            "option_value": value,
                            "allowed_values_raw": allowed_ip_version,
                            "allowed_values": " or ".join(allowed_ip_version),
                        },
                        forceable=True
                    ))

            if name == "port":
                minimum, maximum = 1, 65535
                if not (value.isdigit() and minimum <= int(value) <= maximum):
                    min_max = "{min}-{max}".format(min=minimum, max=maximum)
                    report.append(ReportItem.error(
                        report_codes.INVALID_OPTION_VALUE,
                        "'{option_value}' is not a valid value for "
                            + "{option_name}, use {allowed_values}"
                        ,
                        info={
                            "option_name": "port",
                            "option_value": value,
                            "allowed_values_raw": (min_max, ),
                            "allowed_values": min_max,
                        },
                        forceable=True
                    ))

            if name == "tie_breaker":
                node_ids = [node.id for node in self.get_nodes()]
                allowed_nonid = ["lowest", "highest"]
                if value not in allowed_nonid + node_ids:
                    allowed_values = tuple(allowed_nonid + ["valid node id"])
                    report.append(ReportItem.error(
                        report_codes.INVALID_OPTION_VALUE,
                        "'{option_value}' is not a valid value for "
                            + "{option_name}, use {allowed_values}"
                        ,
                        info={
                            "option_name": "tie_breaker",
                            "option_value": value,
                            "allowed_values_raw": tuple(allowed_values),
                            "allowed_values": " or ".join(allowed_values),
                        },
                        forceable=True
                    ))

        return report

    def __validate_quorum_device_generic_options(self, generic_options):
        optional_options = frozenset([
            "sync_timeout",
            "timeout",
        ])
        allowed_options = optional_options
        report = []

        for name, value in sorted(generic_options.items()):
            if name not in allowed_options:
                report.append(ReportItem.error(
                    report_codes.INVALID_OPTION,
                    "invalid {type} option '{option}'"
                        + ", allowed options are: {allowed}"
                    ,
                    info={
                        "option": name,
                        "type": "quorum device",
                        "allowed_raw": sorted(allowed_options),
                        "allowed": " or ".join(sorted(allowed_options)),
                    },
                    # model is never allowed in generic options, it is passed
                    # in its own argument
                    forceable=(name != "model")
                ))
                continue

            if value == "":
                continue

            if not value.isdigit():
                report.append(ReportItem.error(
                    report_codes.INVALID_OPTION_VALUE,
                    "'{option_value}' is not a valid value for "
                        + "{option_name}, use {allowed_values}"
                    ,
                    info={
                        "option_name": name,
                        "option_value": value,
                        "allowed_values_raw": ("integer", ),
                        "allowed_values": "integer",
                    },
                    forceable=True
                ))

        return report

    def __update_two_node(self):
        # get relevant status
        has_quorum_device = self.has_quorum_device()
        has_two_nodes = len(self.get_nodes()) == 2
        auto_tie_breaker = False
        for quorum in self.config.get_sections("quorum"):
            for attr in quorum.get_attributes("auto_tie_breaker"):
                auto_tie_breaker = attr[1] != "0"
        # update two_node
        if has_two_nodes and not auto_tie_breaker and not has_quorum_device:
            quorum_section_list = self.__ensure_section(self.config, "quorum")
            self.__set_section_options(quorum_section_list, {"two_node": "1"})
        else:
            for quorum in self.config.get_sections("quorum"):
                quorum.del_attributes_by_name("two_node")
        # update qdevice algorithm "lms" vs "2nodelms"
        for quorum in self.config.get_sections("quorum"):
            for device in quorum.get_sections("device"):
                for net in device.get_sections("net"):
                    algorithm = None
                    for dummy_name, value in net.get_attributes("algorithm"):
                        algorithm = value
                    if algorithm == "lms" and has_two_nodes:
                        net.set_attribute("algorithm", "2nodelms")
                    elif algorithm == "2nodelms" and not has_two_nodes:
                        net.set_attribute("algorithm", "lms")

    def __set_section_options(self, section_list, options):
        for section in section_list[:-1]:
            for name in options:
                section.del_attributes_by_name(name)
        for name, value in sorted(options.items()):
            if value == "":
                section_list[-1].del_attributes_by_name(name)
            else:
                section_list[-1].set_attribute(name, value)

    def __ensure_section(self, parent_section, section_name):
        section_list = parent_section.get_sections(section_name)
        if not section_list:
            new_section = config_parser.Section(section_name)
            parent_section.add_section(new_section)
            section_list.append(new_section)
        return section_list

    def __remove_empty_sections(self, parent_section):
        for section in parent_section.get_sections():
            self.__remove_empty_sections(section)
            if section.empty:
                parent_section.del_section(section)