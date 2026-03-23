/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { user } from "@web/core/user";
import { CalendarModel } from "@web/views/calendar/calendar_model";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";
import { CalendarFilterPanel } from "@web/views/calendar/filter_panel/calendar_filter_panel";

const TARGET_RES_MODEL = "trabajadores.vacacion";
const TARGET_FILTER_FIELD = "trabajador_id";
const WORKDAY_MARKER_CLASS = "o_portalgestor_workday_marker";
const WORKDAY_MARKER_COLOR = "rgba(217, 119, 6, 0.18)";
const WORKDAY_MARKER_BORDER = "rgba(217, 119, 6, 0.45)";

const { DateTime } = luxon;

function collectWorkerIdsFromDomain(domain, workerIds = new Set()) {
    if (!Array.isArray(domain)) {
        return workerIds;
    }
    if (domain.length === 3 && typeof domain[0] === "string") {
        const [fieldName, operator, value] = domain;
        if (fieldName === "trabajador_id") {
            if (operator === "=" && value) {
                workerIds.add(value);
            } else if (operator === "in" && Array.isArray(value)) {
                for (const workerId of value) {
                    if (workerId) {
                        workerIds.add(workerId);
                    }
                }
            }
        }
        return workerIds;
    }
    for (const item of domain) {
        collectWorkerIdsFromDomain(item, workerIds);
    }
    return workerIds;
}

function getSingleActiveRecordFilter(filterSections, targetFields) {
    const matches = [];
    for (const fieldName of targetFields) {
        const section = filterSections?.[fieldName];
        for (const filter of section?.filters || []) {
            if (filter.type !== "record" || !filter.active) {
                continue;
            }
            const value = filter.value || filter.recordId;
            if (!value) {
                continue;
            }
            matches.push({ fieldName, value });
        }
    }
    return matches.length === 1 ? matches[0] : null;
}

patch(CalendarModel.prototype, {
    setup() {
        super.setup(...arguments);
        this.data.assignmentMarkers = [];
    },

    get assignmentMarkers() {
        return this.data.assignmentMarkers || [];
    },

    makeContextDefaults(rawRecord) {
        const context = super.makeContextDefaults(...arguments);
        if (this.resModel !== TARGET_RES_MODEL) {
            return context;
        }

        const activeFilter = getSingleActiveRecordFilter(this.data?.filterSections, [TARGET_FILTER_FIELD]);
        if (activeFilter) {
            context.default_trabajador_id = activeFilter.value;
        }
        return context;
    },

    async updateData(data) {
        await super.updateData(...arguments);
        if (this.resModel !== TARGET_RES_MODEL) {
            data.assignmentMarkers = [];
            return;
        }

        const workerIds = [...collectWorkerIdsFromDomain(this.computeDomain(data))];
        if (!workerIds.length) {
            data.assignmentMarkers = [];
            return;
        }

        data.assignmentMarkers = await this.orm.call(this.resModel, "get_assignment_markers", [
            workerIds,
            data.range.start.toISODate(),
            data.range.end.toISODate(),
        ]);
    },

    async createFilter(fieldName, filterValue) {
        if (this.resModel !== TARGET_RES_MODEL || fieldName !== TARGET_FILTER_FIELD) {
            return super.createFilter(...arguments);
        }

        const info = this.meta.filtersInfo[fieldName];
        if (!info?.writeFieldName || !info.writeResModel) {
            return;
        }

        const selectedValues = Array.isArray(filterValue) ? filterValue.filter(Boolean) : [filterValue];
        const selectedValue = selectedValues[selectedValues.length - 1];
        const section = this.data.filterSections[fieldName];
        const existingRecordIds =
            section?.filters
                .filter((filter) => filter.type === "record" && filter.recordId)
                .map((filter) => filter.recordId) || [];
        const allFilter = section?.filters.find((filter) => filter.type === "all");
        if (allFilter) {
            allFilter.active = false;
        }

        if (existingRecordIds.length) {
            await this.orm.unlink(info.writeResModel, existingRecordIds);
        }
        if (!selectedValue) {
            await this.load();
            return;
        }

        const data = {
            user_id: user.userId,
            [info.writeFieldName]: selectedValue,
        };
        if (info.filterFieldName) {
            data[info.filterFieldName] = true;
        }
        await this.orm.create(info.writeResModel, [data]);
        await this.load();
    },

    async unlinkFilter(fieldName, recordId) {
        if (this.resModel === TARGET_RES_MODEL && fieldName === TARGET_FILTER_FIELD) {
            const section = this.data.filterSections[fieldName];
            const recordFilters =
                section?.filters.filter((filter) => filter.type === "record" && filter.recordId) || [];
            if (recordFilters.length === 1 && recordFilters[0].recordId === recordId) {
                const allFilter = section.filters.find((filter) => filter.type === "all");
                if (allFilter) {
                    allFilter.active = true;
                }
            }
        }
        return super.unlinkFilter(...arguments);
    },

    async loadFilterSection(fieldName, filterInfo, previousSection) {
        const section = await super.loadFilterSection(...arguments);
        if (this.resModel !== TARGET_RES_MODEL || fieldName !== TARGET_FILTER_FIELD || !section) {
            return section;
        }

        const recordFilters = section.filters.filter((filter) => filter.type === "record");
        const allFilter = section.filters.find((filter) => filter.type === "all");
        if (allFilter) {
            allFilter.active = !recordFilters.some((filter) => filter.active);
        }
        return section;
    },
});

patch(CalendarCommonRenderer.prototype, {
    get options() {
        const options = super.options;
        if (this.props.model.resModel !== TARGET_RES_MODEL) {
            return options;
        }

        const originalEvents = options.events?.bind(this);
        const originalEventClick = options.eventClick?.bind(this);
        return {
            ...options,
            events: (fetchInfo, successCb, failureCb) => {
                if (!originalEvents) {
                    successCb([...this.mapRecordsToEvents(), ...this.mapAssignmentMarkersToEvents()]);
                    return;
                }
                return originalEvents(
                    fetchInfo,
                    (events) => successCb([...events, ...this.mapAssignmentMarkersToEvents()]),
                    failureCb
                );
            },
            eventClick: (info) => {
                if (info.event.extendedProps?.isPortalGestorWorkdayMarker) {
                    info.jsEvent?.preventDefault();
                    return;
                }
                return originalEventClick?.(info);
            },
        };
    },

    mapAssignmentMarkersToEvents() {
        return this.props.model.assignmentMarkers.map((marker) => {
            const start = DateTime.fromISO(marker.date);
            return {
                id: marker.id,
                title: "",
                start: start.toISODate(),
                end: start.plus({ days: 1 }).toISODate(),
                allDay: true,
                display: "background",
                editable: false,
                startEditable: false,
                durationEditable: false,
                overlap: true,
                classNames: [WORKDAY_MARKER_CLASS],
                backgroundColor: WORKDAY_MARKER_COLOR,
                borderColor: WORKDAY_MARKER_BORDER,
                extendedProps: {
                    isPortalGestorWorkdayMarker: true,
                },
            };
        });
    },
});

patch(CalendarFilterPanel.prototype, {
    getAutoCompleteProps(section) {
        const props = super.getAutoCompleteProps(...arguments);
        if (this.props.model.resModel !== TARGET_RES_MODEL || section.fieldName !== TARGET_FILTER_FIELD) {
            return props;
        }
        return {
            ...props,
            placeholder: "Buscar trabajador",
        };
    },

    async loadSource(section, request) {
        if (this.props.model.resModel !== TARGET_RES_MODEL || section.fieldName !== TARGET_FILTER_FIELD) {
            return super.loadSource(...arguments);
        }

        const excludedWorkerIds = section.filters
            .filter((filter) => filter.type !== "all")
            .map((filter) => filter.value);
        const records = await this.orm.call("trabajadores.trabajador", "name_search", [], {
            name: request,
            operator: "ilike",
            args: [
                ["baja", "=", false],
                ["id", "not in", excludedWorkerIds],
            ],
            limit: 8,
            context: {},
        });

        const options = records.map((result) => ({
            value: result[0],
            label: result[1],
            model: "trabajadores.trabajador",
        }));

        if (records.length > 7) {
            options.push({
                label: _t("Search More..."),
                action: () =>
                    this.onSearchMore(
                        section,
                        "trabajadores.trabajador",
                        [
                            ["baja", "=", false],
                            ["id", "not in", excludedWorkerIds],
                        ],
                        request
                    ),
                classList: "o_calendar_dropdown_option",
            });
        }

        if (!records.length) {
            options.push({
                label: _t("No records"),
                classList: "o_m2o_no_result",
                unselectable: true,
            });
        }

        return options;
    },
});
